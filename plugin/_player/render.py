#!/usr/bin/env python3
"""
plugin/_player/render.py — Render a deck.json into an output directory.

Reads `deck.layout_pack` from deck.json, locates the matching pack under
`plugin/skills/<id>/pack.json`, and invokes that pack's `render_entry`
script with `<deck.json> <output_dir>` plus any pass-through args.

This is the dispatcher. Each layout pack owns the actual rendering.

Usage:
    python3 plugin/_player/render.py <deck.json> <output_dir> [...pack args]

So importer skills (keynote-to-html, etc.) don't bake-in a specific pack —
they emit deck.json and call this. Switching the pack is a one-line edit
to deck.json + a re-run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Where layout packs live, relative to this file.
SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
DEFAULT_PACK = "rolling-deck-h5"


def find_pack(pack_id: str) -> tuple[Path, dict]:
    """Return (pack_dir, pack_manifest) or raise."""
    pack_dir = SKILLS_DIR / pack_id
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Layout pack '{pack_id}' has no pack.json at {manifest_path}. "
            f"Looked under {SKILLS_DIR}/."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"pack.json for '{pack_id}' is invalid JSON: {e}")
    if "render_entry" not in manifest:
        raise RuntimeError(
            f"pack.json for '{pack_id}' has no 'render_entry'. "
            f"See plugin/_player/README.md."
        )
    return pack_dir, manifest


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: render.py <deck.json> <output_dir> [...pack args]",
            file=sys.stderr,
        )
        return 2
    deck_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    passthrough = sys.argv[3:]

    if not deck_path.is_file():
        print(f"deck.json not found: {deck_path}", file=sys.stderr)
        return 2

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    pack_id = (deck.get("deck", {}) or {}).get("layout_pack") or DEFAULT_PACK
    pack_dir, manifest = find_pack(pack_id)

    entry = pack_dir / manifest["render_entry"]
    if not entry.is_file():
        print(
            f"render_entry not found for pack '{pack_id}': {entry}",
            file=sys.stderr,
        )
        return 2

    cmd = [sys.executable, str(entry), str(deck_path), str(output_dir),
           *passthrough]
    print(f"[player] dispatch → pack '{pack_id}' v{manifest.get('version','?')}",
          file=sys.stderr)
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
