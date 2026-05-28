#!/usr/bin/env python3
"""
collect_fingerprints.py — read a .key file directly (NOT regenerating any
output) and write iwa_uuid + element_sig fingerprints into the slides DB.

Phase A only. We don't change the schema's primary keys, we don't move
any assets, we don't re-render anything. Pure indexing pass.

Two modes:

  1. update existing rows (康师傅 deck — already in DB):
       python3 collect_fingerprints.py kangshifu  "/path/to/.key"
     Matches by page_no within the given deck_id.

  2. probe-only dedup check (new .key — NOT yet imported):
       python3 collect_fingerprints.py --probe "/path/to/new.key"
     Doesn't write anything; reports per-page matches against existing slides.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from keynote_parser.codec import IWAFile
except ImportError:
    sys.exit("ERROR: keynote-parser not installed.  pip install keynote-parser")
import zipfile

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"


# ----- helpers --------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _round(v: float | None, step: int = 10) -> int | None:
    if v is None:
        return None
    return int(round(v / step) * step)


def _open_key(key_path: Path):
    """Return a zipfile.ZipFile if .key is the new single-file format, else
    None (caller falls back to directory mode)."""
    try:
        if zipfile.is_zipfile(key_path):
            return zipfile.ZipFile(key_path, "r")
    except OSError:
        pass
    return None


# ----- IWA → slide records --------------------------------------------------

class SlideFingerprint:
    __slots__ = ("page_no", "iwa_uuid", "element_sig",
                 "element_count", "text_chars", "asset_refs", "raw_elements")

    def __init__(self, page_no: int):
        self.page_no = page_no
        self.iwa_uuid: str | None = None
        self.element_sig: str | None = None
        self.element_count = 0
        self.text_chars = 0
        self.asset_refs: list[str] = []   # data_id_to_filename refs we noticed
        self.raw_elements: list[tuple] = []


def _walk_for_elements(obj, ctx: dict, found: list[tuple]):
    """Extract a fingerprint tuple per drawable archive. The drawable's
    `_pbtype` field identifies the real iWork type:
      TSD.ImageArchive   → image (with data ref)
      TSD.MovieArchive   → video (with movieData + posterImageData refs)
      TSD.ShapeArchive   → shape  (with optional fill, path, text content)
      TSD.GroupArchive   → group  (recurse into children)
      TSWP.StorageArchive → text storage (rich text)
    Geometry usually lives one level deep at  obj["super"]["geometry"].
    """
    if not isinstance(obj, dict):
        return

    pbtype = obj.get("_pbtype") or ""
    super_obj = obj.get("super") if isinstance(obj.get("super"), dict) else {}
    geom = (obj.get("geometry")
            or super_obj.get("geometry")
            or (super_obj.get("super") or {}).get("geometry")
            if isinstance(super_obj, dict) else None)

    # Determine drawable type
    kind = "elem"
    asset_ref: str | None = None

    if pbtype == "TSD.ImageArchive":
        kind = "image"
        data = obj.get("data") or {}
        if isinstance(data, dict) and data.get("identifier"):
            asset_ref = f"img:{data['identifier']}"
    elif pbtype == "TSD.MovieArchive":
        kind = "video"
        md = obj.get("movieData") or {}
        pid = obj.get("posterImageData") or {}
        parts = []
        if isinstance(md, dict) and md.get("identifier"):
            parts.append(f"mov:{md['identifier']}")
        if isinstance(pid, dict) and pid.get("identifier"):
            parts.append(f"poster:{pid['identifier']}")
        if parts:
            asset_ref = "|".join(parts)
    elif pbtype in ("TSD.ShapeArchive", "TSWP.ShapeInfoArchive"):
        kind = "shape"
        # Text content for shapes lives in an ownedStorage archive
        # (TSWP.StorageArchive) whose identifier we use as a content
        # proxy: same deck + different text → different storage ids.
        os_ref = obj.get("ownedStorage") or obj.get("owned_storage")
        if isinstance(os_ref, dict) and os_ref.get("identifier"):
            asset_ref = f"storage:{os_ref['identifier']}"
    elif pbtype == "KN.PlaceholderArchive":
        kind = "placeholder"
        # Placeholder has super.super.ownedStorage chain
        super_super = (super_obj.get("super") if isinstance(super_obj, dict) else {}) or {}
        os_ref = (super_obj.get("ownedStorage")
                  or super_super.get("ownedStorage")
                  or super_obj.get("owned_storage")
                  or super_super.get("owned_storage"))
        if isinstance(os_ref, dict) and os_ref.get("identifier"):
            asset_ref = f"storage:{os_ref['identifier']}"
        # Also include the placeholder 'kind' (TITLE=1, BODY=2, etc.)
        # so 'title' and 'body' placeholders fingerprint differently.
        pkind = obj.get("kind")
        if pkind is not None:
            asset_ref = f"{asset_ref}|pkind:{pkind}" if asset_ref else f"pkind:{pkind}"
    elif pbtype == "TSD.GroupArchive":
        kind = "group"
        # Groups have child drawables we should still recurse into.
    elif pbtype.startswith("TSCH."):
        kind = "chart"
    elif pbtype.startswith("TST."):
        kind = "table"
    elif pbtype.startswith("TSWP."):
        kind = "text"

    # Pull geometry
    bbox = (None, None, None, None, None)
    if isinstance(geom, dict):
        pos = geom.get("position") or {}
        sz  = geom.get("size") or {}
        ang = geom.get("angle")
        bbox = (_round(pos.get("x")), _round(pos.get("y")),
                _round(sz.get("width")), _round(sz.get("height")),
                _round(ang, 1) if ang is not None else None)

    # Text content (may live deep in TSWP storage)
    txt = _find_text(obj)
    t_hash = sha256_hex(txt.encode("utf-8"))[:16] if txt else None
    if txt:
        ctx["text_chars"] = ctx.get("text_chars", 0) + len(txt)
    if asset_ref:
        ctx.setdefault("asset_refs", []).append(asset_ref)

    # Emit a fingerprint tuple for THIS drawable
    found.append((kind, *bbox, t_hash, asset_ref, pbtype or None))

    # Recurse for groups (whose super has its own drawables list)
    if kind == "group":
        children = (obj.get("children") or [])
        for c in children:
            if isinstance(c, dict):
                # Children are references — resolution happens in parse_key
                # via the all_archives dict and the recursive caller. For
                # safety, also walk the child object directly if it's inlined.
                _walk_for_elements(c, ctx, found)


_TEXT_FIELDS = ("text", "string", "_pbtype")

def _find_text(node) -> str:
    """Best-effort text extraction. Looks for a 'text' field in a Storage
    object (Keynote text storage)."""
    if isinstance(node, dict):
        # Direct text fields
        if "text" in node and isinstance(node["text"], str):
            return node["text"]
        # text_storage.string
        ts = node.get("text_storage")
        if isinstance(ts, dict) and isinstance(ts.get("text"), str):
            return ts["text"]
        # Sometimes the text lives under .storage.text  or similar — recurse one level
        for k in ("storage", "string", "rich_text"):
            v = node.get(k)
            if isinstance(v, dict):
                t = _find_text(v)
                if t:
                    return t
    return ""


def _find_asset_ref(node) -> str | None:
    """Look for a data identifier we could use as an asset reference."""
    if not isinstance(node, dict):
        return None
    for k in ("imagedata", "image_data", "imageData", "data", "movie"):
        v = node.get(k)
        if isinstance(v, dict):
            ident = v.get("identifier")
            if ident:
                return f"data:{ident}"
            di = v.get("data")
            if isinstance(di, dict):
                ident = di.get("identifier")
                if ident:
                    return f"data:{ident}"
    return None


def fingerprint_slide(slide_dict: dict, page_no: int) -> SlideFingerprint:
    """Given a parsed slide archive (dict from IWAFile.to_dict()), return a
    SlideFingerprint. Robust to schema variation: we walk recursively."""
    fp = SlideFingerprint(page_no)
    # iwa_uuid — the archive identifier of the SlideArchive object
    if isinstance(slide_dict, dict):
        fp.iwa_uuid = slide_dict.get("identifier") or slide_dict.get("__id")

    # Walk elements
    elements: list[tuple] = []
    ctx: dict = {}
    _walk_for_elements(slide_dict, ctx, elements)

    fp.raw_elements = elements
    fp.element_count = len(elements)
    fp.text_chars = ctx.get("text_chars", 0)
    fp.asset_refs = ctx.get("asset_refs", [])

    elements_sorted = sorted(elements, key=lambda t: (t[1] or 0, t[2] or 0, t[0]))
    fp.element_sig = sha256_hex(repr(elements_sorted).encode("utf-8"))
    return fp


# ----- Read all slide archives from a .key ----------------------------------

def parse_key(key_path: Path) -> list[SlideFingerprint]:
    """Open a .key (Keynote 14.5+ zip), follow Document.iwa's slideTree to
    get the ordered list of SlideNode identifiers, follow each SlideNode →
    SlideArchive id, then parse the corresponding archive.

    Skipped slides (`isSkipped=True`) are excluded so page_no aligns with
    the AppleScript / build.py path used for the rest of the DB.
    """
    zf = _open_key(key_path)
    if zf is None:
        sys.exit(f"ERROR: not a zip-format .key  ({key_path})")

    with zf:
        names = zf.namelist()
        doc_names = [n for n in names if n.endswith("Index/Document.iwa")]
        if not doc_names:
            sys.exit("ERROR: no Index/Document.iwa in .key")
        doc = IWAFile.from_buffer(zf.read(doc_names[0])).to_dict()

        archives = doc.get("chunks", [{}])[0].get("archives", [])

        # 1. Find the DocumentArchive — has 'slideTree.slides' = ordered
        #    list of SlideNode identifiers.
        slide_node_order: list[str] = []
        for ar in archives:
            obj = ar.get("objects", [{}])[0] if ar.get("objects") else {}
            tree = obj.get("slideTree")
            if isinstance(tree, dict) and "slides" in tree:
                for entry in tree["slides"]:
                    if isinstance(entry, dict) and "identifier" in entry:
                        slide_node_order.append(str(entry["identifier"]))
                break

        # 2. SlideNode → SlideArchive ident mapping
        node_to_slide: dict[str, dict] = {}
        for ar in archives:
            obj = ar.get("objects", [{}])[0] if ar.get("objects") else {}
            if "slide" in obj and "isSkipped" in obj:
                hid = str(ar.get("header", {}).get("identifier", ""))
                node_to_slide[hid] = {
                    "slide_id": str(obj.get("slide", {}).get("identifier", "")),
                    "is_skipped": bool(obj.get("isSkipped", False)),
                }

        # 3. Filter to non-skipped, preserve order
        visible_slide_ids: list[str] = []
        for nid in slide_node_order:
            link = node_to_slide.get(nid)
            if link and not link["is_skipped"]:
                visible_slide_ids.append(link["slide_id"])

        # 4. Index ALL archives (across every .iwa) by header.identifier
        #    so we can follow drawable references freely. Drawables (shapes,
        #    images, text boxes) are stored as their own archives, referenced
        #    by id from the SlideArchive's ownedDrawables list.
        all_archives: dict[str, dict] = {}
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
                    all_archives[aid] = obj

        # 5. Build fingerprints in page_no order. For each slide, follow its
        #    drawable references (ownedDrawables) → individual drawable
        #    archives, then walk those for geometry / text.
        fingerprints: list[SlideFingerprint] = []
        for page_idx, sid in enumerate(visible_slide_ids, start=1):
            slide_obj = all_archives.get(sid)
            if slide_obj is None:
                fingerprints.append(SlideFingerprint(page_idx))
                continue

            fp = SlideFingerprint(page_idx)
            fp.iwa_uuid = sid

            drawable_refs = (slide_obj.get("ownedDrawables")
                             or slide_obj.get("owned_drawables")
                             or [])

            elements: list[tuple] = []
            ctx: dict = {}
            for ref in drawable_refs:
                if not isinstance(ref, dict):
                    continue
                ref_id = str(ref.get("identifier", ""))
                drawable_obj = all_archives.get(ref_id)
                if drawable_obj is None:
                    continue
                _walk_for_elements(drawable_obj, ctx, elements)

            fp.raw_elements = elements
            fp.element_count = len(elements)
            fp.text_chars = ctx.get("text_chars", 0)
            fp.asset_refs = ctx.get("asset_refs", [])
            elements_sorted = sorted(elements,
                                     key=lambda t: (t[1] or 0, t[2] or 0, t[0]))
            fp.element_sig = sha256_hex(repr(elements_sorted).encode("utf-8"))
            fingerprints.append(fp)

        return fingerprints


def _collect_refs(node, out: list, _seen=None):
    """Walk a node tree looking for {identifier: ...} reference dicts,
    appending identifiers in document order (depth-first)."""
    if _seen is None:
        _seen = set()
    if isinstance(node, dict):
        if "identifier" in node and len(node) <= 3:
            ident = str(node["identifier"])
            if ident not in _seen:
                _seen.add(ident)
                out.append(ident)
        for v in node.values():
            _collect_refs(v, out, _seen)
    elif isinstance(node, list):
        for v in node:
            _collect_refs(v, out, _seen)


# ----- Update DB or probe ---------------------------------------------------

def update_db(deck_id: str, fingerprints: list[SlideFingerprint]) -> int:
    conn = sqlite3.connect(DB)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for fp in fingerprints:
        cur = conn.execute(
            "UPDATE slides SET iwa_uuid = ?, element_sig = ?, updated_at = ? "
            "WHERE deck_id = ? AND page_no = ?",
            (fp.iwa_uuid, fp.element_sig, now, deck_id, fp.page_no)
        )
        n += cur.rowcount
    conn.commit()
    conn.close()
    return n


def probe(fingerprints: list[SlideFingerprint], key_path: Path) -> None:
    """Print a per-page report: which incoming pages match existing slides
    in the DB. Doesn't write anything."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    print(f"\n指纹查重报告  ·  {key_path.name}")
    print("=" * 72)
    print(f"{'page':>4}  {'matched?':<18}  via                       existing slide")
    print("-" * 72)

    tally = {"uuid": 0, "struct": 0, "none": 0, "stub": 0}
    for fp in fingerprints:
        if fp.element_sig is None:
            print(f"{fp.page_no:>4}  {'(stub, 解析失败)':<18}")
            tally["stub"] += 1
            continue
        match_via = None
        match_row = None
        if fp.iwa_uuid:
            r = conn.execute(
                "SELECT id, deck_id, page_no, title FROM slides "
                "WHERE iwa_uuid = ? LIMIT 1",
                (fp.iwa_uuid,)
            ).fetchone()
            if r:
                match_row, match_via = r, "uuid"
        if not match_row:
            r = conn.execute(
                "SELECT id, deck_id, page_no, title FROM slides "
                "WHERE element_sig = ? LIMIT 1",
                (fp.element_sig,)
            ).fetchone()
            if r:
                match_row, match_via = r, "structural"

        if match_row:
            mark = "✓ match"
            existing = f"{match_row['deck_id']}/p{match_row['page_no']}  {match_row['title'][:30]}"
            print(f"{fp.page_no:>4}  {mark:<18}  {match_via:<24}  {existing}")
            tally[match_via if match_via != "structural" else "struct"] += 1
        else:
            print(f"{fp.page_no:>4}  {'· 新':<18}  ({fp.element_count} elems, "
                  f"{fp.text_chars} chars)")
            tally["none"] += 1

    print("-" * 72)
    print(f"  UUID 命中: {tally['uuid']}")
    print(f"  结构命中: {tally['struct']}")
    print(f"  全新:     {tally['none']}")
    print(f"  解析失败: {tally['stub']}")
    print()
    conn.close()


# ----- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck_id", nargs="?", default=None,
                    help="Existing deck_id to update (omit when using --probe)")
    ap.add_argument("key_path", type=Path,
                    help="Path to .key file (zip-format Keynote 14.5+)")
    ap.add_argument("--probe", action="store_true",
                    help="Don't write to DB; just report matches against existing slides")
    args = ap.parse_args()

    if not args.key_path.is_file():
        sys.exit(f"ERROR: .key not found: {args.key_path}")

    print(f"Parsing {args.key_path.name} …", file=sys.stderr)
    fps = parse_key(args.key_path)
    print(f"  → {len(fps)} slides parsed", file=sys.stderr)

    if args.probe:
        probe(fps, args.key_path)
        return

    if not args.deck_id:
        sys.exit("ERROR: deck_id required (or use --probe)")

    print(f"Writing fingerprints for deck_id='{args.deck_id}' …", file=sys.stderr)
    n = update_db(args.deck_id, fps)
    print(f"  → updated {n} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
