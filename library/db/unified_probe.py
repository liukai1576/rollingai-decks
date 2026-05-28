#!/usr/bin/env python3
"""
unified_probe.py — run all dedup channels and aggregate per-page matches.

For each page in the new .key, collect candidate matches from:
  · iwa_uuid               (Tier 1: provably copied)
  · element_sig            (Tier 2: structurally identical)
  · template_sig           (Tier 3: same template, text differs)
  · text overlap           (Tier 4: same content, redesigned layout)
  · asset hash             (Tier 5: shares one or more large assets)

Output a markdown table suitable for human labeling. The user marks each
candidate as ✓ / ~ / ✗, then we adjust per-channel thresholds.

Usage:
    python3 unified_probe.py <.key path>
    → writes data/UNIFIED-PROBE-<basename>.md
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_fingerprints import parse_key, _open_key
from text_overlap_probe import (
    extract_page_texts, tokenize, jaccard, overlap_coef
)
from collect_assets import (
    _build_data_id_index, _build_zip_name_index,
    _index_slide_drawables, _collect_data_refs_in_drawable,
    sha256_file,
)

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"
EXT_OF_INTEREST = {".png", ".jpg", ".jpeg", ".gif", ".webp",
                   ".mp4", ".mov", ".m4v", ".pdf", ".svg", ".tiff"}

# Loose thresholds — we WANT noise here, user filters by annotation
TEXT_MIN_JAC = 0.20
TEXT_MIN_OVL = 0.40
ASSET_MIN_SIZE = 50 * 1024


def probe_fingerprints(key_path: Path) -> dict[int, list[dict]]:
    """{page_no: [{tier, deck_id, page_no, title}]}"""
    out: dict[int, list[dict]] = defaultdict(list)
    fps = parse_key(key_path)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    for fp in fps:
        if fp.element_sig is None:
            continue
        # Tier 1: UUID
        if fp.iwa_uuid:
            r = conn.execute(
                "SELECT id, deck_id, page_no, title FROM slides "
                "WHERE iwa_uuid = ? LIMIT 1", (fp.iwa_uuid,)
            ).fetchone()
            if r:
                out[fp.page_no].append({"tier": "uuid", **dict(r)})
        # Tier 2: element_sig
        r = conn.execute(
            "SELECT id, deck_id, page_no, title FROM slides "
            "WHERE element_sig = ? LIMIT 1", (fp.element_sig,)
        ).fetchone()
        if r:
            out[fp.page_no].append({"tier": "structural", **dict(r)})
        # Tier 3: template_sig
        if fp.template_sig:
            r = conn.execute(
                "SELECT id, deck_id, page_no, title FROM slides "
                "WHERE template_sig = ? LIMIT 1", (fp.template_sig,)
            ).fetchone()
            if r:
                out[fp.page_no].append({"tier": "template", **dict(r)})
    conn.close()
    return out


def probe_text(key_path: Path) -> dict[int, list[dict]]:
    """{page_no: [{deck_id, page_no, title, jaccard, overlap, content_preview}]}"""
    out: dict[int, list[dict]] = defaultdict(list)
    pages = extract_page_texts(key_path)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Pre-tokenize existing slides
    existing = []
    for r in conn.execute(
        "SELECT id, deck_id, page_no, title, body_text FROM slides "
        "WHERE body_text IS NOT NULL"
    ):
        toks = tokenize(r["body_text"])
        if toks:
            existing.append((dict(r), toks))
    conn.close()
    for page_no, texts in pages:
        joined = " ".join(texts)
        toks = tokenize(joined)
        if len(toks) < 5:
            continue
        for row, db_toks in existing:
            j = jaccard(toks, db_toks)
            oc = overlap_coef(toks, db_toks)
            if j >= TEXT_MIN_JAC or oc >= TEXT_MIN_OVL:
                out[page_no].append({
                    **row, "jaccard": j, "overlap": oc,
                    "content_preview": joined[:50]
                })
    return out


def probe_assets(key_path: Path) -> dict[int, list[dict]]:
    """{page_no: [{deck_id, page_no, title, role, size_kb, filename}]}"""
    out: dict[int, list[dict]] = defaultdict(list)
    zf = _open_key(key_path)
    if zf is None:
        return out
    is_dir = key_path.is_dir()
    data_dir = key_path / "Data" if is_dir else None
    zip_idx = {} if is_dir else _build_zip_name_index(zf)
    id_to_fn = _build_data_id_index(zf)
    visible_ids, all_arch = _index_slide_drawables(zf)

    # Hash each asset → seen_hashes[data_id] = (hash, size, filename)
    seen: dict[str, tuple[str, int, str]] = {}
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
                if fp_ is None or fp_.stat().st_size < ASSET_MIN_SIZE:
                    continue
                h, size = sha256_file(fp_)
            else:
                stem, ext_part = os.path.splitext(fn)
                arc = zip_idx.get(f"Data/{stem}-{data_id}{ext_part}") or \
                      zip_idx.get(f"Data/{fn}")
                if arc is None:
                    continue
                info = zf.getinfo(arc)
                if info.file_size < ASSET_MIN_SIZE:
                    continue
                h, size = sha256_file(zf.read(arc))
            seen[data_id] = (h, size, fn)
        except Exception:
            continue

    # For each slide, collect its asset hashes, then query DB
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
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
            h, size, fn = seen[data_id]
            rows = conn.execute(
                "SELECT s.deck_id, s.page_no, s.title FROM slide_assets sa "
                "JOIN slides s ON s.id = sa.slide_id "
                "WHERE sa.asset_hash = ?", (h,)
            ).fetchall()
            for r in rows:
                out[page_idx].append({
                    **dict(r), "role": role, "size_kb": size // 1024,
                    "filename": fn[:40]
                })
    conn.close()
    zf.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key_path", type=Path)
    ap.add_argument("--output", "-o", type=Path, default=None)
    args = ap.parse_args()
    if not args.key_path.exists():
        sys.exit(f"ERROR: not found: {args.key_path}")

    print(f"Probing {args.key_path.name} via all channels …", file=sys.stderr)
    print(f"  · fingerprint channels …", file=sys.stderr)
    fp_matches = probe_fingerprints(args.key_path)
    print(f"  · text overlap channel …", file=sys.stderr)
    text_matches = probe_text(args.key_path)
    print(f"  · asset hash channel …", file=sys.stderr)
    asset_matches = probe_assets(args.key_path)

    all_pages = sorted(set(fp_matches) | set(text_matches) | set(asset_matches))
    print(f"  → {len(all_pages)} pages have at least one match", file=sys.stderr)

    out_path = args.output or (ROOT / "data" / f"UNIFIED-PROBE-{args.key_path.stem}.md")
    lines: list[str] = []
    lines.append(f"# 思念 vs 康师傅 · 统一查重报告\n\n")
    lines.append(f"`.key`: `{args.key_path.name}`\n\n")
    lines.append(f"**通道**：\n")
    lines.append(f"- **UUID** / **结构** / **模板** — 来自 collect_fingerprints\n")
    lines.append(f"- **文本** — jaccard ≥ {TEXT_MIN_JAC} 或 overlap ≥ {TEXT_MIN_OVL}\n")
    lines.append(f"- **素材** — 共享至少一个 ≥ {ASSET_MIN_SIZE//1024}KB 的素材（byte-identical）\n\n")
    lines.append(f"**请在每行 '判定' 列填**：`✓`（相同）/ `~`（相似/模板）/ `✗`（误报）/ 留空（待定）\n\n")
    lines.append("---\n\n")

    for page in all_pages:
        # Aggregate by candidate (deck_id, page_no) to dedup across channels
        agg: dict[tuple[str, int], dict] = {}
        for m in fp_matches.get(page, []):
            k = (m["deck_id"], m["page_no"])
            d = agg.setdefault(k, {"title": m["title"], "channels": {}})
            d["channels"][m["tier"]] = "命中"
        for m in text_matches.get(page, []):
            k = (m["deck_id"], m["page_no"])
            d = agg.setdefault(k, {"title": m["title"], "channels": {}})
            d["channels"]["文本"] = f"jac={m['jaccard']:.2f} ovl={m['overlap']:.2f}"
            d["preview"] = m.get("content_preview", "")
        for m in asset_matches.get(page, []):
            k = (m["deck_id"], m["page_no"])
            d = agg.setdefault(k, {"title": m["title"], "channels": {}})
            ex = d["channels"].get("素材", "")
            # Use " · " as in-cell separator (markdown table cells use |)
            new_entry = f"{m['role']} {m['size_kb']}KB"
            d["channels"]["素材"] = (ex + " · " if ex else "") + new_entry

        if not agg:
            continue

        lines.append(f"## p{page}\n\n")
        # Show content preview if we have it
        first_preview = next((d.get("preview") for d in agg.values() if d.get("preview")), None)
        if first_preview:
            lines.append(f"_内容预览_: `{first_preview}`\n\n")
        # Table
        lines.append("| 命中页 | 标题 | UUID | 结构 | 模板 | 文本 | 素材 | 判定 |\n")
        lines.append("|---|---|---|---|---|---|---|---|\n")
        # Sort candidates: prefer more channels hit, then by deck/page
        def rank(item):
            ch = item[1]["channels"]
            score = (
                10 if "uuid" in ch else 0) + (
                8 if "structural" in ch else 0) + (
                6 if "template" in ch else 0) + (
                4 if "文本" in ch else 0) + (
                2 if "素材" in ch else 0)
            return (-score, item[0][0], item[0][1])
        for (deck, pno), d in sorted(agg.items(), key=rank):
            ch = d["channels"]
            title = (d["title"] or "")[:35].replace("|", "\\|")
            lines.append(
                f"| {deck}/p{pno} | {title} | "
                f"{'✓' if 'uuid' in ch else '·'} | "
                f"{'✓' if 'structural' in ch else '·'} | "
                f"{'✓' if 'template' in ch else '·'} | "
                f"{ch.get('文本', '·')} | "
                f"{ch.get('素材', '·')} | "
                f"  |\n"
            )
        lines.append("\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
