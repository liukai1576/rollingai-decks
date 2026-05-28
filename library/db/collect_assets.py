#!/usr/bin/env python3
"""
collect_assets.py — content-address all media assets in a .key, populate
`assets` + `slide_assets` tables.

For each file in <bundle>/Data/:
  · sha256 the bytes
  · upsert into `assets` (hash, size, ext, filename, first_deck, first_seen)
  · trace which slide(s) reference this file via IWA DataReferenceArchive
    (identifier ↔ filename mapping) → upsert into `slide_assets`

Filtering: by default only assets ≥ MIN_SIZE bytes (skips tiny icons,
which create noise when used as a cross-deck similarity signal). Pass
--min-size 0 to record everything.

Usage:
    python3 collect_assets.py <deck_id> <.key path> [--min-size N]
    python3 collect_assets.py --probe <.key path>       # cross-check vs DB
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from keynote_parser.codec import IWAFile
except ImportError:
    sys.exit("ERROR: pip install keynote-parser")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_fingerprints import _open_key

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"
MIN_SIZE_DEFAULT = 50 * 1024     # 50 KB — skip icons/sprites

EXT_OF_INTEREST = {".png", ".jpg", ".jpeg", ".gif", ".webp",
                   ".mp4", ".mov", ".m4v", ".pdf", ".svg", ".tiff"}


def sha256_file(path_or_bytes) -> tuple[str, int]:
    """Return (hex_digest, size_bytes). Accepts Path or raw bytes."""
    h = hashlib.sha256()
    if isinstance(path_or_bytes, (bytes, bytearray)):
        h.update(path_or_bytes)
        return h.hexdigest(), len(path_or_bytes)
    n = 0
    with open(path_or_bytes, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----- iWork mapping: data_id → file_name + ref by slide ---------------

def _build_data_id_index(zf: zipfile.ZipFile) -> dict[str, str]:
    """Read Index/Metadata.iwa (contains DataReferenceArchive entries) to map
    each data identifier → file_name under Data/. iWork allocates identifiers
    sequentially; this is the mapping our walker uses to record asset_refs."""
    out: dict[str, str] = {}
    names = zf.namelist()
    meta_paths = [n for n in names if n.endswith("Index/Metadata.iwa")]
    if not meta_paths:
        return out
    try:
        meta = IWAFile.from_buffer(zf.read(meta_paths[0])).to_dict()
    except Exception:
        return out
    for ar in meta.get("chunks", [{}])[0].get("archives", []):
        obj = ar.get("objects", [{}])[0] if ar.get("objects") else {}
        # DocumentMetadataArchive has a `datas[]` list, each entry with
        # {identifier, digest, preferredFileName, fileName, ...}.
        for entry in obj.get("datas") or []:
            if not isinstance(entry, dict):
                continue
            ident = entry.get("identifier")
            fn = entry.get("preferredFileName") or entry.get("fileName")
            if ident is not None and fn:
                out[str(ident)] = fn
    return out


def _index_slide_drawables(zf: zipfile.ZipFile) -> tuple[list[str], dict[str, dict]]:
    """Re-parse Document.iwa for visible slide order + index ALL archives.
    Mirror logic in collect_fingerprints.parse_key()."""
    names = zf.namelist()
    all_arch: dict[str, dict] = {}
    for n in names:
        if not n.endswith(".iwa"):
            continue
        try:
            d = IWAFile.from_buffer(zf.read(n)).to_dict()
        except Exception:
            continue
        for ar in d.get("chunks", [{}])[0].get("archives", []):
            aid = str(ar.get("header", {}).get("identifier", ""))
            obj = ar.get("objects", [{}])[0] if ar.get("objects") else {}
            if aid and obj:
                all_arch[aid] = obj

    doc = IWAFile.from_buffer(zf.read("Index/Document.iwa")).to_dict()
    archives = doc.get("chunks", [{}])[0].get("archives", [])
    slide_node_order: list[str] = []
    for ar in archives:
        obj = ar.get("objects", [{}])[0] if ar.get("objects") else {}
        if isinstance(obj.get("slideTree"), dict):
            for entry in obj["slideTree"].get("slides", []):
                slide_node_order.append(str(entry["identifier"]))
            break
    node_to_slide: dict[str, tuple[str, bool]] = {}
    for ar in archives:
        obj = ar.get("objects", [{}])[0] if ar.get("objects") else {}
        if "slide" in obj and "isSkipped" in obj:
            hid = str(ar.get("header", {}).get("identifier", ""))
            node_to_slide[hid] = (
                str(obj["slide"].get("identifier", "")),
                bool(obj.get("isSkipped", False))
            )
    visible_ids = [
        node_to_slide[n][0] for n in slide_node_order
        if n in node_to_slide and not node_to_slide[n][1]
    ]
    return visible_ids, all_arch


def _collect_data_refs_in_drawable(obj: dict, all_archives: dict,
                                   out: dict[str, str], _seen=None) -> None:
    """Recursively walk a drawable subtree, collecting every `data.identifier`
    or `movieData.identifier` / `posterImageData.identifier` reference.
    Result: out[data_id] = role ('image' / 'video' / 'poster')."""
    if _seen is None:
        _seen = set()
    if not isinstance(obj, dict):
        return
    pbtype = obj.get("_pbtype") or ""

    if pbtype == "TSD.ImageArchive":
        data = obj.get("data") or {}
        if isinstance(data, dict) and data.get("identifier"):
            out[str(data["identifier"])] = "image"
    elif pbtype == "TSD.MovieArchive":
        md = obj.get("movieData") or {}
        pid = obj.get("posterImageData") or {}
        if isinstance(md, dict) and md.get("identifier"):
            out[str(md["identifier"])] = "video"
        if isinstance(pid, dict) and pid.get("identifier"):
            out[str(pid["identifier"])] = "poster"

    # Recurse — drawables can contain groups whose children reference
    # other archives. To follow only ONE archive deep we'd miss nested
    # groups, so just recurse the inline dict.
    for v in obj.values():
        if isinstance(v, dict):
            _collect_data_refs_in_drawable(v, all_archives, out, _seen)
        elif isinstance(v, list):
            for vv in v:
                if isinstance(vv, dict):
                    _collect_data_refs_in_drawable(vv, all_archives, out, _seen)


# ----- main per-key processor -----------------------------------------

def _build_zip_name_index(zf: zipfile.ZipFile) -> dict[str, str]:
    """Build a {utf8-name: actual-zip-name} index. Keynote 14.5+ stores
    Chinese filenames as UTF-8 in the zip directory but doesn't set the
    language-encoding flag, so Python decodes them as CP437 (mojibake).
    Recover the real UTF-8 name by re-encoding."""
    idx: dict[str, str] = {}
    for info in zf.infolist():
        nm = info.filename
        if info.flag_bits & 0x800:
            # Flag bit set → already UTF-8
            idx[nm] = nm
        else:
            try:
                fixed = nm.encode("cp437").decode("utf-8")
                idx[fixed] = nm
            except (UnicodeEncodeError, UnicodeDecodeError):
                idx[nm] = nm
    return idx


def process_key(key_path: Path, deck_id: str | None, min_size: int,
                probe_only: bool):
    zf = _open_key(key_path)
    if zf is None:
        sys.exit(f"ERROR: cannot open {key_path}")
    is_dir_bundle = key_path.is_dir()
    data_dir: Path | None = key_path / "Data" if is_dir_bundle else None
    # For single-file zip: build the name index that maps the UTF-8
    # filename (as recorded in Metadata.iwa) to the (possibly mojibaked)
    # name we need to pass to zf.read().
    zip_name_idx: dict[str, str] = {}
    if not is_dir_bundle:
        zip_name_idx = _build_zip_name_index(zf)

    with zf:
        # Map data_id → filename
        id_to_fn = _build_data_id_index(zf)
        # Index slide order + all archives
        visible_ids, all_archives = _index_slide_drawables(zf)

        # For each slide, find which data identifiers it uses
        slide_to_refs: dict[str, dict[str, str]] = {}
        for sid in visible_ids:
            slide_obj = all_archives.get(sid, {})
            refs: dict[str, str] = {}
            for drawable_ref in slide_obj.get("ownedDrawables") or []:
                if not isinstance(drawable_ref, dict):
                    continue
                drawable = all_archives.get(str(drawable_ref.get("identifier", "")))
                if drawable is None:
                    continue
                _collect_data_refs_in_drawable(drawable, all_archives, refs)
            slide_to_refs[sid] = refs

        # Now hash each referenced file
        conn = sqlite3.connect(DB)
        now = now_iso()
        seen_hashes: dict[str, tuple[str, int]] = {}  # data_id → (hash, size)
        n_hashed = 0
        n_skipped_small = 0
        for data_id, fn in id_to_fn.items():
            ext = os.path.splitext(fn)[1].lower()
            if ext not in EXT_OF_INTEREST:
                continue
            # Read bytes
            try:
                if is_dir_bundle:
                    # Same suffix convention applies to directory bundles
                    stem, ext_part = os.path.splitext(fn)
                    candidates = [data_dir / f"{stem}-{data_id}{ext_part}",
                                  data_dir / fn]
                    fp = next((c for c in candidates if c.is_file()), None)
                    if fp is None:
                        continue
                    size = fp.stat().st_size
                    if size < min_size:
                        n_skipped_small += 1
                        continue
                    h, _ = sha256_file(fp)
                else:
                    # single-file zip: file lives at Data/<stem>-<id>.<ext>.
                    # Metadata.iwa stores 'preferredFileName' WITHOUT the
                    # -<id> suffix, but the zip entries always include it.
                    stem, ext_part = os.path.splitext(fn)
                    suffixed = f"Data/{stem}-{data_id}{ext_part}"
                    actual_name = zip_name_idx.get(suffixed)
                    if actual_name is None:
                        # Fallback: try unsuffixed (older formats)
                        actual_name = zip_name_idx.get(f"Data/{fn}")
                    if actual_name is None:
                        continue
                    info = zf.getinfo(actual_name)
                    if info.file_size < min_size:
                        n_skipped_small += 1
                        continue
                    raw = zf.read(actual_name)
                    h, size = sha256_file(raw)
            except Exception as e:
                print(f"  WARN: hash failed for {fn}: {e}", file=sys.stderr)
                continue
            seen_hashes[data_id] = (h, size)
            n_hashed += 1
            if not probe_only:
                conn.execute(
                    "INSERT OR IGNORE INTO assets "
                    "(hash, size_bytes, ext, filename, first_deck, first_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (h, size, ext, fn, deck_id, now)
                )

        print(f"Hashed {n_hashed} assets (skipped {n_skipped_small} "
              f"under {min_size//1024}KB)", file=sys.stderr)

        # Probe mode: just report matches against existing assets
        if probe_only:
            print(f"\n素材重叠查重  ·  {key_path.name}")
            print("=" * 72)
            n_matched_slides = 0
            for page_idx, sid in enumerate(visible_ids, start=1):
                refs = slide_to_refs.get(sid, {})
                # Map each ref's data_id → asset hash (if we hashed it)
                slide_hashes = []
                for data_id, role in refs.items():
                    if data_id in seen_hashes:
                        slide_hashes.append((seen_hashes[data_id], role, data_id))
                if not slide_hashes:
                    continue
                # Look up each hash in DB
                hits = []
                for (h, size), role, data_id in slide_hashes:
                    rows = conn.execute(
                        "SELECT sa.slide_id, s.deck_id, s.page_no, s.title, "
                        "       a.size_bytes, a.filename "
                        "FROM slide_assets sa "
                        "JOIN assets a ON a.hash = sa.asset_hash "
                        "JOIN slides s ON s.id = sa.slide_id "
                        "WHERE sa.asset_hash = ? AND s.deck_id != ?",
                        (h, deck_id or "")
                    ).fetchall()
                    if rows:
                        hits.append((role, size, rows))
                if hits:
                    n_matched_slides += 1
                    print(f"\nnew p{page_idx}")
                    for role, size, rows in hits:
                        for row in rows:
                            print(f"  ↔ {row[1]}/p{row[2]} ({role}, "
                                  f"{size//1024}KB, {row[5]})  {(row[3] or '')[:40]}")
            print(f"\n共 {n_matched_slides} 页发现素材重叠")
        else:
            # write slide_assets links
            n_links = 0
            for sid_iwa in visible_ids:
                refs = slide_to_refs.get(sid_iwa, {})
                # Map IWA slide id to our slide_id (deck_id/slide-NNN format)
                page_idx = visible_ids.index(sid_iwa) + 1
                db_slide_id = f"{deck_id}/slide-{page_idx:03d}"
                for data_id, role in refs.items():
                    if data_id not in seen_hashes:
                        continue
                    h, _ = seen_hashes[data_id]
                    conn.execute(
                        "INSERT OR IGNORE INTO slide_assets "
                        "(slide_id, asset_hash, role, iwa_data_id) "
                        "VALUES (?, ?, ?, ?)",
                        (db_slide_id, h, role, data_id)
                    )
                    n_links += 1
            conn.commit()
            print(f"Linked {n_links} slide↔asset relationships", file=sys.stderr)

        conn.commit()
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck_id", nargs="?", default=None,
                    help="omit when --probe")
    ap.add_argument("key_path", type=Path)
    ap.add_argument("--min-size", type=int, default=MIN_SIZE_DEFAULT,
                    help=f"Skip assets under this size (bytes). "
                         f"Default {MIN_SIZE_DEFAULT//1024}KB.")
    ap.add_argument("--probe", action="store_true",
                    help="Don't write — just report matches vs existing")
    args = ap.parse_args()
    if not args.key_path.exists():
        sys.exit(f"ERROR: not found: {args.key_path}")
    if not args.probe and not args.deck_id:
        sys.exit("ERROR: deck_id required when not in probe mode")
    process_key(args.key_path, args.deck_id, args.min_size, args.probe)


if __name__ == "__main__":
    main()
