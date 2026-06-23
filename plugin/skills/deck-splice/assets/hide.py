#!/usr/bin/env python3
"""
hide.py — hide / unhide slides in a rolling-deck deck WITHOUT deleting them.

Hiding flips a slide's standalone `slide` class token to `slide-hidden` and
adds data-hidden="1". The rolling-deck player iterates
`document.querySelectorAll('.slide')`, so a `slide-hidden` section is skipped
in navigation AND page counting; an injected `.slide-hidden{display:none}`
rule keeps it off-screen. The <section> never moves, so unhide restores it to
its exact original position.

Because build-deckjson keys off the standalone `slide` token, a hidden
section drops out of deck.json (and thus the active slides.db list) on its
own — no parser change needed. The page stays in index.html, recoverable via
the admin "已隐藏" panel (which reads data-hidden straight from the HTML).

Pipeline (one run = N slides, one action):
  1. Resolve the target deck via deck mounts; guard rolling-deck host only
  2. Locate the requested sections by data-slide-key
       hide:   must be currently visible (and not the cover)
       unhide: must be currently hidden
  3. Snapshot index.html (.bak-hide-<ts>)
  4. Flip each section's class token + data-hidden attribute
  5. Inject the .slide-hidden CSS rule once (idempotent, hide only)
  6. Renumber data-screen-label across the remaining visible slides
  7. Rebuild deck.json (rolling-deck build-deckjson; hidden auto-excluded)
  8. Re-ingest into slides.db
  9. hide:   prune the now-hidden rows from the active list (ingest never
            prunes); unhide: regenerate the restored slides' thumbnails

Usage:
    python3 hide.py --spec spec.json
    python3 hide.py --spec -          # read spec JSON from stdin

Spec schema:
    {
      "action": "hide",                     # or "unhide"
      "target_deck_id": "AI组织方法论",
      "slide_keys": ["program-overview", ...]
    }

Exit codes: 0 ok · 1 validation/content error · 2 bad invocation.
All progress goes to stderr (the admin task runner captures it as the log).
"""
from __future__ import annotations

import argparse
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
import insert  # noqa: E402  (reuse find_sections / renumber / build_deckjson)
import feishu_ops  # noqa: E402  (div-based path for feishu-deck-h5 / keynote)

HIDE_CSS = (".slide-hidden{display:none !important}"
            "  /* hide-slide: hidden pages, see deck-splice/hide.py */")
HIDE_SENTINEL = "/* hide-slide:"
_SLIDE_TOKEN_RE = re.compile(r'(?<![\w-])slide(?![\w-])')


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def find_all_sections(html: str) -> list[dict]:
    """Like insert.find_sections but also includes HIDDEN sections (class
    token `slide-hidden`). insert's finder filters to the standalone `slide`
    token only, so it can't see hidden pages — unhide needs them."""
    out = []
    for m in insert.SECTION_OPEN_RE.finditer(html):
        classes, key = m.group(1), m.group(2)
        if not (insert._slide_token(classes) or "slide-hidden" in classes):
            continue
        depth, pos = 1, m.end()
        while depth and pos < len(html):
            o = insert.ANY_OPEN_RE.search(html, pos)
            c = insert.ANY_CLOSE_RE.search(html, pos)
            if not c:
                sys.exit(f"unbalanced <section> after slide '{key}'")
            if o and o.start() < c.start():
                depth += 1; pos = o.end()
            else:
                depth -= 1; pos = c.end()
        out.append({"key": key, "start": m.start(), "end": pos})
    return out


def _resolve_dir(deck_id: str) -> Path:
    sys.path.insert(0, str(REPO_ROOT / "library" / "db"))
    from deck_mounts import discover_mounts
    return discover_mounts(REPO_ROOT).get(deck_id) or (
        REPO_ROOT / "imports" / deck_id / "render-output-full")


def _open_tag(html: str, sec: dict) -> tuple[int, int, str]:
    """(start, end, text) of a section's opening <section …> tag."""
    gt = html.index(">", sec["start"])
    return sec["start"], gt + 1, html[sec["start"]:gt + 1]


def _is_hidden_tag(open_tag: str) -> bool:
    return 'data-hidden="1"' in open_tag


def _flip_to_hidden(open_tag: str) -> str:
    m = re.search(r'class="([^"]*)"', open_tag)
    classes = m.group(1)
    new_classes = _SLIDE_TOKEN_RE.sub("slide-hidden", classes, count=1)
    tag = open_tag[:m.start(1)] + new_classes + open_tag[m.end(1):]
    if 'data-hidden="1"' not in tag:
        tag = tag[:-1].rstrip() + ' data-hidden="1">'
    return tag


def _flip_to_visible(open_tag: str) -> str:
    tag = open_tag.replace("slide-hidden", "slide")
    tag = re.sub(r'\s*data-hidden="1"', "", tag)
    return tag


def _inject_hide_css(html: str) -> str:
    if HIDE_SENTINEL in html:
        return html
    idx = html.find("</style>")
    if idx < 0:
        log("WARN: no </style> found — hidden pages rely on class swap only")
        return html
    return html[:idx] + "\n  " + HIDE_CSS + "\n  " + html[idx:]


def main() -> int:
    ap = argparse.ArgumentParser(prog="deck-splice/hide")
    ap.add_argument("--spec", required=True, help="spec JSON path, or '-' for stdin")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text(encoding="utf-8")
    spec = json.loads(raw)
    for k in ("action", "target_deck_id", "slide_keys"):
        if k not in spec:
            sys.exit(f"spec: missing '{k}'")
    action = spec["action"]
    if action not in ("hide", "unhide"):
        sys.exit(f"spec: action must be hide|unhide, got {action!r}")
    deck_id = spec["target_deck_id"]
    want = list(dict.fromkeys(spec["slide_keys"]))
    if not want:
        sys.exit("spec: slide_keys is empty")

    target_dir = _resolve_dir(deck_id)
    index_path = target_dir / "index.html"
    if not index_path.is_file():
        sys.exit(f"target deck not found: {index_path}")
    html = index_path.read_text(encoding="utf-8")
    is_rolling = '<main class="deck" id="deck">' in html
    is_feishu = feishu_ops.is_feishu_deck(html)
    if not (is_rolling or is_feishu):
        sys.exit("target is neither a rolling-deck nor a feishu-deck-h5 deck; "
                 "hide unsupported for this pack")

    # Unified [{key, start, end}] over the element we flip — <section> for
    # rolling, <div class="slide-frame"> for feishu. Both finders include
    # already-hidden items so unhide can locate them.
    if is_rolling:
        sections = find_all_sections(html)
    else:
        sections = [{"key": f["key"], "start": f["frame_start"],
                     "end": f["frame_end"]} for f in feishu_ops.find_frames(html)]
    by_key = {s["key"]: s for s in sections}
    missing = [k for k in want if k not in by_key]
    if missing:
        sys.exit(f"slide_keys not found in deck: {', '.join(missing)}")

    if action == "hide" and sections[0]["key"] in want:
        sys.exit(f"refusing to hide the cover page (first slide "
                 f"'{sections[0]['key']}')")

    # State check: only flip slides that are in the opposite state.
    actionable = []
    for k in want:
        _, _, tag = _open_tag(html, by_key[k])
        is_hidden = _is_hidden_tag(tag)
        if action == "hide" and not is_hidden:
            actionable.append(k)
        elif action == "unhide" and is_hidden:
            actionable.append(k)
    if not actionable:
        log(f"nothing to {action}: all requested slides already in target state")
        return 0

    log(f"target: {deck_id} ({len(sections)} pages) · {action} "
        f"{len(actionable)} slide(s): {', '.join(actionable)}")

    # 1. snapshot
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = index_path.with_suffix(f".html.bak-hide-{ts}")
    shutil.copy2(index_path, backup)
    log(f"snapshot: {backup.name}")

    # 2. flip open tags, back-to-front so offsets stay valid
    if is_rolling:
        flip = _flip_to_hidden if action == "hide" else _flip_to_visible
    else:
        flip = lambda tag: feishu_ops.flip_frame_open_tag(
            tag, hide=(action == "hide"))
    for k in sorted(actionable, key=lambda k: by_key[k]["start"], reverse=True):
        s, e, tag = _open_tag(html, by_key[k])
        html = html[:s] + flip(tag) + html[e:]

    if action == "hide":
        html = _inject_hide_css(html) if is_rolling else feishu_ops.inject_hide_css(html)
    html = (insert.renumber_screen_labels(html) if is_rolling
            else feishu_ops.renumber_labels(html))
    index_path.write_text(html, encoding="utf-8")
    log(f"slides flipped to {'hidden' if action == 'hide' else 'visible'} · "
        f"labels renumbered")

    # 3. rebuild deck.json — hidden slides STAY in it, flagged hidden:true, so
    #    they remain in the deck + the admin list (just display:none in the
    #    presentation).
    deck = (insert.build_deckjson.build(index_path) if is_rolling
            else feishu_ops.build_deckjson(index_path))
    (target_dir / "deck.json").write_text(
        json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    n_hidden = sum(1 for s in deck["slides"] if s.get("hidden"))
    log(f"deck.json rebuilt: {len(deck['slides'])} slides ({n_hidden} hidden)")

    # 4. re-ingest — sets each row's hidden flag from deck.json. No pruning:
    #    hidden pages stay in the DB (and thus the admin list), thumbnails
    #    intact (we never deleted them).
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "library" / "db" / "ingest_deck.py"),
         deck_id, str(target_dir / "deck.json")]).returncode
    if rc != 0:
        log("ingest failed — restoring snapshot")
        shutil.copy2(backup, index_path)
        return 1

    # 6. verify (rolling-only — verify.sh checks <section class="slide"> + splice
    #    markers, which don't exist in feishu's div structure)
    if is_rolling:
        rc = subprocess.run(["bash", str(ASSETS_DIR / "verify.sh"), str(target_dir)]).returncode
        if rc != 0:
            log("WARNING: verify.sh reported problems — inspect the deck")
            return 1

    log(f"done: {action} {len(actionable)} slide(s) in {deck_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
