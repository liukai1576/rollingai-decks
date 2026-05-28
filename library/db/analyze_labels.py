#!/usr/bin/env python3
"""
analyze_labels.py — compare unified_probe output against user-provided
ground truth labels and report per-channel precision.

For each (sinian_page, target_slide_key) candidate, look up:
  · what channels fired and with what scores
  · ground truth label (S=same, L=similar, N=unrelated)

Then bucket by channel/threshold and print precision (✓+~ over total)
and split (S vs L vs N).

This drives threshold tuning: which combinations give best signal?
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_fingerprints import parse_key, _open_key
from text_overlap_probe import extract_page_texts, tokenize, jaccard, overlap_coef
from collect_assets import (
    _build_data_id_index, _build_zip_name_index,
    _index_slide_drawables, _collect_data_refs_in_drawable, sha256_file,
)

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"
LABELS_PATH = ROOT / "data" / "SINIAN-LABELS.json"
SINIAN_KEY = Path("/Users/liukai/Library/Mobile Documents/com~apple~Keynote/Documents/企业Pitch/AI案例分享和AI转型建议- 思念.key")
EXT_OF_INTEREST = {".png", ".jpg", ".jpeg", ".gif", ".webp",
                   ".mp4", ".mov", ".m4v", ".pdf", ".svg", ".tiff"}
MIN_ASSET_SIZE = 50 * 1024


def collect_all_candidates() -> dict[tuple[int, str], dict]:
    """Re-run all channels and collect every (sinian_page, slide_key) →
    {channels: {...}} record."""
    out: dict[tuple[int, str], dict] = defaultdict(lambda: {"channels": {}})

    # --- Fingerprint channels ---
    fps = parse_key(SINIAN_KEY)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    for fp in fps:
        if fp.element_sig is None:
            continue
        if fp.iwa_uuid:
            r = conn.execute(
                "SELECT slide_key FROM slides WHERE iwa_uuid = ? LIMIT 1",
                (fp.iwa_uuid,)
            ).fetchone()
            if r:
                out[(fp.page_no, r["slide_key"])]["channels"]["uuid"] = True
        r = conn.execute(
            "SELECT slide_key FROM slides WHERE element_sig = ? LIMIT 1",
            (fp.element_sig,)
        ).fetchone()
        if r:
            out[(fp.page_no, r["slide_key"])]["channels"]["structural"] = True
        if fp.template_sig:
            r = conn.execute(
                "SELECT slide_key FROM slides WHERE template_sig = ? LIMIT 1",
                (fp.template_sig,)
            ).fetchone()
            if r:
                out[(fp.page_no, r["slide_key"])]["channels"]["template"] = True

    # --- Text channel ---
    pages = extract_page_texts(SINIAN_KEY)
    db_slides = []
    for r in conn.execute(
        "SELECT slide_key, body_text FROM slides WHERE body_text IS NOT NULL"
    ):
        toks = tokenize(r["body_text"])
        if toks:
            db_slides.append((r["slide_key"], toks))
    for page_no, texts in pages:
        joined = " ".join(texts)
        toks = tokenize(joined)
        if len(toks) < 5:
            continue
        for slide_key, db_toks in db_slides:
            j = jaccard(toks, db_toks)
            oc = overlap_coef(toks, db_toks)
            if j >= 0.2 or oc >= 0.4:
                out[(page_no, slide_key)]["channels"]["text"] = (j, oc)

    # --- Asset channel ---
    zf = _open_key(SINIAN_KEY)
    is_dir = SINIAN_KEY.is_dir()
    data_dir = SINIAN_KEY / "Data" if is_dir else None
    zip_idx = {} if is_dir else _build_zip_name_index(zf)
    id_to_fn = _build_data_id_index(zf)
    visible_ids, all_arch = _index_slide_drawables(zf)
    seen: dict[str, tuple[str, int]] = {}
    for data_id, fn in id_to_fn.items():
        ext = os.path.splitext(fn)[1].lower()
        if ext not in EXT_OF_INTEREST:
            continue
        try:
            if is_dir:
                stem, ext_part = os.path.splitext(fn)
                cands = [data_dir / f"{stem}-{data_id}{ext_part}",
                         data_dir / fn]
                fp_ = next((c for c in cands if c.is_file()), None)
                if fp_ is None or fp_.stat().st_size < MIN_ASSET_SIZE:
                    continue
                h, size = sha256_file(fp_)
            else:
                stem, ext_part = os.path.splitext(fn)
                arc = zip_idx.get(f"Data/{stem}-{data_id}{ext_part}") or \
                      zip_idx.get(f"Data/{fn}")
                if arc is None:
                    continue
                info = zf.getinfo(arc)
                if info.file_size < MIN_ASSET_SIZE:
                    continue
                h, size = sha256_file(zf.read(arc))
            seen[data_id] = (h, size)
        except Exception:
            continue

    for page_idx, sid in enumerate(visible_ids, start=1):
        refs: dict[str, str] = {}
        slide_obj = all_arch.get(sid, {})
        for ref in slide_obj.get("ownedDrawables") or []:
            if isinstance(ref, dict) and ref.get("identifier"):
                drawable = all_arch.get(str(ref["identifier"]))
                if drawable:
                    _collect_data_refs_in_drawable(drawable, all_arch, refs)
        for data_id, role in refs.items():
            if data_id not in seen:
                continue
            h, size = seen[data_id]
            reuse = conn.execute(
                "SELECT COUNT(DISTINCT slide_id) FROM slide_assets "
                "WHERE asset_hash = ?", (h,)
            ).fetchone()[0]
            if reuse >= 3:
                continue
            rows = conn.execute(
                "SELECT s.slide_key FROM slide_assets sa "
                "JOIN slides s ON s.id = sa.slide_id "
                "WHERE sa.asset_hash = ?", (h,)
            ).fetchall()
            for r in rows:
                ch = out[(page_idx, r["slide_key"])]["channels"]
                ch.setdefault("assets", []).append((size, role))
    zf.close()
    conn.close()
    return out


def main():
    labels = json.loads(LABELS_PATH.read_text())["labels"]
    print(f"Loaded {len(labels)} labeled pages\n", file=sys.stderr)

    print("Running probes …", file=sys.stderr)
    candidates = collect_all_candidates()
    print(f"  → {len(candidates)} (page, slide) candidates total\n",
          file=sys.stderr)

    # For each candidate, determine its strongest signal type
    rows = []
    for (page, skey), data in candidates.items():
        ch = data["channels"]
        truth = labels.get(f"p{page}", {}).get(skey, "?")
        text = ch.get("text")
        assets = ch.get("assets", [])
        flags = []
        if ch.get("uuid"):       flags.append("uuid")
        if ch.get("structural"): flags.append("struct")
        if ch.get("template"):   flags.append("tmpl")
        if text:
            j, oc = text
            flags.append(f"text(j={j:.2f},ovl={oc:.2f})")
        if assets:
            total_kb = sum(s for s,_ in assets) // 1024
            flags.append(f"asset({len(assets)}×, {total_kb}KB)")
        rows.append((page, skey, truth, ", ".join(flags), text, assets))

    # Count target reuse: how many Sinian pages does each Kangshifu slide
    # get hit by via asset-only?
    target_counter: Counter[str] = Counter()
    for page, skey, truth, _, text, assets in rows:
        if assets and not text:
            target_counter[skey] += 1

    print("=== Target asset-only popularity (potential template/scenery) ===")
    for skey, n in target_counter.most_common(10):
        print(f"  {skey}: matched {n} Sinian pages via asset-only")

    # --- Precision by channel ---
    def precision(predicate, name):
        matched = [(p, sk, t) for (p, sk, t, _, _, _) in rows if predicate(rows, p, sk)]
        if not matched:
            print(f"{name}: 0 candidates"); return
        bucket = Counter(t for _, _, t in matched)
        s = bucket.get("S", 0); l = bucket.get("L", 0)
        n = bucket.get("N", 0); q = bucket.get("?", 0)
        total = s + l + n
        if total == 0:
            print(f"{name}: {len(matched)} cands but no labels"); return
        prec = (s + l) / total * 100
        print(f"{name}: {s}S + {l}L + {n}N  ({q} unlabeled)  "
              f"precision={prec:.0f}%  ({s+l}/{total})")

    print("\n=== Per-channel precision ===")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[4] and r[4][0] >= 0.5
        for r in rs
    ), "text jac ≥ 0.50            ")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[4] and r[4][1] >= 0.7
        for r in rs
    ), "text ovl ≥ 0.70            ")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[4] and r[4][0] >= 0.2 and r[4][0] < 0.5
        for r in rs
    ), "text jac 0.20–0.50         ")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[5] and not r[4]
        for r in rs
    ), "asset only (no text)       ")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[5] and not r[4] and target_counter[sk] <= 3
        for r in rs
    ), "asset only + target ≤ 3×   ")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[5] and not r[4] and target_counter[sk] >= 4
        for r in rs
    ), "asset only + target ≥ 4×   ")
    precision(lambda rs, p, sk: any(
        r[0]==p and r[1]==sk and r[5] and not r[4]
        and sum(s for s,_ in r[5]) >= 2*1024*1024
        for r in rs
    ), "asset only + ≥ 2MB         ")

    # Detail table
    print("\n=== Per-candidate detail ===")
    print(f"{'page':>5}  {'target':<14}  {'truth':<3}  signals")
    for page, skey, truth, flags, _, _ in sorted(rows):
        print(f"{page:>5}  {skey:<14}  {truth:<3}  {flags}")


if __name__ == "__main__":
    main()
