#!/usr/bin/env python3
"""
delete.py — remove one or more slides from a rolling-deck deck. This is the
mirror of insert.py and the driver behind the admin "从 Deck 删除" action.

Pipeline (one run = N slides removed from one deck):
  1.  Resolve the target deck via deck mounts; guard rolling-deck host only
  2.  Locate the requested sections by data-slide-key (refuse: missing key /
      the cover / deleting every slide)
  3.  Snapshot target index.html (.bak-delete-<ts>)
  4.  Cut the sections out of index.html (back-to-front, offsets stay valid)
  5.  Renumber data-screen-label numeric prefixes across the remaining deck
  6.  Rebuild deck.json (rolling-deck build-deckjson)
  7.  Re-ingest into slides.db (updates the shifted rows' page_no/labels)
  8.  Delete the removed rows from slides.db — ingest only upserts, it never
      prunes, so the gone slides would otherwise linger. The slides_fts
      trigger + slide_assets ON DELETE CASCADE clean up dependents.
  9.  Best-effort delete the removed slides' thumbnail files

Usage:
    python3 delete.py --spec spec.json
    python3 delete.py --spec -          # read spec JSON from stdin

Spec schema:
    {
      "target_deck_id": "AI组织方法论",      # imports/<id>/render-output-full
      "slide_keys": ["sp-slide-003", ...]   # data-slide-key of pages to remove
    }

Exit codes: 0 ok · 1 validation/content error · 2 bad invocation.
All progress goes to stderr (the admin task runner captures it as the log).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ASSETS_DIR.parents[3]
DB_PATH = REPO_ROOT / "library" / "db" / "data" / "slides.db"

# Reuse insert.py's section parser + label renumberer + build-deckjson loader
# (same skill, same depth-counted <section> convention). Importing it only
# runs function/constant defs, not main().
sys.path.insert(0, str(ASSETS_DIR))
import insert  # noqa: E402


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _remove_rows_and_thumbs(deck_id: str, keys: list[str]) -> None:
    """DELETE the removed slides' rows (FTS trigger + slide_assets cascade
    follow) and unlink their thumbnail files. Forward-only — by this point
    the HTML/deck.json are already the new truth."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    thumb_paths: list[str] = []
    for key in keys:
        sid = f"{deck_id}/{key}"
        row = conn.execute(
            "SELECT thumbnail_path FROM slides WHERE id = ?", (sid,)).fetchone()
        if row and row[0]:
            thumb_paths.append(row[0])
        conn.execute("DELETE FROM slides WHERE id = ?", (sid,))
    conn.commit()
    conn.close()
    log(f"db: deleted {len(keys)} row(s)")

    # Thumbnails are pure housekeeping — a file with no DB row is invisible.
    # Cover both possible locations: the DB's recorded path and the deck's
    # per-deck .thumbs/<key>.jpg.
    base = insert_target_dir(deck_id)
    for tp in thumb_paths:
        f = (REPO_ROOT / tp)
        if f.is_file():
            f.unlink(missing_ok=True)
    if base:
        for key in keys:
            f = base / ".thumbs" / f"{key}.jpg"
            if f.is_file():
                f.unlink(missing_ok=True)


def insert_target_dir(deck_id: str) -> Path | None:
    sys.path.insert(0, str(REPO_ROOT / "library" / "db"))
    from deck_mounts import discover_mounts
    return discover_mounts(REPO_ROOT).get(deck_id)


def main() -> int:
    ap = argparse.ArgumentParser(prog="deck-splice/delete")
    ap.add_argument("--spec", required=True,
                    help="Path to spec JSON, or '-' for stdin.")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text(encoding="utf-8")
    spec = json.loads(raw)
    for k in ("target_deck_id", "slide_keys"):
        if k not in spec:
            sys.exit(f"spec: missing '{k}'")
    target_deck_id = spec["target_deck_id"]
    want = list(dict.fromkeys(spec["slide_keys"]))  # de-dup, keep order
    if not want:
        sys.exit("spec: slide_keys is empty")

    target_dir = insert_target_dir(target_deck_id) or (
        REPO_ROOT / "imports" / target_deck_id / "render-output-full")
    index_path = target_dir / "index.html"
    if not index_path.is_file():
        sys.exit(f"target deck not found: {index_path}")

    html = index_path.read_text(encoding="utf-8")

    # Guard: rolling-deck hosts only. The feishu-deck-h5 pack renders
    # index.html from deck.json, so editing its HTML would be overwritten.
    if '<main class="deck" id="deck">' not in html:
        sys.exit("target is not a rolling-deck deck (no <main class=\"deck\">); "
                 "delete only supports rolling-deck decks")

    sections = insert.find_sections(html)
    if not sections:
        sys.exit("target has no slide sections")
    by_key = {s["key"]: s for s in sections}

    missing = [k for k in want if k not in by_key]
    if missing:
        sys.exit(f"slide_keys not found in deck: {', '.join(missing)}")
    # Refuse deleting the cover (first DOM section) — a rolling-deck must open
    # on its cover-hero.
    if sections[0]["key"] in want:
        sys.exit(f"refusing to delete the cover page (first slide "
                 f"'{sections[0]['key']}')")
    if len(want) >= len(sections):
        sys.exit("refusing to delete every slide in the deck")

    log(f"target: {target_deck_id} ({len(sections)} pages) · "
        f"deleting {len(want)} slide(s): {', '.join(want)}")

    # 1. snapshot
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = index_path.with_suffix(f".html.bak-delete-{ts}")
    shutil.copy2(index_path, backup)
    log(f"snapshot: {backup.name}")

    # 2. cut sections out, back-to-front so offsets stay valid
    targets = sorted((by_key[k] for k in want), key=lambda s: s["start"],
                     reverse=True)
    for s in targets:
        # Also swallow the whitespace immediately before the section so we
        # don't leave a widening gap of blank lines on repeated deletes.
        cut_start = s["start"]
        while cut_start > 0 and html[cut_start - 1] in " \t":
            cut_start -= 1
        if cut_start > 0 and html[cut_start - 1] == "\n":
            cut_start -= 1
        html = html[:cut_start] + html[s["end"]:]

    # 3. renumber screen labels on what remains
    html = insert.renumber_screen_labels(html)
    index_path.write_text(html, encoding="utf-8")
    log("sections removed · screen labels renumbered")

    # 4. rebuild deck.json
    deck = insert.build_deckjson.build(index_path)
    deck_json_path = target_dir / "deck.json"
    deck_json_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    log(f"deck.json rebuilt: {len(deck['slides'])} slides")

    # 5. re-ingest (refreshes page_no / screen_label on the shifted rows;
    #    tags preserved by ingest_deck's upsert)
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "library" / "db" / "ingest_deck.py"),
         target_deck_id, str(deck_json_path)],
    ).returncode
    if rc != 0:
        log("ingest failed — restoring snapshot")
        shutil.copy2(backup, index_path)
        return 1

    # 6. prune the removed rows + their thumbnails (ingest never deletes)
    _remove_rows_and_thumbs(target_deck_id, want)

    # 7. verify
    rc = subprocess.run(
        ["bash", str(ASSETS_DIR / "verify.sh"), str(target_dir)],
    ).returncode
    if rc != 0:
        log("WARNING: verify.sh reported problems — inspect the deck")
        return 1

    log(f"done: removed {len(want)} slide(s) from {target_deck_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
