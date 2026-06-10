"""Shared deck-mount discovery.

Both the admin server (which serves rendered deck files to the preview
iframe) and gen_thumbnails (which drives Chrome through the rendered
HTML) need to know "where does deck_id X live on disk?". Both used to
hold a hand-edited dict; every new client added another line in two
files. This module discovers mounts dynamically by scanning `imports/`.

Conventions:
  - A deck is anything under `<repo>/imports/<deck_id>/render-output-full/`
    that has an `index.html`. The directory name IS the deck_id.
  - Optional override: `<repo>/imports/.deck-mounts.json` (gitignored
    because imports/ itself is gitignored) — a JSON `{deck_id: dir_name}`
    map for legacy aliases where the DB's deck_id doesn't match the
    directory name (e.g. `"kangshifu": "RollingAI分享"`).

The function is pure read-only — caller decides what to do with the
result.
"""
from __future__ import annotations
import json
from pathlib import Path

_ALIAS_FILE = ".deck-mounts.json"


def discover_mounts(repo: Path) -> dict[str, Path]:
    """Return {deck_id: render_dir} for every importable deck under
    `<repo>/imports/`. A deck counts as importable if its
    `render-output-full/index.html` exists.

    Legacy aliases from `<repo>/imports/.deck-mounts.json` (if present)
    are merged in on top of the auto-discovered set.
    """
    mounts: dict[str, Path] = {}
    imports = repo / "imports"
    if imports.is_dir():
        for sub in sorted(imports.iterdir()):
            if not sub.is_dir():
                continue
            render = sub / "render-output-full"
            if (render / "index.html").is_file():
                mounts[sub.name] = render
    # Optional aliases for DB deck_ids that don't match a directory name.
    alias_path = imports / _ALIAS_FILE
    if alias_path.is_file():
        try:
            aliases = json.loads(alias_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"{alias_path}: invalid JSON ({exc}). "
                "Expected: {\"deck_id\": \"dir_name\", ...}"
            ) from exc
        for deck_id, dir_name in aliases.items():
            render = imports / dir_name / "render-output-full"
            if (render / "index.html").is_file():
                mounts[deck_id] = render
    return mounts
