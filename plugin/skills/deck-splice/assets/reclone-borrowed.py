#!/usr/bin/env python3
"""
reclone-borrowed.py — reclaim disk by re-cloning existing borrowed assets.

Decks spliced before the APFS-clone change carry REAL copies under
assets/_borrowed/<source_deck>/…. This tool walks every mounted deck,
and for each borrowed file whose original still exists with identical
content, replaces the copy with an APFS clone (`cp -c`). Byte-identical
result, same self-containment, shared storage.

Safe by construction: the clone replaces the copy only after a size +
hash match against the source; non-matching files are left untouched.

Usage:
    python3 reclone-borrowed.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ASSETS_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT / "library" / "db"))
from deck_mounts import discover_mounts  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(prog="reclone-borrowed")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mounts = discover_mounts(REPO_ROOT)
    recloned = skipped_missing = skipped_diff = 0
    bytes_shared = 0

    for deck_id, mount in sorted(mounts.items()):
        borrowed = mount / "assets" / "_borrowed"
        if not borrowed.is_dir():
            continue
        for src_deck_dir in sorted(borrowed.iterdir()):
            if not src_deck_dir.is_dir():
                continue
            src_mount = mounts.get(src_deck_dir.name)
            if not src_mount:
                print(f"  ? {deck_id}: source deck '{src_deck_dir.name}' "
                      f"not mounted — leaving its copies as-is")
                continue
            for f in src_deck_dir.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(src_deck_dir)
                orig = src_mount / rel
                if not orig.is_file():
                    skipped_missing += 1
                    continue
                if (orig.stat().st_size != f.stat().st_size
                        or sha256(orig) != sha256(f)):
                    skipped_diff += 1
                    continue
                if args.dry_run:
                    print(f"  would reclone: {deck_id} ← {src_deck_dir.name}/{rel} "
                          f"({f.stat().st_size // 1024 // 1024}MB)")
                else:
                    tmp = f.with_suffix(f.suffix + ".reclone-tmp")
                    r = subprocess.run(["cp", "-c", str(orig), str(tmp)],
                                       capture_output=True)
                    if r.returncode != 0:
                        tmp.unlink(missing_ok=True)
                        print(f"  ! clone failed (non-APFS?): {rel} — kept copy")
                        continue
                    tmp.replace(f)
                recloned += 1
                bytes_shared += f.stat().st_size

    verb = "would share" if args.dry_run else "now shared"
    print(f"\n{recloned} file(s) recloned · {bytes_shared // 1024 // 1024}MB "
          f"{verb} with originals · {skipped_missing} originals missing · "
          f"{skipped_diff} content-diverged (kept as real copies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
