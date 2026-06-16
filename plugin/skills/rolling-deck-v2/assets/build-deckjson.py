#!/usr/bin/env python3
"""
build-deckjson.py — synthesize a v2 deck.json from a rolling-deck
index.html.

The rolling-deck pack authors content directly in HTML (template clone &
fill); deck.json is derived, not authored. This script extracts every
outer <section class="slide …" data-slide-key="…"> into a slides[] entry
with layout="raw" and the full section markup in data.html.

Inlined splice content (.src-slide divs from deck-splice) stays inside
its host section's data.html — sections are matched by depth-counted
<section>…</section> pairs, so nested markup never splits a slide.

Usage:
    python3 build-deckjson.py <index.html> [--title "Deck title"] [-o out.json]

Default output: deck.json next to the input index.html.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SECTION_OPEN_RE = re.compile(
    r'<section\b[^>]*class="([^"]*)"[^>]*data-slide-key="([^"]+)"[^>]*>',
    re.DOTALL)
ANY_OPEN_RE = re.compile(r'<section\b', re.IGNORECASE)
ANY_CLOSE_RE = re.compile(r'</section>', re.IGNORECASE)
SCREEN_LABEL_RE = re.compile(r'data-screen-label="(\d+)\s*([^"]*)"')
TITLE_TAG_RE = re.compile(r'<title>([^<]+)</title>')


def _slide_token(classes: str) -> bool:
    return bool(re.search(r'(?<![\w-])slide(?![\w-])', classes))


def extract_sections(html: str) -> list[dict]:
    """Return [{key, classes, block, screen_label, label_title}] for every
    outer <section> whose class list contains the standalone token `slide`."""
    out = []
    for m in SECTION_OPEN_RE.finditer(html):
        classes, key = m.group(1), m.group(2)
        if not _slide_token(classes):
            continue
        # depth-count to the matching </section>
        depth, pos = 1, m.end()
        while depth and pos < len(html):
            o = ANY_OPEN_RE.search(html, pos)
            c = ANY_CLOSE_RE.search(html, pos)
            if not c:
                raise SystemExit(f"unbalanced <section> after slide '{key}'")
            if o and o.start() < c.start():
                depth += 1; pos = o.end()
            else:
                depth -= 1; pos = c.end()
        block = html[m.start():pos]
        sl = SCREEN_LABEL_RE.search(m.group(0))
        out.append({
            "key": key,
            "block": block,
            "screen_label": sl.group(1) if sl else "",
            "label_title": (sl.group(2).strip() if sl else ""),
        })
    return out


def pick_title(block: str, fallback: str) -> str:
    for pat in (r'<h2[^>]*>(.*?)</h2>', r'<h1[^>]*>(.*?)</h1>',
                r'<h3[^>]*>(.*?)</h3>'):
        m = re.search(pat, block, re.DOTALL)
        if m:
            t = re.sub(r'<br[^>]*>', ' / ', m.group(1))
            t = re.sub(r'<[^>]+>', '', t).strip()
            t = re.sub(r'\s+', ' ', t)[:100]
            if t:
                return t
    return fallback


def build(index_path: Path, title: str | None = None) -> dict:
    html = index_path.read_text(encoding="utf-8")
    sections = extract_sections(html)
    if not sections:
        raise SystemExit(f"no <section class=\"slide …\"> found in {index_path}")
    slides = []
    for i, s in enumerate(sections, start=1):
        slides.append({
            "key": s["key"],
            "title": pick_title(s["block"], s["label_title"] or s["key"]),
            "notes": "",
            "layout": "raw",
            "screen_label": s["screen_label"] or f"{i:02d}",
            "data": {"html": s["block"]},
        })
    if not title:
        m = TITLE_TAG_RE.search(html)
        title = m.group(1).strip() if m else index_path.parent.name
    return {
        "version": "2",
        "deck": {
            "title": title,
            "language": "zh-only",
            "mode": "rewrite",
            "layout_pack": "rolling-deck-v2",
        },
        "slides": slides,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="build-deckjson")
    ap.add_argument("index_html", type=Path)
    ap.add_argument("--title", help="Deck title override (default: <title> tag)")
    ap.add_argument("-o", "--out", type=Path,
                    help="Output path (default: deck.json next to index.html)")
    args = ap.parse_args()

    if not args.index_html.is_file():
        sys.exit(f"not found: {args.index_html}")
    deck = build(args.index_html, args.title)
    out = args.out or (args.index_html.parent / "deck.json")
    out.write_text(json.dumps(deck, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"wrote {out}: {len(deck['slides'])} slides", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
