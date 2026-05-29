"""
plugin/_lib/history.py — the changelog of a deck output.

Every skill that produces / modifies a deck output directory should call
`history.append(output_dir, skill=..., version=...)` at the end of its run.

The file `<output_dir>/history.json` accumulates one entry per step, in
chronological order. Use it to:
  · See which skills, at which versions, produced this deck.
  · Roll back to "the deck as of step N".
  · Hand a client a provenance record.

JSON shape:
[
  {
    "step":    1,
    "skill":   "keynote-to-html",
    "version": "0.16",
    "at":      "2026-05-29T10:00:00Z",
    "input":   "/Users/.../eCINDI.key",
    "notes":   "scaled 960×540 → 1920×1080"
  },
  ...
]

This is a thin file-append helper — not a database. Concurrent writers
on the same output dir is an out-of-scope problem (each output dir is
single-writer by convention).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_FILENAME = "history.json"


def load(output_dir: Path | str) -> list[dict]:
    """Return the current history list, or [] if no history yet."""
    path = Path(output_dir) / HISTORY_FILENAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def append(
    output_dir: Path | str,
    *,
    skill: str,
    version: str,
    notes: str | None = None,
    **extra: Any,
) -> dict:
    """Append one entry to <output_dir>/history.json. Returns the new entry.

    `skill` and `version` are required so that every record is traceable.
    `notes` and any **extra kwargs (input, changed_slides, …) flow through
    as-is — schema is intentionally open so skills can record whatever is
    useful to them.
    """
    if not skill:
        raise ValueError("history.append: `skill` must be non-empty")
    if not version:
        raise ValueError("history.append: `version` must be non-empty")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / HISTORY_FILENAME

    existing = load(out)
    entry: dict[str, Any] = {
        "step":    len(existing) + 1,
        "skill":   skill,
        "version": version,
        "at":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if notes:
        entry["notes"] = notes
    for k, v in extra.items():
        # don't let extras silently clobber the canonical fields
        if k in entry:
            continue
        entry[k] = v

    existing.append(entry)
    path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return entry
