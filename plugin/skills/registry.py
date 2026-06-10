#!/usr/bin/env python3
"""
plugin/skills/registry.py — discover all skills under plugin/skills/<id>/.

For each `SKILL.md`:
  · parse YAML frontmatter (the part between two `---` lines)
  · expose a stable record: name / kind / version / description / triggers /
    invocation / input / output / requires / path / readme_markdown
For each `pack.json` (= layout pack):
  · attach pack manifest to the same skill record

Usage:
    python3 plugin/skills/registry.py            # pretty JSON to stdout
    python3 plugin/skills/registry.py --kind 创建  # filter by kind
    python3 plugin/skills/registry.py --raw      # raw list (no group)

Importable:
    from plugin.skills.registry import list_skills
    skills = list_skills()
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # PyYAML
except ImportError:
    print("registry.py: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

SKILLS_DIR = Path(__file__).resolve().parent
KIND_ORDER = ["构思", "创建", "布局风格", "调整", "管理分析"]
CANONICAL_KINDS = set(KIND_ORDER)


class RegistryError(Exception):
    """Raised on a structural problem the registry must surface (collision,
    missing required field on a layout pack, etc.). Lint-style soft issues
    are warned via stderr, not raised."""


def _warn(msg: str) -> None:
    print(f"registry: WARN {msg}", file=sys.stderr)

# Match a single YAML frontmatter block at the very top of a markdown file.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


def _parse_skill_md(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_markdown). Empty dict if no frontmatter."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        print(f"registry: bad YAML in {path}: {e}", file=sys.stderr)
        return {}, m.group(2)
    if not isinstance(meta, dict):
        return {}, m.group(2)
    return meta, m.group(2)


def _normalise_kind(raw: Any) -> list[str]:
    """`kind` accepts string OR list[str]. Output: list[str]."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(k) for k in raw if k]
    return [str(raw)]


def _first_prose_paragraph(body: str) -> str:
    """Pick the first non-heading paragraph from a markdown body. Falls back
    to empty string. Lets new-style SKILL.mds keep the description in
    markdown rather than YAML."""
    paragraph: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            if paragraph:
                break
            continue
        if s.startswith("#"):
            continue
        paragraph.append(s)
    return " ".join(paragraph).strip()


def _normalise_str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.splitlines() if s.strip()]
    if isinstance(raw, list):
        return [str(s) for s in raw if s]
    return [str(raw)]


def list_skills(strict: bool = True) -> list[dict]:
    """Return one record per skill dir that has a SKILL.md.

    `strict=True` (default) raises RegistryError when it finds:
      · two skills declaring the same `name:`
      · a skill with `produces_layout_pack: true` but no/broken pack.json
      · a pack.json whose `id` disagrees with the directory name

    Non-fatal issues — `kind` values outside the canonical 5, broken
    individual pack.json on a non-layout-pack skill, missing `name:` —
    print a WARN line on stderr and the record is still emitted.
    `strict=False` downgrades the structural errors to WARNs too (used by
    the admin UI / non-CI callers that prefer "show what's there" over
    "halt").
    """
    out: list[dict] = []
    if not SKILLS_DIR.is_dir():
        return out

    name_to_id: dict[str, str] = {}

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        meta, body = _parse_skill_md(skill_md)
        description = (meta.get("description") or "").strip()
        if not description:
            description = _first_prose_paragraph(body)

        # ---- Validation passes ----
        skill_id = skill_dir.name
        name = meta.get("name") or skill_id
        if not meta.get("name"):
            _warn(f"{skill_id}: SKILL.md has no `name:` (using dir id)")

        # Name collision
        if name in name_to_id and name_to_id[name] != skill_id:
            msg = (f"duplicate skill name {name!r} in "
                   f"{name_to_id[name]} AND {skill_id}")
            if strict:
                raise RegistryError(msg)
            _warn(msg)
        name_to_id[name] = skill_id

        # Kind validation against the canonical list
        kinds = _normalise_kind(meta.get("kind"))
        bad_kinds = [k for k in kinds if k not in CANONICAL_KINDS]
        if bad_kinds:
            _warn(f"{skill_id}: kind value(s) {bad_kinds} not in canonical "
                  f"{sorted(CANONICAL_KINDS)} — slot under '其他'")
        if not kinds:
            _warn(f"{skill_id}: no `kind:` declared — slot under '其他'")
        if not (meta.get("author") or "").strip():
            _warn(f"{skill_id}: no `author:` declared in SKILL.md frontmatter")

        # Try-relative-path; fall back to absolute if outside the repo
        # (e.g. when plugin/ is vendored elsewhere — see review note).
        try:
            rel_path = str(skill_md.relative_to(SKILLS_DIR.parent.parent))
        except ValueError:
            rel_path = str(skill_md)

        record: dict[str, Any] = {
            "id":           skill_id,
            "name":         name,
            # Optional human-readable Chinese label. Falls back to `name` so
            # any UI that just reads `display_name` is safe with older skills.
            "display_name": meta.get("display_name") or meta.get("中文名") or name,
            # Optional skill author. Every skill SHOULD declare one — surfaces
            # in the admin UI so it's clear who owns each skill.
            "author":       (meta.get("author") or "").strip(),
            "kind":         kinds,
            "version":      meta.get("version") or "",
            "description":  description,
            "input":        meta.get("input") or "",
            "output":       meta.get("output") or "",
            "triggers":     _normalise_str_list(meta.get("triggers")),
            "invocation":   (meta.get("invocation") or "").strip(),
            "requires":     _normalise_str_list(meta.get("requires")),
            "appends_history":        bool(meta.get("appends_history", False)),
            "reads_history":          bool(meta.get("reads_history", False)),
            "produces_layout_pack":   bool(meta.get("produces_layout_pack", False)),
            "path":         rel_path,
            "body_markdown": body.strip(),
        }

        # Layout pack manifest (if any)
        pack_path = skill_dir / "pack.json"
        pack_required = record["produces_layout_pack"]
        if pack_required and not pack_path.is_file():
            msg = (f"{skill_id}: produces_layout_pack=true but pack.json "
                   f"missing at {pack_path}")
            if strict:
                raise RegistryError(msg)
            _warn(msg)
        if pack_path.is_file():
            try:
                pack = json.loads(pack_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                msg = f"{skill_id}: pack.json is invalid JSON: {e}"
                if strict and pack_required:
                    raise RegistryError(msg)
                _warn(msg)
                pack = None
            if pack is not None:
                record["pack"] = pack
                # pack.id must match dir name (avoids silent mismatches
                # where dispatcher loads by dir but a tool keys by pack.id).
                if pack.get("id") and pack["id"] != skill_id:
                    msg = (f"{skill_id}: pack.json id={pack['id']!r} "
                           f"disagrees with directory name")
                    if strict:
                        raise RegistryError(msg)
                    _warn(msg)
                if "render_entry" not in pack and pack_required:
                    msg = f"{skill_id}: pack.json missing 'render_entry'"
                    if strict:
                        raise RegistryError(msg)
                    _warn(msg)
        out.append(record)
    return out


def group_by_kind(skills: Iterable[dict]) -> dict[str, list[dict]]:
    """Group skills by `kind`. A skill listed under multiple kinds appears in
    each. Kinds are output in `KIND_ORDER`; unknown kinds appended after."""
    groups: dict[str, list[dict]] = {k: [] for k in KIND_ORDER}
    seen_other: list[str] = []
    for s in skills:
        kinds = s.get("kind") or ["其他"]
        for k in kinds:
            if k not in groups:
                groups[k] = []
                if k not in KIND_ORDER and k not in seen_other:
                    seen_other.append(k)
            groups[k].append(s)
    # Drop empty canonical kinds for cleanliness
    return {k: v for k, v in groups.items() if v}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", help="Filter to one kind (e.g. 创建)")
    ap.add_argument("--raw", action="store_true",
                    help="Flat list instead of grouped-by-kind")
    ap.add_argument("--lenient", action="store_true",
                    help="Treat structural problems as warnings, not errors")
    args = ap.parse_args()

    try:
        skills = list_skills(strict=not args.lenient)
    except RegistryError as e:
        print(f"registry: ERROR {e}", file=sys.stderr)
        return 2
    if args.kind:
        skills = [s for s in skills if args.kind in (s.get("kind") or [])]

    if args.raw:
        out: Any = skills
    else:
        out = group_by_kind(skills)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
