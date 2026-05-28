#!/usr/bin/env python3
"""
text_overlap_probe.py — find DB slides that share substantial text content
with the slides of a new .key file. Catches the "same content, different
layout" case that element_sig / template_sig miss (e.g. Sinian p3
re-laying-out Kangshifu p6's case-study card grid).

Tokenization: Chinese character 2-grams + ASCII word-stems. Robust to
whitespace / punctuation differences. Similarity = Jaccard of token sets.

Usage:
    python3 text_overlap_probe.py "<path-to-.key>" [--min-jaccard 0.3]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

try:
    from keynote_parser.codec import IWAFile
except ImportError:
    sys.exit("ERROR: pip install keynote-parser")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_fingerprints import _open_key, _walk_for_elements

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"

# ---- tokenization ---------------------------------------------------------

_RE_CJK = re.compile(r"[一-鿿]")
_RE_ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_RE_NUM = re.compile(r"\d+(?:\.\d+)?")

# Stop-tokens that are too generic to be useful (also filter master
# placeholders / company-name-only matches that always trigger)
_STOP_TOKENS = {
    "rollingai", "rolling", "ai", "100", "10", "1000",
    "rolling ai", "rolling-ai",
}


def tokenize(text: str) -> set[str]:
    """Convert text to a set of unique tokens for Jaccard comparison.

    Strategy: character 2-grams for CJK runs + lowercased ASCII words +
    raw numbers. We strip whitespace / punctuation so two slides with
    the same content but different formatting still match.
    """
    if not text:
        return set()
    tokens: set[str] = set()
    # CJK 2-grams
    for run in re.findall(r"[一-鿿]+", text):
        for i in range(len(run) - 1):
            tokens.add(run[i:i+2])
        # also include single chars to anchor short titles
        if len(run) <= 2:
            tokens.add(run)
    # ASCII words
    for w in _RE_ASCII_WORD.findall(text):
        wl = w.lower()
        if wl not in _STOP_TOKENS:
            tokens.add(wl)
    # Numbers (sometimes the only signal — "+14%" / "2800小时")
    for n in _RE_NUM.findall(text):
        if n not in _STOP_TOKENS:
            tokens.add(n)
    return tokens - _STOP_TOKENS


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap_coef(a: set, b: set) -> float:
    """Containment / overlap coefficient: |A ∩ B| / min(|A|, |B|).
    Robust to size imbalance — catches the "small page is fully reused
    inside a larger page" pattern that Jaccard misses."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ---- extract texts per page from a .key -----------------------------------

def extract_page_texts(key_path: Path) -> list[tuple[int, list[str]]]:
    """Return [(page_no, [text_strs])] in slide order."""
    zf = _open_key(key_path)
    if zf is None:
        sys.exit(f"ERROR: cannot open {key_path}")
    with zf:
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

        out: list[tuple[int, list[str]]] = []
        for page_idx, sid in enumerate(visible_ids, start=1):
            slide_obj = all_arch.get(sid, {})
            elements, ctx = [], {}
            for ref in slide_obj.get("ownedDrawables") or []:
                if isinstance(ref, dict) and ref.get("identifier"):
                    _walk_for_elements(all_arch.get(str(ref["identifier"]), {}),
                                       ctx, elements, all_arch)
            out.append((page_idx, ctx.get("texts", [])))
        return out


# ---- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key_path", type=Path)
    ap.add_argument("--min-jaccard", type=float, default=0.60,
                    help="Min Jaccard for symmetric overlap")
    ap.add_argument("--min-overlap", type=float, default=0.50,
                    help="Min overlap coefficient (|A∩B| / min(|A|,|B|)) — "
                         "catches 'small page reused in larger page'")
    ap.add_argument("--min-tokens", type=int, default=8,
                    help="Skip pages with fewer than this many tokens")
    ap.add_argument("--top-k", type=int, default=3,
                    help="Show up to K best matches per page")
    args = ap.parse_args()

    if not args.key_path.exists():
        sys.exit(f"ERROR: not found: {args.key_path}")

    print(f"Extracting text from {args.key_path.name} …", file=sys.stderr)
    pages = extract_page_texts(args.key_path)
    print(f"  → {len(pages)} pages", file=sys.stderr)

    # Pre-load DB slides with body_text
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    db_slides = []
    for r in conn.execute(
        "SELECT id, deck_id, page_no, title, body_text FROM slides WHERE body_text IS NOT NULL"
    ):
        tokens = tokenize(r["body_text"])
        if len(tokens) >= args.min_tokens:
            db_slides.append((dict(r), tokens))
    print(f"  → {len(db_slides)} existing slides with text in DB", file=sys.stderr)
    conn.close()

    print(f"\n文本重叠查重 (jaccard ≥ {args.min_jaccard} 或 overlap ≥ {args.min_overlap})")
    print("=" * 78)
    n_with_matches = 0
    for page_no, texts in pages:
        joined = " ".join(texts)
        toks = tokenize(joined)
        if len(toks) < args.min_tokens:
            continue
        scored = []
        for row, db_toks in db_slides:
            j = jaccard(toks, db_toks)
            oc = overlap_coef(toks, db_toks)
            # match if EITHER metric exceeds threshold
            if j >= args.min_jaccard or oc >= args.min_overlap:
                scored.append((max(j, oc), j, oc, row, db_toks & toks))
        if not scored:
            continue
        n_with_matches += 1
        scored.sort(key=lambda t: -t[0])
        print(f"\nnew p{page_no} ({len(toks)} tokens)")
        joined_preview = joined.replace("\n", " ")[:60]
        print(f"  内容预览: {joined_preview!r}")
        for best, j, oc, row, overlap in scored[:args.top_k]:
            existing = f"{row['deck_id']}/p{row['page_no']}"
            title = (row["title"] or "")[:36]
            shared = list(overlap)[:5]
            print(f"  ↔ {existing:18}  jac={j:.2f} ovl={oc:.2f}   {title}")
            print(f"       共享 token: {' / '.join(shared)}")
    print()
    print(f"共 {n_with_matches} 页找到文本重叠匹配")


if __name__ == "__main__":
    main()
