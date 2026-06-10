#!/usr/bin/env python3
"""
platform/admin/server.py — Slide & Story 管理后端 (FastAPI)

启动：
    pip install -r platform/admin/requirements.txt
    python3 platform/admin/server.py
    # → http://localhost:8123

提供：
    · GET  /api/slides           列表 + 过滤
    · GET  /api/slides/{id}      单条详情
    · PUT  /api/slides/{id}      更新 tag
    · GET  /api/stories          列表
    · GET  /api/stories/{id}     单条 + 成员
    · POST /api/stories          新建
    · PUT  /api/stories/{id}     更新
    · DELETE /api/stories/{id}   删除
    · GET  /api/stats            标签统计
    · POST /api/stories/{id}/export-deck   未实现，预留给未来再生成
    · GET  /decks/{deck_id}/...  代理静态 deck 文件 (preview iframe 用)

静态前端在 static/index.html。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---- Paths ----
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
DB_PATH = REPO / "library" / "db" / "data" / "slides.db"
THUMBS_DIR = REPO / "library" / "db" / "data" / "thumbs"
STATIC_DIR = ROOT / "static"
SKILLS_DIR = REPO / "plugin" / "skills"
sys.path.insert(0, str(REPO / "plugin"))

# Decks live outside the public repo (imports/ is gitignored). The admin
# server only proxies them locally for the preview iframe.
#
# Mount discovery is now dynamic — any imports/<deck_id>/render-output-full/
# with an index.html is auto-mounted. Legacy DB-id → dir-name aliases (e.g.
# "kangshifu" → "RollingAI分享") live in the optional, gitignored file
# imports/.deck-mounts.json. See library/db/deck_mounts.py.
sys.path.insert(0, str(REPO / "library" / "db"))
from deck_mounts import discover_mounts  # noqa: E402

DECK_PATHS: dict[str, Path] = discover_mounts(REPO)

_DECK_TITLE_CACHE: dict[str, str] = {}

def deck_display_name(deck_id: str) -> str:
    """Return the original deck title (from deck.json) or the slug as fallback.
    We do NOT invent English names — show whatever the source file was called."""
    if deck_id in _DECK_TITLE_CACHE:
        return _DECK_TITLE_CACHE[deck_id]
    name = deck_id
    base = DECK_PATHS.get(deck_id)
    if base and base.is_dir():
        deck_json = base / "deck.json"
        if deck_json.is_file():
            try:
                d = json.loads(deck_json.read_text("utf-8"))
                t = d.get("deck", {}).get("title") or d.get("title")
                if t:
                    name = t
            except Exception:
                pass
    _DECK_TITLE_CACHE[deck_id] = name
    return name


# ---- DB helpers ----
def db() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise HTTPException(500, f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # free_tags is stored as JSON string — return parsed array
    if "free_tags" in d and isinstance(d["free_tags"], str):
        try:
            d["free_tags"] = json.loads(d["free_tags"])
        except json.JSONDecodeError:
            d["free_tags"] = []
    return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- App ----
app = FastAPI(title="RollingAI Slide Admin")

# CORS open for local development convenience (only running on localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ---- Models ----
class SlideUpdate(BaseModel):
    title: Optional[str] = None
    type_tag: Optional[str] = None
    subtype_tag: Optional[str] = None
    customer_tag: Optional[str] = None
    media_tag: Optional[str] = None
    free_tags: Optional[list[str]] = None
    notes: Optional[str] = None


class StoryCreate(BaseModel):
    id: str               # e.g. "kangshifu/my-story"
    title: str
    description: Optional[str] = None
    deck_id: str
    start_page: int
    end_page: int


class StoryUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None


# ---- API: slides ----
@app.get("/api/slides")
def list_slides(
    deck_id: Optional[str] = None,
    type_tag: Optional[str] = None,
    customer_tag: Optional[str] = None,
    media_tag: Optional[str] = None,
    free_tag: Optional[str] = None,                 # match inside JSON array
    search: Optional[str] = Query(None, description="substring over title/body/tags"),
    in_story: Optional[str] = None,                 # story_id; rows in that story
    needs_review: Optional[bool] = None,
    limit: int = Query(500, ge=1, le=2000),
):
    conn = db()
    sql = "SELECT s.* FROM slides s"
    where, params = [], []
    if in_story:
        # Stories are now (start_page, end_page) ranges; derive membership.
        sql += (" JOIN stories st ON st.id = ? AND st.deck_id = s.deck_id "
                "AND s.page_no BETWEEN st.start_page AND st.end_page")
        params.append(in_story)
    if search:
        # Substring (LIKE) match across title, body_text, and every tag column —
        # more forgiving than FTS for short Chinese queries (e.g. 单字 "牛").
        like = f"%{search}%"
        where.append(
            "(s.title LIKE ? OR s.body_text LIKE ? "
            " OR s.type_tag LIKE ? OR s.subtype_tag LIKE ? "
            " OR s.customer_tag LIKE ? OR s.media_tag LIKE ? "
            " OR s.free_tags LIKE ? OR s.notes LIKE ?)"
        )
        params.extend([like] * 8)
    if deck_id:       where.append("s.deck_id = ?");       params.append(deck_id)
    if type_tag:      where.append("s.type_tag = ?");      params.append(type_tag)
    if customer_tag:  where.append("s.customer_tag = ?");  params.append(customer_tag)
    if media_tag:     where.append("s.media_tag = ?");     params.append(media_tag)
    if free_tag:      where.append("s.free_tags LIKE ?");  params.append(f"%{free_tag}%")
    if needs_review is True:
        where.append("s.free_tags LIKE '%needs-review%'")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.deck_id, s.page_no LIMIT ?"
    params.append(limit)
    rows = [row_to_dict(r) for r in conn.execute(sql, params)]
    conn.close()
    return {"count": len(rows), "slides": rows}


@app.get("/api/slides/{slide_id:path}")
def get_slide(slide_id: str):
    conn = db()
    row = conn.execute("SELECT * FROM slides WHERE id = ?", (slide_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Slide not found: {slide_id}")
    slide = row_to_dict(row)
    # Also return story memberships — derived from page_no being within
    # any story's [start_page, end_page] range for this deck.
    slide["stories"] = [
        dict(r) for r in conn.execute(
            "SELECT st.id, st.title, "
            "       (slide.page_no - st.start_page) AS position "
            "FROM stories st, slides slide "
            "WHERE slide.id = ? AND st.deck_id = slide.deck_id "
            "  AND slide.page_no BETWEEN st.start_page AND st.end_page",
            (slide_id,)
        )
    ]
    conn.close()
    return slide


@app.put("/api/slides/{slide_id:path}")
def update_slide(slide_id: str, body: SlideUpdate):
    conn = db()
    row = conn.execute("SELECT id FROM slides WHERE id = ?", (slide_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Slide not found: {slide_id}")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        return {"updated": 0}
    # JSON-encode free_tags
    if "free_tags" in changes:
        changes["free_tags"] = json.dumps(changes["free_tags"], ensure_ascii=False)
    set_clause = ", ".join(f"{k} = ?" for k in changes)
    params = list(changes.values()) + [now_iso(), slide_id]
    conn.execute(
        f"UPDATE slides SET {set_clause}, updated_at = ? WHERE id = ?",
        params
    )
    # Sync FTS
    if "title" in changes:
        conn.execute("DELETE FROM slides_fts WHERE id = ?", (slide_id,))
        new = conn.execute(
            "SELECT title, body_text FROM slides WHERE id = ?", (slide_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO slides_fts(id, title, body_text) VALUES (?, ?, ?)",
            (slide_id, new["title"], new["body_text"])
        )
    conn.commit()
    conn.close()
    return {"updated": 1, "id": slide_id}


# ---- API: stories ----
@app.get("/api/stories")
def list_stories(
    deck_id: Optional[str] = None,
    search: Optional[str] = None,
):
    conn = db()
    sql = ("SELECT s.*, "
           " (s.end_page - s.start_page + 1) AS slide_count, "
           " (SELECT thumbnail_path FROM slides sl "
           "    WHERE sl.deck_id = s.deck_id AND sl.page_no = s.start_page) "
           "   AS cover_thumbnail_path "
           "FROM stories s")
    where, params = [], []
    if deck_id:
        where.append("s.deck_id = ?")
        params.append(deck_id)
    if search:
        like = f"%{search}%"
        where.append(
            "(s.title LIKE ? OR s.description LIKE ? OR s.id LIKE ?)"
        )
        params.extend([like, like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.deck_id, s.start_page, slide_count DESC"
    rows = []
    for r in conn.execute(sql, params):
        d = dict(r)
        d["deck_display_name"] = deck_display_name(d["deck_id"])
        rows.append(d)
    conn.close()
    return {"count": len(rows), "stories": rows}


@app.get("/api/stories/{story_id:path}")
def get_story(story_id: str):
    conn = db()
    story = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    if not story:
        raise HTTPException(404, f"Story not found: {story_id}")
    out = dict(story)
    out["deck_display_name"] = deck_display_name(out["deck_id"])
    # Membership derived from page_no range; section pages included but
    # caller can filter by type_tag != 'Section' if desired.
    out["slides"] = [
        row_to_dict(r) for r in conn.execute(
            "SELECT s.*, (s.page_no - ?) AS position FROM slides s "
            "WHERE s.deck_id = ? AND s.page_no BETWEEN ? AND ? "
            "ORDER BY s.page_no",
            (story["start_page"], story["deck_id"],
             story["start_page"], story["end_page"])
        )
    ]
    conn.close()
    return out


@app.post("/api/stories")
def create_story(body: StoryCreate):
    conn = db()
    exists = conn.execute("SELECT id FROM stories WHERE id = ?", (body.id,)).fetchone()
    if exists:
        raise HTTPException(409, f"Story already exists: {body.id}")
    if body.start_page > body.end_page:
        raise HTTPException(400, "start_page must be <= end_page")
    now = now_iso()
    conn.execute(
        "INSERT INTO stories (id, title, description, deck_id, start_page, end_page, "
        "                     notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (body.id, body.title, body.description, body.deck_id,
         body.start_page, body.end_page, None, now, now)
    )
    conn.commit()
    conn.close()
    return {"created": body.id}


@app.put("/api/stories/{story_id:path}")
def update_story(story_id: str, body: StoryUpdate):
    conn = db()
    row = conn.execute("SELECT id FROM stories WHERE id = ?", (story_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Story not found: {story_id}")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return {"updated": 0}
    if ("start_page" in fields and "end_page" in fields and
            fields["start_page"] > fields["end_page"]):
        raise HTTPException(400, "start_page must be <= end_page")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [now_iso(), story_id]
    conn.execute(
        f"UPDATE stories SET {set_clause}, updated_at = ? WHERE id = ?",
        params
    )
    conn.commit()
    conn.close()
    return {"updated": story_id}


@app.delete("/api/stories/{story_id:path}")
def delete_story(story_id: str):
    conn = db()
    conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
    conn.commit()
    conn.close()
    return {"deleted": story_id}


# ---- API: decks ----
@app.get("/api/decks")
def list_decks(search: Optional[str] = None):
    """One row per deck with summary + cover-slide reference for thumbnails."""
    conn = db()
    rows = conn.execute(
        "SELECT s.deck_id, "
        "       COUNT(*) AS slide_count, "
        "       (SELECT COUNT(*) FROM stories st WHERE st.deck_id = s.deck_id) "
        "         AS story_count, "
        "       (SELECT slide_key FROM slides WHERE deck_id = s.deck_id "
        "          ORDER BY page_no LIMIT 1) AS cover_slide_key, "
        "       (SELECT title FROM slides WHERE deck_id = s.deck_id "
        "          ORDER BY page_no LIMIT 1) AS cover_title, "
        "       (SELECT thumbnail_path FROM slides WHERE deck_id = s.deck_id "
        "          ORDER BY page_no LIMIT 1) AS cover_thumbnail_path "
        "FROM slides s GROUP BY s.deck_id ORDER BY s.deck_id"
    ).fetchall()
    decks = []
    needle = (search or "").lower().strip()
    for r in rows:
        d = dict(r)
        d["display_name"] = deck_display_name(d["deck_id"])
        d["has_mount"] = d["deck_id"] in DECK_PATHS and DECK_PATHS[d["deck_id"]].is_dir()
        if needle and needle not in d["deck_id"].lower() and needle not in (d["display_name"] or "").lower():
            continue
        decks.append(d)
    conn.close()
    return {"count": len(decks), "decks": decks}


# ---- API: skills ----
# Backed by plugin/skills/registry.py. Re-scanned per request so editing
# any SKILL.md / pack.json is reflected without a server restart.
@app.get("/api/skills")
def list_skills_api(kind: Optional[str] = None):
    try:
        # Lazy import so a registry bug doesn't take the server down at boot.
        from skills import registry  # type: ignore
        # Force a fresh module read on every request (cheap; ~10ms for 10 skills).
        import importlib
        importlib.reload(registry)
        # Lenient mode: the admin UI prefers "show everything with warnings"
        # over "halt on first structural problem". CI / `python3 registry.py`
        # uses strict mode by default.
        skills = registry.list_skills(strict=False)
    except Exception as e:
        raise HTTPException(500, f"registry failed: {e}")
    if kind:
        skills = [s for s in skills if kind in (s.get("kind") or [])]
    grouped = {}
    for s in skills:
        for k in (s.get("kind") or ["其他"]):
            grouped.setdefault(k, []).append(s)
    # Canonical kind order; unknown kinds tacked on the end.
    KIND_ORDER = ["构思", "创建", "布局风格", "调整", "管理分析"]
    ordered = {k: grouped[k] for k in KIND_ORDER if k in grouped}
    for k, v in grouped.items():
        if k not in ordered:
            ordered[k] = v
    return {
        "count":  len(skills),
        "skills": skills,
        "grouped": ordered,
        "kind_order": KIND_ORDER,
    }


# ---- API: stats ----
@app.get("/api/stats")
def stats():
    conn = db()
    out: dict[str, list] = {}
    for axis in ("type_tag", "subtype_tag", "customer_tag", "media_tag"):
        out[axis] = [
            {"value": r[0], "count": r[1]}
            for r in conn.execute(
                f"SELECT {axis}, COUNT(*) FROM slides "
                f"WHERE {axis} IS NOT NULL GROUP BY {axis} ORDER BY COUNT(*) DESC"
            )
        ]
    out["totals"] = {
        "slides": conn.execute("SELECT COUNT(*) FROM slides").fetchone()[0],
        "stories": conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0],
        "needs_review": conn.execute(
            "SELECT COUNT(*) FROM slides WHERE free_tags LIKE '%needs-review%'"
        ).fetchone()[0],
    }
    # Decks
    out["decks"] = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT deck_id FROM slides ORDER BY deck_id"
        )
    ]
    conn.close()
    return out


# ---- API: future-feature stubs ----
@app.post("/api/stories/{story_id:path}/export-deck")
def export_story_to_deck(story_id: str):
    """TODO: render the story's slides into a fresh deck.json + index.html.
    For now, return the deck.json scaffold (no rendering)."""
    conn = db()
    story = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
    if not story:
        raise HTTPException(404, f"Story not found: {story_id}")
    slides = conn.execute(
        "SELECT s.slide_key, s.title FROM story_slides ss "
        "JOIN slides s ON s.id = ss.slide_id "
        "WHERE ss.story_id = ? ORDER BY ss.position",
        (story_id,)
    ).fetchall()
    conn.close()
    return {
        "story_id": story_id,
        "title": story["title"],
        "deck_json_preview": {
            "title": story["title"],
            "slides": [{"key": r["slide_key"], "title": r["title"]} for r in slides],
        },
        "todo": "actually build deck.json + call render-deck.py (next iteration)",
    }


# ---- Deck preview proxy (read-only) ----
@app.get("/decks/{deck_id}/{path:path}")
def deck_file(deck_id: str, path: str):
    """Serve files under DECK_PATHS[deck_id]/{path}. Read-only. Used by the
    preview iframe in the UI to show a slide's actual rendered HTML."""
    base = DECK_PATHS.get(deck_id)
    if not base or not base.is_dir():
        raise HTTPException(404, f"No deck mounted for {deck_id}")
    target = (base / path).resolve()
    # Path traversal guard
    try:
        target.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(403, "Path escapes deck root")
    if not target.is_file():
        raise HTTPException(404, f"File not found: {path}")
    return FileResponse(target)


# Some rendered decks (those produced by `render-deck.py` invoked directly,
# without the `keynote-to-html` localizer step) reference renderer assets via
# `../../../plugin/skills/<pack>/...` relative paths. Inside the admin iframe
# those resolve to `/plugin/skills/...`, so we serve them out of the repo's
# plugin/ tree. Read-only + traversal guard, same pattern as /decks/.
PLUGIN_DIR = REPO / "plugin"


@app.get("/plugin/{path:path}")
def plugin_file(path: str):
    target = (PLUGIN_DIR / path).resolve()
    try:
        target.relative_to(PLUGIN_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "Path escapes plugin root")
    if not target.is_file():
        raise HTTPException(404, f"File not found: {path}")
    return FileResponse(target)


# ---- Static UI ----
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Serve pre-rendered slide thumbnails (see library/db/gen_thumbnails.py).
# Frontend referenecs them via paths like "thumbs/kangshifu/slide-004.jpg".
if THUMBS_DIR.is_dir():
    app.mount("/thumbs", StaticFiles(directory=THUMBS_DIR), name="thumbs")


@app.get("/")
def root():
    # Hard no-cache so iterating on the UI doesn't get stuck on a stale
    # index.html in the browser.
    resp = FileResponse(STATIC_DIR / "index.html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ---- Entry ----
if __name__ == "__main__":
    import uvicorn
    print(f"DB: {DB_PATH}")
    for d, p in DECK_PATHS.items():
        print(f"deck['{d}']: {p} {'(found)' if p.is_dir() else '(MISSING)'}")
    uvicorn.run("server:app", host="127.0.0.1", port=8123, reload=True)
