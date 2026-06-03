#!/usr/bin/env python3
"""
slim-deck · slim.py

Take a deck project directory, slim it to the minimum shippable bytes.
See ../SKILL.md for the design.

Usage:
    python3 slim.py <project-dir> [--dry-run] [--keep-source] [--keep-media]

‼ IMPORTANT — DO NOT re-render after slim.
slim edits index.html in place via str.replace on path strings. It
does NOT need (and must not trigger) a render.py call to "sync"
index.html from deck.json. The user's workflow treats index.html as
the source of truth — re-rendering would destroy any hand-edits not
mirrored in deck.json. slim's responsibility ends at "every byte on
disk is reachable from index.html (and deck.json) without going
outside the deck dir."
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

# --- Configuration --------------------------------------------------------

REF_ATTR_RE = re.compile(
    r'(?:src|href|poster|data-src)\s*=\s*["\']([^"\']+)["\']'
)

# At the project root, these are recognized "external sources" — present
# only because of the build pipeline / authoring workflow; not needed at
# runtime once the deck is self-contained.
EXTERNAL_SOURCE_DIRS = ("media",)
EXTERNAL_SOURCE_FILES_GLOB = ("source.pdf", "phone-*.png", "phone-*.jpg")

# Inside render-output-full/, these are byproducts that the rendered deck
# never references.
INSIDE_TRASH = (".cache", "extract.tsv", "deck.json.bak")


# --- Helpers --------------------------------------------------------------

def _bytes_human(n: int) -> str:
    """Pretty-print byte count: 1.4 GB / 882 MB / 12 KB."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def _collect_refs(html: str) -> set[str]:
    refs: set[str] = set()
    for m in REF_ATTR_RE.finditer(html):
        url = m.group(1).strip().split("?", 1)[0].split("#", 1)[0]
        if not url:
            continue
        if url.startswith((
            "http://", "https://", "data:", "blob:",
            "javascript:", "mailto:", "#",
        )):
            continue
        refs.add(url)
    return refs


def _slide_html_bodies(deck_json: dict) -> list[tuple[str, str]]:
    """Return [(slide_key, html_body), ...] from a deck.json."""
    out = []
    for s in deck_json.get("slides", []):
        body = (s.get("data") or {}).get("html", "")
        out.append((s.get("key", "?"), body))
    return out


def _file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- The five steps -------------------------------------------------------

def step1_absorb_external(deck_dir: Path, project_root: Path,
                          dry_run: bool) -> tuple[int, list[str]]:
    """For every ref in deck.json + index.html that escapes deck_dir,
    pull the file in (assets/_shared/) and rewrite the ref.

    Returns (n_files_pulled_in, list_of_warnings_for_unresolved_refs).
    """
    import json
    deck_path = deck_dir / "deck.json"
    if not deck_path.is_file():
        return 0, [f"deck.json not found at {deck_path}"]
    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    shared = deck_dir / "assets" / "_shared"
    warnings: list[str] = []
    rewrites: dict[str, str] = {}  # old url → new url (relative to deck_dir)
    pulled = 0

    # Gather all unique refs across slide bodies + index.html
    all_refs: set[str] = set()
    for _, html in _slide_html_bodies(deck):
        all_refs |= _collect_refs(html)
    idx = deck_dir / "index.html"
    if idx.is_file():
        all_refs |= _collect_refs(idx.read_text(encoding="utf-8", errors="ignore"))

    for ref in all_refs:
        # Resolve relative to deck_dir.
        # Anything not starting with `../`, `/` or `..` AND that resolves
        # to inside deck_dir is already self-contained.
        target = (deck_dir / ref).resolve()
        try:
            target.relative_to(deck_dir.resolve())
            continue  # already inside deck_dir — no absorption needed
        except ValueError:
            pass
        # Outside deck_dir. Try to resolve.
        # Also try relative to project_root (covers `../media/...`).
        candidates = [
            (deck_dir / ref).resolve(),
            (project_root / ref).resolve(),
            (project_root / ref.lstrip("./")).resolve(),
        ]
        # Deduplicate while preserving order
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]
        src = next((c for c in candidates if c.is_file()), None)
        if src is None:
            warnings.append(f"unresolved external ref: {ref}")
            continue
        # Absorb. New name = basename; if collision, add a short hash.
        dst = shared / src.name
        if dst.exists() and dst.stat().st_size != src.stat().st_size:
            digest = _file_sha256(src)[:8]
            dst = shared / f"{src.stem}-{digest}{src.suffix}"
        if not dst.exists():
            if not dry_run:
                shared.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            pulled += 1
        rewrites[ref] = f"assets/_shared/{dst.name}"

    if rewrites and not dry_run:
        # Apply to deck.json slide bodies + index.html
        def _apply(text: str) -> str:
            for old, new in rewrites.items():
                text = text.replace(old, new)
            return text

        for s in deck.get("slides", []):
            body = (s.get("data") or {}).get("html", "")
            new = _apply(body)
            if new != body:
                s["data"]["html"] = new
        deck_path.write_text(
            json.dumps(deck, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if idx.is_file():
            idx.write_text(_apply(idx.read_text(encoding="utf-8", errors="ignore")),
                           encoding="utf-8")

        # Also rewrite the source redesign HTMLs at `<project_root>/redesigns/`
        # so a later `slide-redesign apply` doesn't re-introduce the same
        # external refs and break the deck again. This is the difference
        # between slim being a one-shot post-process vs the canonical state.
        redesigns_dir = project_root / "redesigns"
        if redesigns_dir.is_dir():
            for rf in redesigns_dir.glob("*.html"):
                txt = rf.read_text(encoding="utf-8", errors="ignore")
                new = _apply(txt)
                if new != txt:
                    rf.write_text(new, encoding="utf-8")

    return pulled, warnings


def step2_orphan_sweep(deck_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Delete files under assets/ not referenced by any slide HTML or
    index.html. Returns (n_deleted, bytes_freed)."""
    import json
    deck_path = deck_dir / "deck.json"
    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    referenced: set[str] = set()
    for _, html in _slide_html_bodies(deck):
        referenced |= {os.path.normpath(r) for r in _collect_refs(html)}
    idx = deck_dir / "index.html"
    if idx.is_file():
        referenced |= {
            os.path.normpath(r)
            for r in _collect_refs(idx.read_text(encoding="utf-8", errors="ignore"))
        }

    assets = deck_dir / "assets"
    if not assets.is_dir():
        return 0, 0
    deleted = 0
    freed = 0
    for p in assets.rglob("*"):
        if not p.is_file():
            continue
        rel = os.path.normpath(str(p.relative_to(deck_dir)))
        if rel in referenced:
            continue
        try:
            sz = p.stat().st_size
            if not dry_run:
                p.unlink()
            deleted += 1
            freed += sz
        except OSError:
            pass
    # Prune now-empty slide dirs
    if not dry_run:
        for d in sorted(assets.iterdir(), reverse=True):
            if d.is_dir() and d.name != "_shared":
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except OSError:
                    pass
    return deleted, freed


def step3_dedup(deck_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Hash every remaining file under assets/. For each group with two
    or more identical files, keep one in assets/_shared/<basename> and
    rewrite refs. Returns (n_files_collapsed, bytes_freed)."""
    import json
    assets = deck_dir / "assets"
    if not assets.is_dir():
        return 0, 0

    by_hash: dict[str, list[Path]] = {}
    for p in assets.rglob("*"):
        if not p.is_file() or p.parent == assets:
            continue  # skip files directly in assets/ root
        by_hash.setdefault(_file_sha256(p), []).append(p)

    shared = assets / "_shared"
    rewrites: dict[str, str] = {}
    collapsed = 0
    freed = 0
    for digest, paths in by_hash.items():
        if len(paths) < 2:
            continue
        canonical_name = paths[0].name
        target = shared / canonical_name
        # Collision check (same basename, different content)
        if target.exists() and _file_sha256(target) != digest:
            target = shared / f"{paths[0].stem}-{digest[:8]}{paths[0].suffix}"

        new_rel = f"assets/_shared/{target.name}"
        for i, p in enumerate(paths):
            old_rel = str(p.relative_to(deck_dir))
            rewrites[os.path.normpath(old_rel)] = new_rel
            if i == 0:
                if not dry_run:
                    shared.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        shutil.move(str(p), str(target))
                    else:
                        p.unlink()
                # First copy: doesn't free space (it moves to shared/).
            else:
                sz = p.stat().st_size
                if not dry_run:
                    p.unlink()
                freed += sz
            collapsed += 1

    if rewrites and not dry_run:
        deck_path = deck_dir / "deck.json"
        deck = json.loads(deck_path.read_text(encoding="utf-8"))

        def _apply(text: str) -> str:
            for old, new in rewrites.items():
                text = text.replace(old, new)
            return text

        for s in deck.get("slides", []):
            body = (s.get("data") or {}).get("html", "")
            s["data"]["html"] = _apply(body)
        deck_path.write_text(
            json.dumps(deck, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        idx = deck_dir / "index.html"
        if idx.is_file():
            idx.write_text(_apply(idx.read_text(encoding="utf-8", errors="ignore")),
                           encoding="utf-8")
    return collapsed, freed


def step4_inside_trash(deck_dir: Path, dry_run: bool) -> tuple[int, int]:
    """Drop .cache/, extract.tsv, deck.json.bak. Returns (n, bytes_freed)."""
    deleted = 0
    freed = 0
    for name in INSIDE_TRASH:
        p = deck_dir / name
        if not p.exists():
            continue
        sz = _dir_size(p)
        if not dry_run:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        deleted += 1
        freed += sz
    return deleted, freed


def step5_external_sources(project_root: Path, deck_dir: Path,
                           dry_run: bool, keep_source: bool,
                           keep_media: bool) -> tuple[int, int, list[str]]:
    """At project root (parent of deck_dir), drop external source
    materials no longer needed at runtime: source.pdf, media/, phone-*.png.

    Returns (n_paths_removed, bytes_freed, warnings)."""
    # Safety: only delete project-level stuff if deck looks self-contained.
    # An external ref that didn't get absorbed in step 1 means we'd break
    # the deck. Re-scan for any remaining external refs.
    import json
    deck = json.loads((deck_dir / "deck.json").read_text(encoding="utf-8"))
    leftover_external: set[str] = set()
    all_refs: set[str] = set()
    for _, html in _slide_html_bodies(deck):
        all_refs |= _collect_refs(html)
    idx = deck_dir / "index.html"
    if idx.is_file():
        all_refs |= _collect_refs(idx.read_text(encoding="utf-8", errors="ignore"))
    for ref in all_refs:
        target = (deck_dir / ref).resolve()
        try:
            target.relative_to(deck_dir.resolve())
        except ValueError:
            leftover_external.add(ref)
    if leftover_external:
        return 0, 0, [
            f"refused to delete external sources — "
            f"{len(leftover_external)} ref(s) still escape the deck dir: "
            f"{sorted(leftover_external)[:3]}"
        ]

    deleted = 0
    freed = 0
    for name in EXTERNAL_SOURCE_DIRS:
        if keep_media and name == "media":
            continue
        p = project_root / name
        if not p.exists():
            continue
        sz = _dir_size(p)
        if not dry_run:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        deleted += 1
        freed += sz
    for pattern in EXTERNAL_SOURCE_FILES_GLOB:
        if keep_source and pattern == "source.pdf":
            continue
        for p in project_root.glob(pattern):
            sz = _dir_size(p)
            if not dry_run:
                p.unlink()
            deleted += 1
            freed += sz
    return deleted, freed, []


# --- Entry ----------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Slim a deck project directory to minimum shippable bytes."
    )
    ap.add_argument("project_dir", type=Path,
                    help="The deck project root (contains render-output-full/, "
                         "optionally media/, source.pdf, redesigns/, etc.)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan and savings, change nothing.")
    ap.add_argument("--keep-source", action="store_true",
                    help="Keep source.pdf at the project root.")
    ap.add_argument("--keep-media", action="store_true",
                    help="Keep media/ at the project root.")
    args = ap.parse_args()

    project_root = args.project_dir.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1

    deck_dir = project_root / "render-output-full"
    if not deck_dir.is_dir():
        print(f"ERROR: render-output-full/ not found under {project_root}",
              file=sys.stderr)
        return 1

    print(f"slim-deck · {project_root.name}")
    if args.dry_run:
        print("  ** DRY RUN — nothing will be deleted **")

    before_project = _dir_size(project_root)
    before_deck = _dir_size(deck_dir)
    print(f"  before:  project {_bytes_human(before_project)}  ·  "
          f"deck {_bytes_human(before_deck)}")
    print()

    # Step 1
    pulled, warns = step1_absorb_external(deck_dir, project_root, args.dry_run)
    print(f"  step 1  ·  absorb external refs  →  {pulled} file(s) pulled into assets/_shared/")
    for w in warns:
        print(f"          ⚠ {w}")

    # Step 2
    n_orph, freed_orph = step2_orphan_sweep(deck_dir, args.dry_run)
    print(f"  step 2  ·  orphan sweep          →  {n_orph} file(s), freed {_bytes_human(freed_orph)}")

    # Step 3
    n_dup, freed_dup = step3_dedup(deck_dir, args.dry_run)
    print(f"  step 3  ·  cross-slide dedup     →  {n_dup} file(s) collapsed, freed {_bytes_human(freed_dup)}")

    # Step 4
    n_trash, freed_trash = step4_inside_trash(deck_dir, args.dry_run)
    print(f"  step 4  ·  build artifacts       →  {n_trash} item(s), freed {_bytes_human(freed_trash)}")

    # Step 5
    n_ext, freed_ext, ext_warns = step5_external_sources(
        project_root, deck_dir, args.dry_run, args.keep_source, args.keep_media,
    )
    if ext_warns:
        for w in ext_warns:
            print(f"  step 5  ·  external sources      →  SKIPPED: {w}")
    else:
        print(f"  step 5  ·  external sources      →  {n_ext} item(s), freed {_bytes_human(freed_ext)}")

    print()
    after_project = _dir_size(project_root)
    after_deck = _dir_size(deck_dir)
    saved_total = before_project - after_project
    print(f"  after:   project {_bytes_human(after_project)}  ·  "
          f"deck {_bytes_human(after_deck)}")
    print(f"  saved:   {_bytes_human(saved_total)} "
          f"({saved_total * 100 / before_project:.0f}% of project)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
