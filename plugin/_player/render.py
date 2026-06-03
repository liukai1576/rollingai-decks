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
import re
import subprocess
import sys
from pathlib import Path

# Where layout packs live, relative to this file.
SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
DEFAULT_PACK = "feishu-deck-h5"

# pack_id is consumed from deck.json's `deck.layout_pack`. We treat that as
# untrusted (deck.json can come from any source — Keynote, hand-edit, LLM
# output, third-party pipeline). Restricting to a tight allowlist defangs
# `"layout_pack": "../../../etc/x"` and similar.
_PACK_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

# How long a pack's render is allowed to run before we kill it. Generous
# enough for big decks (500 slides) but bounded so a hung / interactive pack
# doesn't hang the dispatcher forever.
RENDER_TIMEOUT_S = 600


def _validate_pack_id(pack_id: str) -> None:
    if not _PACK_ID_RE.match(pack_id or ""):
        raise ValueError(
            f"Invalid layout_pack id: {pack_id!r}. Must match "
            f"{_PACK_ID_RE.pattern} (no path separators, no traversal)."
        )


def find_pack(pack_id: str) -> tuple[Path, dict]:
    """Return (pack_dir, pack_manifest) or raise."""
    _validate_pack_id(pack_id)

    pack_dir = (SKILLS_DIR / pack_id).resolve()
    # Containment: even with the regex, defense-in-depth.
    try:
        pack_dir.relative_to(SKILLS_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Layout pack '{pack_id}' resolves outside {SKILLS_DIR}/"
        )

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
    try:
        pack_dir, manifest = find_pack(pack_id)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"[player] {e}", file=sys.stderr)
        return 2

    # Resolve render_entry under pack_dir and require containment. Defends
    # against a malicious / typo'd `render_entry: "../../../etc/x"`.
    entry = (pack_dir / manifest["render_entry"]).resolve()
    try:
        entry.relative_to(pack_dir)
    except ValueError:
        print(
            f"[player] render_entry escapes pack dir: {entry} not under "
            f"{pack_dir}",
            file=sys.stderr,
        )
        return 2
    if not entry.is_file():
        print(
            f"render_entry not found for pack '{pack_id}': {entry}",
            file=sys.stderr,
        )
        return 2

    # Safety: snapshot the existing index.html (if any) before letting the
    # pack regenerate it. Many users keep hand-edits inside index.html that
    # the renderer would otherwise blow away — this gives them a known
    # recovery point at output_dir/.render-snapshots/index-YYYYMMDD-HHMMSS.html.
    idx = output_dir / "index.html"
    if idx.is_file():
        import shutil, datetime
        snap_dir = output_dir / ".render-snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        snap = snap_dir / f"index-{ts}.html"
        shutil.copy2(idx, snap)
        # Keep only the latest 10 to avoid unbounded growth.
        snaps = sorted(snap_dir.glob("index-*.html"))
        for old in snaps[:-10]:
            try: old.unlink()
            except OSError: pass
        print(f"[player] snapshotted index.html → {snap.relative_to(output_dir)}",
              file=sys.stderr)

    cmd = [sys.executable, str(entry), str(deck_path), str(output_dir),
           *passthrough]
    print(f"[player] dispatch → pack '{pack_id}' v{manifest.get('version','?')}",
          file=sys.stderr)
    try:
        # stdin=DEVNULL: an interactive pack (input(), getpass(), etc.) would
        # otherwise hang the dispatcher forever waiting for stdin that never
        # comes. With DEVNULL the read returns EOF immediately so the pack
        # either falls back to a default or crashes — both better than hang.
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            timeout=RENDER_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[player] pack '{pack_id}' exceeded {RENDER_TIMEOUT_S}s; killed.",
            file=sys.stderr,
        )
        return 124  # GNU coreutils 'timeout' exit convention
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
