#!/usr/bin/env python3
"""
slide-redesign · apply.py  (v0.1)

Replace targeted slides in a deck.json with hand-authored HTML.

Two ways to target a slide:
  · By PDF page number — file `slide-NN.html` (NN = 1-based position in deck)
  · By slide key       — file `<slide-key>.html` (e.g. `slide-039.html`)

PDF-page format wins for legacy decks from keynote-to-html. Slide-key format
is preferred for new decks (more stable across reorders).

Usage:
  python3 apply.py <input.json> <redesigns-dir> [<output.json>]

If output is omitted, updates in place (with .bak backup).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def load_redesigns(redesigns_dir: Path) -> dict[str, str]:
    """Scan redesigns dir and build {target_key: html_body}.

    Supports two filename conventions:
      slide-NN.html  → target = "pdf:NN"  (e.g. "pdf:24")
      slide-XYZ.html → target = "key:slide-XYZ" if matches \\d+-padded form
    """
    out: dict[str, str] = {}
    if not redesigns_dir.is_dir():
        return out
    pdf_pat = re.compile(r"^slide-(\d{1,3})\.html$")
    key_pat = re.compile(r"^slide-([a-z0-9\-]+)\.html$", re.IGNORECASE)
    for f in sorted(redesigns_dir.glob("slide-*.html")):
        name = f.name
        m = pdf_pat.match(name)
        if m:
            # decide: PDF index or zero-padded slide key?
            n = m.group(1)
            # interpret 1-3 digit forms as PDF index (NN) — slide keys are typically
            # NNN (3 digits zero-padded) in keynote-to-html output. Convention:
            #   slide-24.html  → PDF 24 (1-based) by default
            #   slide-039.html → key slide-039
            # We resolve both at apply time, preferring PDF-index match first.
            if len(n) == 3 and n.startswith("0"):
                out[f"key:slide-{n}"] = f.read_text(encoding="utf-8")
            else:
                out[f"pdf:{int(n)}"] = f.read_text(encoding="utf-8")
            continue
        m = key_pat.match(name)
        if m:
            out[f"key:slide-{m.group(1)}"] = f.read_text(encoding="utf-8")
    return out


def apply_redesigns(deck: dict, redesigns: dict[str, str]) -> tuple[int, list[str]]:
    """Mutate deck['slides'] in place. Returns (n_applied, log_lines)."""
    n_applied = 0
    log: list[str] = []
    slides = deck.get("slides", [])
    for i, slide in enumerate(slides, start=1):
        key = slide.get("key", "")
        # Two targeting options
        html = redesigns.get(f"pdf:{i}") or redesigns.get(f"key:{key}")
        if not html:
            continue
        slide["layout"] = "raw"
        slide.setdefault("data", {})
        slide["data"] = {"html": html}
        slide.setdefault("screen_label", f"{i:02d}")
        n_applied += 1
        which = "pdf" if f"pdf:{i}" in redesigns else "key"
        log.append(f"  pdf-page {i:2d}  ←  REDESIGN (matched by {which})  key={key}")
    return n_applied, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path, help="Path to input deck.json")
    ap.add_argument("redesigns_dir", type=Path, help="Directory with slide-*.html files")
    ap.add_argument("output", type=Path, nargs="?", default=None,
                    help="Optional output path (default: in-place update)")
    args = ap.parse_args()

    if not args.input.is_file():
        sys.exit(f"ERROR: input deck.json not found: {args.input}")
    if not args.redesigns_dir.is_dir():
        sys.exit(f"ERROR: redesigns dir not found: {args.redesigns_dir}")

    redesigns = load_redesigns(args.redesigns_dir)
    if not redesigns:
        print(f"==> no slide-*.html files found in {args.redesigns_dir}")
        return 0
    print(f"==> {len(redesigns)} redesign override(s) loaded from {args.redesigns_dir}")

    deck = json.loads(args.input.read_text(encoding="utf-8"))
    n_applied, log = apply_redesigns(deck, redesigns)

    for line in log:
        print(line)

    # Backup + write
    if args.output is None or args.output.resolve() == args.input.resolve():
        backup = args.input.with_suffix(args.input.suffix + ".bak")
        shutil.copy(args.input, backup)
        out_path = args.input
        print(f"\n==> backup written to {backup.name}")
    else:
        out_path = args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"==> {n_applied} slide(s) replaced; wrote {out_path}")
    if n_applied < len(redesigns):
        print(f"   ⚠ {len(redesigns) - n_applied} redesign file(s) had no matching slide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
