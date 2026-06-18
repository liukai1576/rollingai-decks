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
import re
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


class InsertItem(BaseModel):
    source_deck_id: str
    source_slide_key: str


class InsertSlidesRequest(BaseModel):
    after_page: int          # 0 = insert before page 1
    items: list[InsertItem]


class DeleteSlidesRequest(BaseModel):
    slide_keys: list[str]    # data-slide-key of the pages to remove


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
    # FTS shadow is maintained by schema triggers (slides_fts_after_*).
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
        d["is_rolling_target"] = _is_rolling_deck(d["deck_id"])
        d["stale"] = _is_stale(conn, d["deck_id"])
        if needle and needle not in d["deck_id"].lower() and needle not in (d["display_name"] or "").lower():
            continue
        decks.append(d)
    conn.close()
    return {"count": len(decks), "decks": decks}


def _is_stale(conn, deck_id: str) -> bool:
    """True when the mounted index.html is newer than the deck's last
    ingest — i.e. someone edited the deck but the DB (page_no, titles,
    body_text, search index) still reflects the old content. Surfaced as
    a '需重新入库' badge in the UI instead of silently drifting."""
    base = DECK_PATHS.get(deck_id)
    if not base:
        return False
    index = base / "index.html"
    if not index.is_file():
        return False
    row = conn.execute(
        "SELECT MAX(updated_at) FROM slides WHERE deck_id = ?", (deck_id,)
    ).fetchone()
    if not row or not row[0]:
        return False
    try:
        # Tolerate both '+00:00' and 'Z' suffixes (different writers), and
        # treat naive timestamps as UTC (every writer in this repo uses UTC).
        dt = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ingested_at = dt.timestamp()
    except ValueError:
        return False
    # 5s grace: ingest runs right after the html is written.
    return index.stat().st_mtime > ingested_at + 5


# mtime-keyed cache: deck_id → (index mtime, is rolling-deck host)
_ROLLING_CACHE: dict[str, tuple[float, bool]] = {}

def _is_rolling_deck(deck_id: str) -> bool:
    """True if the mounted deck's index.html is a rolling-deck host —
    i.e. a valid insert-slides target. The marker is the pack's
    <main class="deck" id="deck"> shell element."""
    base = DECK_PATHS.get(deck_id)
    if not base:
        return False
    index = base / "index.html"
    if not index.is_file():
        return False
    mtime = index.stat().st_mtime
    cached = _ROLLING_CACHE.get(deck_id)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        ok = '<main class="deck" id="deck">' in index.read_text(encoding="utf-8")
    except OSError:
        ok = False
    _ROLLING_CACHE[deck_id] = (mtime, ok)
    return ok


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


# ---- API: tasks (background insert-slides runner) ----
#
# One daemon worker thread, strictly one task at a time (matches the
# "跑完一个再加下一段" workflow). Tasks persist in the `tasks` table;
# live output of the running task is buffered in memory and merged into
# GET responses, then flushed to the DB row on completion.
import secrets
import subprocess
import threading
import time as _time

INSERT_RUNNER = REPO / "plugin" / "skills" / "deck-splice" / "assets" / "insert.py"
DELETE_RUNNER = REPO / "plugin" / "skills" / "deck-splice" / "assets" / "delete.py"
HIDE_RUNNER = REPO / "plugin" / "skills" / "deck-splice" / "assets" / "hide.py"
TASK_TIMEOUT_S = 1800
_LIVE_LOGS: dict[str, list[str]] = {}
_worker_started = threading.Event()


def _set_task(task_id: str, **fields) -> None:
    conn = db()
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE tasks SET {sets} WHERE id=?",
                 [*fields.values(), task_id])
    conn.commit()
    conn.close()


def _stream_subprocess(cmd: list[str], lines: list[str],
                       stdin_data: str | None = None) -> int:
    """Run one subprocess, streaming combined output into `lines`.
    Returns the exit code; raises on global task timeout."""
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_data is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=str(REPO),
    )
    if stdin_data is not None:
        proc.stdin.write(stdin_data)
        proc.stdin.close()
    deadline = _time.time() + TASK_TIMEOUT_S
    for line in proc.stdout:
        lines.append(line.rstrip("\n"))
        if _time.time() > deadline:
            proc.kill()
            raise RuntimeError(f"task exceeded {TASK_TIMEOUT_S}s; killed")
    return proc.wait(timeout=60)


def _run_reingest(spec: dict, lines: list[str]) -> int:
    """Re-ingest pipeline for one deck: (rolling hosts) rebuild deck.json
    from index.html → ingest (tags preserved) → thumbnails for new/changed
    slides. Mirrors the manual three-step ritual in CLAUDE.md."""
    deck_id = spec["target_deck_id"]
    base = DECK_PATHS.get(deck_id)
    if not base:
        raise RuntimeError(f"no mount for deck '{deck_id}'")
    deck_json = base / "deck.json"
    if _is_rolling_deck(deck_id):
        rc = _stream_subprocess(
            [sys.executable,
             str(REPO / "plugin/skills/rolling-deck/assets/build-deckjson.py"),
             str(base / "index.html")], lines)
        if rc != 0:
            return rc
    if not deck_json.is_file():
        raise RuntimeError(f"{deck_json} missing (non-rolling deck without "
                           f"deck.json cannot be re-ingested)")
    rc = _stream_subprocess(
        [sys.executable, str(REPO / "library/db/ingest_deck.py"),
         deck_id, str(deck_json)], lines)
    if rc != 0:
        return rc
    return _stream_subprocess(
        [sys.executable, str(REPO / "library/db/gen_thumbnails.py"),
         "--deck", deck_id], lines)


def _run_one_task(task_id: str, kind: str, payload: str) -> None:
    _set_task(task_id, status="running", started_at=now_iso())
    lines = _LIVE_LOGS.setdefault(task_id, [])
    try:
        if kind == "insert-slides":
            rc = _stream_subprocess(
                [sys.executable, str(INSERT_RUNNER), "--spec", "-"],
                lines, stdin_data=payload)
        elif kind == "delete-slides":
            rc = _stream_subprocess(
                [sys.executable, str(DELETE_RUNNER), "--spec", "-"],
                lines, stdin_data=payload)
        elif kind in ("hide-slides", "unhide-slides"):
            rc = _stream_subprocess(
                [sys.executable, str(HIDE_RUNNER), "--spec", "-"],
                lines, stdin_data=payload)
        elif kind == "reingest":
            rc = _run_reingest(json.loads(payload), lines)
        else:
            raise RuntimeError(f"unknown task kind: {kind}")
        if rc == 0:
            _set_task(task_id, status="done", finished_at=now_iso(),
                      log="\n".join(lines))
        else:
            _set_task(task_id, status="failed", finished_at=now_iso(),
                      log="\n".join(lines),
                      error=f"runner exited with code {rc}")
    except Exception as e:  # noqa: BLE001 — task isolation boundary
        lines.append(f"!! {e}")
        _set_task(task_id, status="failed", finished_at=now_iso(),
                  log="\n".join(lines), error=str(e))
    finally:
        _LIVE_LOGS.pop(task_id, None)
        # New slides / new pages → deck title & rolling-target caches and
        # mounts may be stale.
        _ROLLING_CACHE.clear()
        _DECK_TITLE_CACHE.clear()


def _worker_loop() -> None:
    while True:
        conn = db()
        row = conn.execute(
            "SELECT id, kind, payload FROM tasks WHERE status='queued' "
            "ORDER BY created_at LIMIT 1").fetchone()
        conn.close()
        if row:
            _run_one_task(row["id"], row["kind"], row["payload"])
        else:
            _time.sleep(1.5)


@app.on_event("startup")
def _start_worker() -> None:
    if _worker_started.is_set():
        return
    _worker_started.set()
    # Tasks stuck in 'running' from a previous server process are dead.
    conn = db()
    conn.execute(
        "UPDATE tasks SET status='failed', error='interrupted by server restart', "
        "finished_at=? WHERE status='running'", (now_iso(),))
    conn.commit()
    conn.close()
    threading.Thread(target=_worker_loop, daemon=True,
                     name="task-worker").start()


@app.post("/api/decks/{deck_id:path}/insert-slides")
def create_insert_task(deck_id: str, body: InsertSlidesRequest):
    if not body.items:
        raise HTTPException(400, "items is empty")
    if not _is_rolling_deck(deck_id):
        raise HTTPException(409,
            f"deck '{deck_id}' is not a rolling-deck host — v1 only supports "
            f"rolling-deck targets (feishu-deck-h5 decks would be overwritten "
            f"on next render)")
    # Validate page bound against the DB's view of the deck.
    conn = db()
    page_count = conn.execute(
        "SELECT COUNT(*) FROM slides WHERE deck_id=?", (deck_id,)).fetchone()[0]
    if not (0 <= body.after_page <= page_count):
        conn.close()
        raise HTTPException(400,
            f"after_page {body.after_page} out of range (deck has {page_count} pages)")
    # Validate every source slide exists in the DB.
    missing = []
    for it in body.items:
        sid = f"{it.source_deck_id}/{it.source_slide_key}"
        if not conn.execute("SELECT 1 FROM slides WHERE id=?", (sid,)).fetchone():
            missing.append(sid)
    if missing:
        conn.close()
        raise HTTPException(404, f"source slides not in DB: {', '.join(missing)}")

    task_id = (f"task-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-"
               f"{secrets.token_hex(2)}")
    spec = {
        "target_deck_id": deck_id,
        "after_page": body.after_page,
        "items": [it.model_dump() for it in body.items],
    }
    conn.execute(
        "INSERT INTO tasks (id, kind, status, payload, created_at) "
        "VALUES (?, 'insert-slides', 'queued', ?, ?)",
        (task_id, json.dumps(spec, ensure_ascii=False), now_iso()))
    conn.commit()
    conn.close()
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/decks/{deck_id:path}/delete-slides")
def create_delete_task(deck_id: str, body: DeleteSlidesRequest):
    keys = list(dict.fromkeys(body.slide_keys))  # de-dup, keep order
    if not keys:
        raise HTTPException(400, "slide_keys is empty")
    if not _is_rolling_deck(deck_id):
        raise HTTPException(409,
            f"deck '{deck_id}' is not a rolling-deck host — delete only "
            f"supports rolling-deck decks (feishu-deck-h5 decks render their "
            f"index.html from deck.json and would be overwritten)")
    conn = db()
    rows = conn.execute(
        "SELECT slide_key, page_no FROM slides WHERE deck_id=?",
        (deck_id,)).fetchall()
    page_by_key = {r["slide_key"]: r["page_no"] for r in rows}
    conn_total = len(rows)
    missing = [k for k in keys if k not in page_by_key]
    if missing:
        conn.close()
        raise HTTPException(404, f"slides not in deck: {', '.join(missing)}")
    # Cover protection: page 1 is the cover-hero a rolling-deck must open on.
    cover = [k for k in keys if page_by_key.get(k) == 1]
    if cover:
        conn.close()
        raise HTTPException(400,
            f"refusing to delete the cover page (page 1): {', '.join(cover)}")
    if len(keys) >= conn_total:
        conn.close()
        raise HTTPException(400, "refusing to delete every slide in the deck")

    task_id = (f"task-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-"
               f"{secrets.token_hex(2)}")
    spec = {"target_deck_id": deck_id, "slide_keys": keys}
    conn.execute(
        "INSERT INTO tasks (id, kind, status, payload, created_at) "
        "VALUES (?, 'delete-slides', 'queued', ?, ?)",
        (task_id, json.dumps(spec, ensure_ascii=False), now_iso()))
    conn.commit()
    conn.close()
    return {"task_id": task_id, "status": "queued"}


_HIDDEN_SEC_RE = re.compile(
    r'<section\b[^>]*\bdata-slide-key="([^"]+)"[^>]*\bdata-hidden="1"[^>]*>',
    re.IGNORECASE)
_SCREEN_LABEL_RE = re.compile(r'data-screen-label="([^"]*)"')


def _hidden_sections(deck_id: str) -> list[dict]:
    """Parse the deck's index.html for sections marked data-hidden="1".
    Hidden pages live only in the HTML (they're excluded from deck.json/DB),
    so this is the source of truth for the '已隐藏' panel."""
    base = DECK_PATHS.get(deck_id)
    if not base:
        return []
    idx = base / "index.html"
    if not idx.is_file():
        return []
    html = idx.read_text(encoding="utf-8")
    out = []
    for m in _HIDDEN_SEC_RE.finditer(html):
        key = m.group(1)
        lbl = _SCREEN_LABEL_RE.search(m.group(0))
        out.append({"slide_key": key,
                    "screen_label": lbl.group(1) if lbl else ""})
    return out


@app.get("/api/decks/{deck_id:path}/hidden-slides")
def list_hidden_slides(deck_id: str):
    if deck_id not in DECK_PATHS:
        raise HTTPException(404, f"no mount for deck '{deck_id}'")
    items = _hidden_sections(deck_id)
    return {"deck_id": deck_id, "count": len(items), "hidden": items}


def _queue_hide_task(deck_id: str, action: str, keys: list[str]) -> dict:
    keys = list(dict.fromkeys(keys))
    if not keys:
        raise HTTPException(400, "slide_keys is empty")
    if not _is_rolling_deck(deck_id):
        raise HTTPException(409,
            f"deck '{deck_id}' is not a rolling-deck host — {action} only "
            f"supports rolling-deck decks")
    kind = "hide-slides" if action == "hide" else "unhide-slides"
    task_id = (f"task-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-"
               f"{secrets.token_hex(2)}")
    spec = {"action": action, "target_deck_id": deck_id, "slide_keys": keys}
    conn = db()
    conn.execute(
        "INSERT INTO tasks (id, kind, status, payload, created_at) "
        "VALUES (?, ?, 'queued', ?, ?)",
        (task_id, kind, json.dumps(spec, ensure_ascii=False), now_iso()))
    conn.commit()
    conn.close()
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/decks/{deck_id:path}/hide-slides")
def create_hide_task(deck_id: str, body: DeleteSlidesRequest):
    # Cover protection lives in the runner; validate keys exist & not cover here.
    conn = db()
    rows = conn.execute(
        "SELECT slide_key, page_no FROM slides WHERE deck_id=?",
        (deck_id,)).fetchall()
    conn.close()
    page_by_key = {r["slide_key"]: r["page_no"] for r in rows}
    missing = [k for k in body.slide_keys if k not in page_by_key]
    if missing:
        raise HTTPException(404, f"slides not in deck: {', '.join(missing)}")
    cover = [k for k in body.slide_keys if page_by_key.get(k) == 1]
    if cover:
        raise HTTPException(400,
            f"refusing to hide the cover page (page 1): {', '.join(cover)}")
    return _queue_hide_task(deck_id, "hide", body.slide_keys)


@app.post("/api/decks/{deck_id:path}/unhide-slides")
def create_unhide_task(deck_id: str, body: DeleteSlidesRequest):
    # Unhide targets are hidden pages — they live in the HTML, not the DB.
    hidden = {h["slide_key"] for h in _hidden_sections(deck_id)}
    missing = [k for k in body.slide_keys if k not in hidden]
    if missing:
        raise HTTPException(404, f"not hidden in deck: {', '.join(missing)}")
    return _queue_hide_task(deck_id, "unhide", body.slide_keys)


@app.post("/api/decks/{deck_id:path}/reingest")
def create_reingest_task(deck_id: str):
    """Queue a re-ingest for a deck whose index.html changed after its
    last ingest (the 'stale' badge's one-click fix)."""
    if deck_id not in DECK_PATHS:
        raise HTTPException(404, f"no mount for deck '{deck_id}'")
    task_id = (f"task-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-"
               f"{secrets.token_hex(2)}")
    spec = {"target_deck_id": deck_id}
    conn = db()
    conn.execute(
        "INSERT INTO tasks (id, kind, status, payload, created_at) "
        "VALUES (?, 'reingest', 'queued', ?, ?)",
        (task_id, json.dumps(spec, ensure_ascii=False), now_iso()))
    conn.commit()
    conn.close()
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/tasks")
def list_tasks(limit: int = Query(20, le=100)):
    conn = db()
    rows = conn.execute(
        "SELECT id, kind, status, payload, error, created_at, started_at, "
        "finished_at FROM tasks ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    tasks = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d["payload"])
        except json.JSONDecodeError:
            pass
        tasks.append(d)
    return {"count": len(tasks), "tasks": tasks}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    conn = db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"task not found: {task_id}")
    d = dict(row)
    try:
        d["payload"] = json.loads(d["payload"])
    except json.JSONDecodeError:
        pass
    if d["status"] == "running" and task_id in _LIVE_LOGS:
        d["log"] = "\n".join(_LIVE_LOGS[task_id])
    return d


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
