#!/usr/bin/env python3
"""
feishu_ops.py — slide-level HTML surgery for feishu-deck-h5 decks (Keynote
→ HTML products), the div-based counterpart to insert.py's <section> parser.

A feishu deck's body is:

    <… class="deck" data-layout-pack="feishu-deck-h5">
      <div class="slide-frame">
        <div class="slide" data-screen-label="06" data-slide-key="slide-006">
          <style>…</style> …els…
        </div>
      </div>
      …one slide-frame per slide…
    </…>

The player (feishu-deck.js) enumerates `deck.querySelectorAll('.slide-frame')`,
so navigation + page count key off the FRAME wrapper, not the inner `.slide`
(which carries the key/label and scoped CSS). That drives the conventions
here:

  · hide  = swap the wrapper's class token `slide-frame` → `slide-frame-hidden`
            and add data-hidden="1". querySelectorAll('.slide-frame') no longer
            matches it, so it drops out of nav + count; a one-shot
            `.slide-frame-hidden{display:none}` rule keeps it off-screen. The
            frame never moves, so unhide restores its exact position.
  · delete = cut the whole <div class="slide-frame">…</div> block.
  · deck.json = rebuilt from the VISIBLE frames only (hidden auto-excluded),
            data.html = the inner-of-`.slide` markup (feishu convention — the
            wrapper is reconstructed by the renderer, not stored).

This module is pure HTML/JSON; DB + ingest orchestration stays in
delete.py / hide.py, shared with the rolling path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# A feishu host is marked by the layout-pack attribute on the deck shell.
FEISHU_MARKER = 'data-layout-pack="feishu-deck-h5"'

HIDE_CSS = (".slide-frame-hidden{display:none !important}"
            "  /* hide-slide: hidden pages, see deck-splice/feishu_ops.py */")
HIDE_SENTINEL = "/* hide-slide:"

_DIV_TOKEN_RE = re.compile(r'<div\b|</div>', re.IGNORECASE)
# A slide-frame wrapper, visible or hidden. The class list contains the
# standalone token `slide-frame` (visible) or `slide-frame-hidden` (hidden).
_FRAME_OPEN_RE = re.compile(
    r'<div\b[^>]*\bclass="([^"]*\bslide-frame(?:-hidden)?\b[^"]*)"[^>]*>',
    re.IGNORECASE)
# The inner <div class="slide …"> that carries key + screen label.
_SLIDE_OPEN_RE = re.compile(
    r'<div\b[^>]*\bdata-slide-key="([^"]+)"[^>]*>', re.IGNORECASE)
_SCREEN_LABEL_RE = re.compile(r'data-screen-label="(\d+)(\s*[^"]*)"')


def is_feishu_deck(html: str) -> bool:
    return FEISHU_MARKER in html


def _match_close(html: str, open_end: int) -> int:
    """Given the index just past a `<div …>` open tag, return the index just
    past its matching `</div>` (depth-counted over nested divs)."""
    depth, pos = 1, open_end
    while depth and pos < len(html):
        t = _DIV_TOKEN_RE.search(html, pos)
        if not t:
            raise SystemExit("unbalanced <div> while scanning slide-frame")
        if t.group(0).lower().startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return t.end()
        pos = t.end()
    raise SystemExit("unbalanced <div> while scanning slide-frame")


def find_frames(html: str) -> list[dict]:
    """Every slide-frame (visible AND hidden), in DOM order. Each entry:
        key, hidden, frame_start, frame_end,
        slide_open_start, slide_open_end (the inner <div class="slide …"> tag)
    """
    out: list[dict] = []
    for m in _FRAME_OPEN_RE.finditer(html):
        classes = m.group(1)
        frame_start = m.start()
        frame_end = _match_close(html, m.end())
        block = html[m.end():frame_end]
        sm = _SLIDE_OPEN_RE.search(block)
        if not sm:
            # A frame with no data-slide-key — skip (defensive; shouldn't happen).
            continue
        key = sm.group(1)
        lbl = _SCREEN_LABEL_RE.search(sm.group(0))
        out.append({
            "key": key,
            "hidden": "slide-frame-hidden" in classes,
            "screen_label": lbl.group(1) if lbl else "",
            "frame_start": frame_start,
            "frame_end": frame_end,
            "slide_open_start": m.end() + sm.start(),
            "slide_open_end": m.end() + sm.end(),
        })
    return out


def _slide_inner(html: str, fr: dict) -> str:
    """The inner-of-`.slide` markup (style + els) for one frame — the feishu
    deck.json `data.html` convention (no wrapper divs)."""
    inner_start = fr["slide_open_end"]
    inner_end = _match_close(html, inner_start) - len("</div>")
    return html[inner_start:inner_end].strip("\n")


def renumber_labels(html: str) -> str:
    """Rewrite each VISIBLE slide's data-screen-label numeric prefix to its
    1-based visible position (zero-padded, matching the keynote convention).
    Hidden frames are skipped and don't consume a number."""
    frames = find_frames(html)
    visible = [f for f in frames if not f["hidden"]]
    # Back-to-front so byte offsets stay valid.
    pos = len(visible)
    for f in reversed(visible):
        tag = html[f["slide_open_start"]:f["slide_open_end"]]
        lbl = _SCREEN_LABEL_RE.search(tag)
        if lbl:
            new_tag = (tag[:lbl.start()]
                       + f'data-screen-label="{pos:02d}{lbl.group(2)}"'
                       + tag[lbl.end():])
            html = (html[:f["slide_open_start"]] + new_tag
                    + html[f["slide_open_end"]:])
        pos -= 1
    return html


def build_deckjson(index_path: Path) -> dict:
    """Rebuild a v2 deck.json from the (edited) index.html — ALL frames,
    hidden ones flagged `hidden: true` (they stay in the deck + the admin list,
    just display:none in the presentation). Deck-level meta + per-slide
    title/notes are preserved from the existing deck.json (matched by key) so
    the carefully-extracted Keynote titles survive; data.html + screen_label
    are refreshed from the HTML."""
    html = index_path.read_text(encoding="utf-8")
    frames = find_frames(html)
    if not frames:
        raise SystemExit(f"no slide-frames found in {index_path}")

    prev_by_key: dict[str, dict] = {}
    deck_meta = {"title": index_path.parent.name, "language": "zh-only",
                 "mode": "rewrite", "layout_pack": "feishu-deck-h5"}
    dj_path = index_path.parent / "deck.json"
    if dj_path.is_file():
        try:
            prev = json.loads(dj_path.read_text(encoding="utf-8"))
            deck_meta = prev.get("deck", deck_meta)
            prev_by_key = {s["key"]: s for s in prev.get("slides", [])}
        except (OSError, ValueError, KeyError):
            pass

    slides = []
    for i, fr in enumerate(frames, start=1):
        key = fr["key"]
        tag = html[fr["slide_open_start"]:fr["slide_open_end"]]
        lbl = _SCREEN_LABEL_RE.search(tag)
        prior = prev_by_key.get(key, {})
        slides.append({
            "key": key,
            "title": prior.get("title") or key,
            "notes": prior.get("notes", ""),
            "layout": prior.get("layout", "raw"),
            "hidden": bool(fr["hidden"]),
            "screen_label": (lbl.group(1) if lbl else f"{i:02d}"),
            "data": {"html": _slide_inner(html, fr)},
        })
    return {"version": "2", "deck": deck_meta, "slides": slides}


# ── hide / unhide primitives (frame-level class swap) ───────────────────────

def flip_frame_open_tag(open_tag: str, *, hide: bool) -> str:
    """Swap a slide-frame open tag between visible and hidden state."""
    m = re.search(r'class="([^"]*)"', open_tag)
    classes = m.group(1)
    if hide:
        new = re.sub(r'(?<![\w-])slide-frame(?![\w-])', "slide-frame-hidden",
                     classes, count=1)
        tag = open_tag[:m.start(1)] + new + open_tag[m.end(1):]
        if 'data-hidden="1"' not in tag:
            tag = tag[:-1].rstrip() + ' data-hidden="1">'
        return tag
    new = classes.replace("slide-frame-hidden", "slide-frame")
    tag = open_tag[:m.start(1)] + new + open_tag[m.end(1):]
    return re.sub(r'\s*data-hidden="1"', "", tag)


# ── CLI: rebuild deck.json from an (edited) index.html ──────────────────────
# Mirrors rolling-deck/build-deckjson.py so the admin reingest path can rebuild
# a feishu deck's deck.json from its HTML truth. Usage:
#   python3 feishu_ops.py <index.html> [-o out.json]
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="feishu_ops")
    ap.add_argument("index_html", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    a = ap.parse_args()
    deck = build_deckjson(a.index_html)
    out = a.out or (a.index_html.parent / "deck.json")
    out.write_text(json.dumps(deck, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"deck.json written: {len(deck['slides'])} slides → {out}")


def inject_hide_css(html: str) -> str:
    # Idempotent. Prefer </head> (keynote index.html has one <style> block per
    # slide, so we must NOT land inside a slide's scoped block).
    if HIDE_SENTINEL in html:
        return html
    idx = html.find("</head>")
    if idx < 0:
        idx = html.find("</style>")
    if idx < 0:
        return html
    return html[:idx] + "  <style>" + HIDE_CSS + "</style>\n  " + html[idx:]
