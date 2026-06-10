#!/usr/bin/env python3
"""
plugin/skills/rolling-deck/render.py — render a deck.json into an
output directory using the rolling-deck single-file template.

Contract (matches plugin/_player/render.py dispatch shape):
    python3 render.py <deck.json> <output_dir>

deck.json is expected to have:
    {
      "version": "2",
      "deck": { "title": "...", "layout_pack": "rolling-deck", ... },
      "slides": [
        {
          "key": "cover-hero",
          "title": "...",
          "layout": "raw",
          "screen_label": "01",
          "data": { "html": "<section class=\"slide ...\">...</section>" }
        },
        ...
      ]
    }

Output:
    <output_dir>/index.html      — assembled single-file HTML
    <output_dir>/assets/         — logos + any pack-shipped images
                                   (DOES NOT overwrite an existing
                                   assets/ — caller's per-deck images
                                   take precedence)

The template's design system + JS engine come from pack.json's
assets/template.html. We splice in:
    · the deck title into <title>
    · brand-rail (left logo always RollingAI; right logo = the client
      logo if deck.deck.client_logo points to one, else the deck-label
      text)
    · the slides[] sections, in order, replacing the template's sample
      slides between <main class="deck"> and </main>
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent
# v1.5: template.html lives at the skill root (was assets/template.html in
# v1.4 and earlier). The new layout matches ganyifan's directory-form
# template — script tags inside the template reference `assets/vendor/...`,
# `assets/thumbs/...` etc., so the template must sit ABOVE its assets dir.
TEMPLATE = PACK_DIR / "template.html"
ASSETS_SRC = PACK_DIR / "assets"


def _splice(template: str, marker_open: str, marker_close: str, new_inner: str) -> str:
    """Replace everything between `marker_open` … `marker_close` (inclusive
    of those literal anchor substrings? NO — exclusive: we keep the anchors
    and replace only what's between). If anchors not found, the template is
    returned unchanged and a warning is emitted to stderr."""
    open_i = template.find(marker_open)
    close_i = template.find(marker_close, open_i + 1 if open_i >= 0 else 0)
    if open_i < 0 or close_i < 0:
        print(
            f"render.py: anchor not found ({marker_open!r} / {marker_close!r}); "
            f"template not patched",
            file=sys.stderr,
        )
        return template
    return (template[: open_i + len(marker_open)]
            + new_inner
            + template[close_i:])


def _build_brand_rail(deck_meta: dict) -> str:
    """Build the .brand-rail block. Both logos sit flush left at equal
    height with a thin vertical separator between them — the layout the
    user picked over the original "logo-left, label-right" split.

    deck_meta may carry:
        client_logo: "assets/<file>"   (optional; default = no client logo)
        client_label: "..."             (alt text on the client logo image)
    """
    client_logo = deck_meta.get("client_logo")
    client_label = deck_meta.get("client_label", deck_meta.get("title", ""))
    parts = [
        '      <div class="brand-rail">\n',
        '        <img class="rolling-logo" src="assets/rolling-ai-logo.svg" alt="Rolling AI">\n',
    ]
    if client_logo:
        parts.append('        <span class="brand-sep" aria-hidden="true"></span>\n')
        parts.append(
            f'        <img class="client-logo" src="{client_logo}" alt="{client_label}">\n'
        )
    parts.append('      </div>\n')
    return "".join(parts)


def render(deck_path: Path, output_dir: Path) -> None:
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    version = str(deck.get("version", ""))
    if version not in ("2",):
        sys.exit(
            f"render.py: unsupported deck.json version {version!r} "
            f"(expected '2'). See plugin/_spec/deck-json-v2.md."
        )

    deck_meta = deck.get("deck", {}) or {}
    slides = deck.get("slides", [])
    if not slides:
        sys.exit("render.py: deck.json has no slides")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy pack assets in (logos, fonts, etc). Do not overwrite an existing
    # assets/<file> — the caller's per-deck image takes precedence.
    out_assets = output_dir / "assets"
    out_assets.mkdir(exist_ok=True)
    for src in ASSETS_SRC.iterdir():
        # template.html no longer lives under assets/ (v1.5+); kept as a
        # defensive skip in case anyone reverts the structure.
        if src.name == "template.html":
            continue
        dst = out_assets / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

    template = TEMPLATE.read_text(encoding="utf-8")

    # 1. Patch <title>
    title = deck_meta.get("title", "Rolling Deck")
    template = re.sub(
        r"<title>[^<]*</title>",
        f"<title>{title}</title>",
        template,
        count=1,
    )

    # 2. Assemble the deck body: brand-rail + all sections.
    # We splice between `<main class="deck" id="deck">` and `</main>`.
    body_inner = ["\n", _build_brand_rail(deck_meta)]
    for s in slides:
        if s.get("layout") != "raw":
            print(
                f"render.py: slide {s.get('key')!r} has layout={s.get('layout')!r}, "
                f"only 'raw' is supported in this pack; falling back to data.html",
                file=sys.stderr,
            )
        html = (s.get("data") or {}).get("html", "")
        body_inner.append("\n      ")
        body_inner.append(html)
        body_inner.append("\n")

    template = _splice(
        template,
        '<main class="deck" id="deck">',
        '</main>',
        "".join(body_inner),
    )

    out_html = output_dir / "index.html"
    out_html.write_text(template, encoding="utf-8")
    print(f"render.py: wrote {out_html}  ({len(slides)} slides)", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(prog="rolling-deck/render.py")
    ap.add_argument("deck_json", type=Path)
    ap.add_argument("output_dir", type=Path)
    args = ap.parse_args()

    if not args.deck_json.is_file():
        print(f"deck.json not found: {args.deck_json}", file=sys.stderr)
        return 2
    render(args.deck_json, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
