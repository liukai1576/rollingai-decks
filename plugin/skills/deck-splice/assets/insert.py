#!/usr/bin/env python3
"""
insert.py — insert slides from other decks into a rolling-deck deck at a
chosen page position. This is the driver behind the admin "加入 Deck"
(add-to-deck cart) task.

Pipeline (one run = one insertion point, N slides):
  1.  Snapshot target index.html (.bak-insert-<ts>)
  2.  Generate empty `is-splice` placeholder <section>s right after the
      section at --after-page (0 = before everything / after the cover is
      position 1)
  3.  Fill them via deck-splice's splice.py machinery (DOM copy, .slide →
      .src-slide rename, asset copy to assets/_borrowed/, CSS injection).
      Content is preserved verbatim — no restyle, no logo.
  4.  Renumber data-screen-label numeric prefixes across the deck
  5.  Rebuild deck.json (rolling-deck build-deckjson)
  6.  Re-ingest into slides.db (existing tags preserved by ingest_deck)
  7.  Copy each source slide's tags onto its new row
  8.  Generate thumbnails for the new slides only

Usage:
    python3 insert.py --spec spec.json
    python3 insert.py --spec -          # read spec JSON from stdin

Spec schema:
    {
      "target_deck_id": "lanyueliang-pitch",     # imports/<id>/render-output-full
      "after_page": 5,                            # 1-based; 0 = insert at very front
      "items": [
        {"source_deck_id": "RollingAI分享", "source_slide_key": "slide-041"},
        ...
      ]
    }

Exit codes: 0 ok · 1 validation/content error · 2 bad invocation.
All progress goes to stderr (the admin task runner captures it as the log).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ASSETS_DIR.parents[3]
DB_PATH = REPO_ROOT / "library" / "db" / "data" / "slides.db"

sys.path.insert(0, str(ASSETS_DIR))
import splice  # noqa: E402  (same skill: splice.py)
import feishu_ops  # noqa: E402  (div-based host: feishu-deck-h5 / keynote)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_deckjson = _load_module(
    REPO_ROOT / "plugin" / "skills" / "rolling-deck" / "assets" / "build-deckjson.py",
    "build_deckjson",
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ── section parsing (same depth-counted convention as build-deckjson) ────

SECTION_OPEN_RE = re.compile(
    r'<section\b[^>]*class="([^"]*)"[^>]*data-slide-key="([^"]+)"[^>]*>',
    re.DOTALL)
ANY_OPEN_RE = re.compile(r'<section\b', re.IGNORECASE)
ANY_CLOSE_RE = re.compile(r'</section>', re.IGNORECASE)


def _slide_token(classes: str) -> bool:
    return bool(re.search(r'(?<![\w-])slide(?![\w-])', classes))


def find_sections(html: str) -> list[dict]:
    """[{key, start, end}] for outer sections with the standalone `slide`
    class token, in DOM order. start/end are offsets of the full block."""
    out = []
    for m in SECTION_OPEN_RE.finditer(html):
        classes, key = m.group(1), m.group(2)
        if not _slide_token(classes):
            continue
        depth, pos = 1, m.end()
        while depth and pos < len(html):
            o = ANY_OPEN_RE.search(html, pos)
            c = ANY_CLOSE_RE.search(html, pos)
            if not c:
                sys.exit(f"unbalanced <section> after slide '{key}'")
            if o and o.start() < c.start():
                depth += 1; pos = o.end()
            else:
                depth -= 1; pos = c.end()
        out.append({"key": key, "start": m.start(), "end": pos})
    return out


def unique_outer_key(base: str, taken: set[str]) -> str:
    key = f"sp-{base}"
    if key not in taken:
        return key
    n = 2
    while f"{key}-{n}" in taken:
        n += 1
    return f"{key}-{n}"


def renumber_screen_labels(html: str) -> str:
    """Rewrite the numeric prefix of every slide section's
    data-screen-label to its 1-based DOM position. Labels without a
    numeric prefix are left untouched."""
    sections = find_sections(html)
    # Replace from the back so offsets stay valid.
    for idx in range(len(sections) - 1, -1, -1):
        s = sections[idx]
        open_tag_m = re.match(r'<section\b[^>]*>', html[s["start"]:s["end"]])
        open_tag = open_tag_m.group(0)
        lbl = re.search(r'data-screen-label="(\d+)(\s*[^"]*)"', open_tag)
        if not lbl:
            continue
        new_tag = (open_tag[:lbl.start()]
                   + f'data-screen-label="{idx + 1:02d}{lbl.group(2)}"'
                   + open_tag[lbl.end():])
        html = html[:s["start"]] + new_tag + html[s["start"] + len(open_tag):]
    return html


# ── DB helpers ────────────────────────────────────────────────────────────

def fetch_source_meta(items: list[dict]) -> list[dict]:
    """Attach title/tags from slides.db to each item. Missing rows get
    title=None (still spliceable — DB metadata is optional)."""
    conn = sqlite3.connect(DB_PATH)
    out = []
    for it in items:
        sid = f"{it['source_deck_id']}/{it['source_slide_key']}"
        row = conn.execute(
            "SELECT title, type_tag, subtype_tag, customer_tag, media_tag, "
            "       free_tags, notes FROM slides WHERE id = ?", (sid,)
        ).fetchone()
        meta = dict(it)
        if row:
            meta.update(title=row[0], type_tag=row[1], subtype_tag=row[2],
                        customer_tag=row[3], media_tag=row[4],
                        free_tags=row[5], notes=row[6])
        else:
            meta.update(title=None, type_tag=None, subtype_tag=None,
                        customer_tag=None, media_tag=None,
                        free_tags=None, notes=None)
            log(f"  · no DB row for {sid} (will splice without tag copy)")
        out.append(meta)
    conn.close()
    return out


def copy_tags_to_new_rows(target_deck_id: str, mapping: list[tuple[str, dict]]) -> None:
    """mapping: [(outer_key, source_meta)] — push source tags onto the
    freshly ingested rows."""
    conn = sqlite3.connect(DB_PATH)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for outer_key, meta in mapping:
        if meta["title"] is None:
            continue
        conn.execute(
            "UPDATE slides SET type_tag=?, subtype_tag=?, customer_tag=?, "
            "media_tag=?, free_tags=COALESCE(?, free_tags), updated_at=? "
            "WHERE id = ?",
            (meta["type_tag"], meta["subtype_tag"], meta["customer_tag"],
             meta["media_tag"], meta["free_tags"], now,
             f"{target_deck_id}/{outer_key}"))
    conn.commit()
    conn.close()


def copy_source_thumbnails(target_deck_id: str, target_dir: Path,
                           mapping: list[tuple[str, dict]]) -> None:
    """Copy each source slide's existing thumbnail to the spliced slide's
    thumbnail slot + set thumbnail_path. Splice copies the slide verbatim, so
    the source thumbnail is already correct — copying it is faster and more
    reliable than re-screenshotting the new page (which needs a live server)."""
    sys.path.insert(0, str(REPO_ROOT / "library" / "db"))
    from deck_mounts import discover_mounts
    mounts = discover_mounts(REPO_ROOT)
    tgt_thumbs = target_dir / ".thumbs"
    tgt_thumbs.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    copied = 0
    for outer_key, meta in mapping:
        src_dir = mounts.get(meta["source_deck_id"])
        if not src_dir:
            continue
        src_thumb = src_dir / ".thumbs" / f"{meta['source_slide_key']}.jpg"
        if not src_thumb.is_file():
            continue
        shutil.copy2(src_thumb, tgt_thumbs / f"{outer_key}.jpg")
        conn.execute(
            "UPDATE slides SET thumbnail_path=?, updated_at=? WHERE id=?",
            (f"decks/{target_deck_id}/.thumbs/{outer_key}.jpg", now,
             f"{target_deck_id}/{outer_key}"))
        copied += 1
    conn.commit()
    conn.close()
    log(f"thumbnails copied from source: {copied}/{len(mapping)}")


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="deck-splice/insert")
    ap.add_argument("--spec", required=True,
                    help="Path to spec JSON, or '-' for stdin.")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text(encoding="utf-8")
    spec = json.loads(raw)
    for k in ("target_deck_id", "after_page", "items"):
        if k not in spec:
            sys.exit(f"spec: missing '{k}'")
    target_deck_id = spec["target_deck_id"]
    after_page = int(spec["after_page"])
    items = spec["items"]
    if not items:
        sys.exit("spec: items is empty")

    # Resolve via deck mounts (handles DB-id → dir-name aliases).
    sys.path.insert(0, str(REPO_ROOT / "library" / "db"))
    from deck_mounts import discover_mounts
    mount = discover_mounts(REPO_ROOT).get(target_deck_id)
    target_dir = mount or (REPO_ROOT / "imports" / target_deck_id / "render-output-full")
    index_path = target_dir / "index.html"
    if not index_path.is_file():
        sys.exit(f"target deck not found: {index_path}")

    html = index_path.read_text(encoding="utf-8")

    # Two supported host packs (the spliced .src-slide is self-contained —
    # own 1920×1080 canvas + class-isolated CSS — so it renders the same in
    # either; only the placeholder WRAPPER differs):
    #   · rolling-deck     → <section class="slide is-splice">
    #   · feishu-deck-h5   → <div class="slide-frame"><div class="slide is-splice">
    is_rolling = '<main class="deck" id="deck">' in html
    is_feishu = feishu_ops.is_feishu_deck(html)
    if not (is_rolling or is_feishu):
        sys.exit("target is neither a rolling-deck nor a feishu-deck-h5 deck — "
                 "insert unsupported for this pack")

    if is_rolling:
        units = find_sections(html)               # [{key, start, end, …}]
    else:
        units = [{"key": f["key"], "start": f["frame_start"],
                  "end": f["frame_end"]} for f in feishu_ops.find_frames(html)]
    if not units:
        sys.exit("target has no slide sections")
    if not (0 <= after_page <= len(units)):
        sys.exit(f"after_page {after_page} out of range (deck has {len(units)} pages)")

    log(f"target: {target_deck_id} ({len(units)} pages, "
        f"{'feishu' if is_feishu else 'rolling'}) · insert after page {after_page} "
        f"· {len(items)} slide(s)")

    # 1. snapshot
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = index_path.with_suffix(f".html.bak-insert-{ts}")
    shutil.copy2(index_path, backup)
    log(f"snapshot: {backup.name}")

    # 2. build placeholders (per-host wrapper; both carry the is-splice marker
    #    + outer key/label so splice.py + renumber + build_deckjson find them)
    metas = fetch_source_meta(items)
    taken = {u["key"] for u in units}
    placeholders = []
    mapping: list[tuple[str, dict]] = []
    for pos, meta in enumerate(metas, start=1):
        outer_key = unique_outer_key(meta["source_slide_key"], taken)
        taken.add(outer_key)
        label_title = (meta["title"] or meta["source_slide_key"])[:40]
        page_guess = after_page + pos
        if is_rolling:
            placeholders.append(
                f'      <section class="slide is-splice" data-slide-key="{outer_key}" '
                f'data-screen-label="{page_guess:02d} {label_title}"></section>\n'
            )
        else:
            placeholders.append(
                f'    <div class="slide-frame">\n'
                f'      <div class="slide is-splice" data-layout="raw" '
                f'data-screen-label="{page_guess:02d} {label_title}" '
                f'data-slide-key="{outer_key}"></div>\n'
                f'    </div>\n'
            )
        mapping.append((outer_key, meta))

    insert_at = (units[after_page - 1]["end"] if after_page > 0
                 else units[0]["start"])
    block = "\n" + "".join(placeholders)
    html = html[:insert_at] + block + html[insert_at:]
    index_path.write_text(html, encoding="utf-8")
    log(f"placeholders inserted: {', '.join(k for k, _ in mapping)}")

    # 3. fill via splice.py
    def _sound_override(meta: dict):
        """Default sound comes from source markup (lazy-video class →
        audible, mirrors the feishu player). Admin free_tags override per
        slide: 有声视频 forces ON, 静音视频 forces OFF, neither → None
        (markup default stands)."""
        try:
            tags = json.loads(meta.get("free_tags") or "[]")
        except json.JSONDecodeError:
            tags = []
        if any("静音" in (t or "") for t in tags):
            return False
        if any("有声" in (t or "") for t in tags):
            return True
        return None

    def _splice_entry(k, m):
        e = {"outer_key": k,
             "source_deck_id": m["source_deck_id"],
             "source_slide_key": m["source_slide_key"]}
        ov = _sound_override(m)
        if ov is not None:
            e["sound"] = ov
        return e

    manifest = {
        "host_pack": "rolling-deck" if is_rolling else "feishu-deck-h5",
        "splices": [_splice_entry(k, m) for k, m in mapping],
    }
    manifest_path = target_dir / f".insert-manifest-{ts}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    rc = subprocess.run(
        [sys.executable, str(ASSETS_DIR / "splice.py"),
         "--target", str(target_dir), "--manifest", str(manifest_path)],
    ).returncode
    manifest_path.unlink(missing_ok=True)
    if rc != 0:
        log("splice failed — restoring snapshot")
        shutil.copy2(backup, index_path)
        return 1

    # 4. renumber screen labels
    html = index_path.read_text(encoding="utf-8")
    html = (renumber_screen_labels(html) if is_rolling
            else feishu_ops.renumber_labels(html))
    index_path.write_text(html, encoding="utf-8")
    log("screen labels renumbered")

    # 5. rebuild deck.json
    deck = (build_deckjson.build(index_path) if is_rolling
            else feishu_ops.build_deckjson(index_path))
    deck_json_path = target_dir / "deck.json"
    deck_json_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    log(f"deck.json rebuilt: {len(deck['slides'])} slides")

    # 6. re-ingest (tags preserved by ingest_deck's upsert)
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "library" / "db" / "ingest_deck.py"),
         target_deck_id, str(deck_json_path)],
    ).returncode
    if rc != 0:
        log("WARNING: ingest failed — HTML is updated but DB is stale")
        return 1

    # 7. copy source tags onto the new rows
    copy_tags_to_new_rows(target_deck_id, mapping)
    log("source tags copied to new slides")

    # 7b. copy the source slides' thumbnails onto the new rows (verbatim splice
    #     → source thumbnail is already correct; no re-screenshot needed)
    copy_source_thumbnails(target_deck_id, target_dir, mapping)

    # 8. fallback for any spliced slide whose source had no thumbnail —
    #    gen_thumbnails skips the ones we just copied (their files exist).
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "library" / "db" / "gen_thumbnails.py"),
         "--deck", target_deck_id],
    ).returncode
    if rc != 0:
        log("WARNING: thumbnail generation failed (deck content is fine; "
            "re-run gen_thumbnails.py manually)")

    # 9. verify (verify.sh's checks key off rolling's <section class="slide">
    #    + splice markers — not applicable to feishu's div structure)
    if is_rolling:
        rc = subprocess.run(
            ["bash", str(ASSETS_DIR / "verify.sh"), str(target_dir)],
        ).returncode
        if rc != 0:
            log("WARNING: verify.sh reported problems — inspect the deck")
            return 1

    log(f"done: {len(mapping)} slide(s) inserted into {target_deck_id} "
        f"after page {after_page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
