#!/usr/bin/env python3
"""
deck-splice helper · pick.py — find candidate slides in slides.db for a
new pitch deck, based on keywords (FTS) + customer tags + exclusions.

Usage:
    python3 pick.py --keywords 销售 渠道 培训 \
                    --customers 立白 安利 美宜佳 \
                    --exclude-deck lanyueliang-pitch \
                    --limit 40

Output: a ranked, tab-separated table to stdout, plus a candidate manifest
skeleton on --emit-manifest (paste into splice.py).
"""
from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DB_PATH   = REPO_ROOT / "library" / "db" / "data" / "slides.db"


def main() -> int:
    ap = argparse.ArgumentParser(prog="pick")
    ap.add_argument("--keywords", nargs="*", default=[],
                    help="FTS keywords (OR-joined). Empty = ignore text match.")
    ap.add_argument("--customers", nargs="*", default=[],
                    help="Filter by customer_tag (any of).")
    ap.add_argument("--types", nargs="*", default=[],
                    help="Filter by type_tag (any of, e.g. 案例 方法论).")
    ap.add_argument("--exclude-deck", nargs="*", default=[],
                    help="Skip these deck_ids.")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--emit-manifest", action="store_true",
                    help="Also print a manifest skeleton to stdout (need to edit "
                         "outer_key for each row).")
    args = ap.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"slides.db not found at {DB_PATH}")
    con = sqlite3.connect(DB_PATH); cur = con.cursor()

    rows: list[tuple] = []

    if args.keywords:
        q = " OR ".join(args.keywords)
        cur.execute(
            "SELECT s.deck_id, s.slide_key, s.page_no, s.type_tag, s.customer_tag, "
            "       s.media_tag, s.title "
            "FROM slides_fts f JOIN slides s ON s.id = f.id "
            "WHERE slides_fts MATCH ? ORDER BY s.deck_id, s.page_no",
            (q,)
        )
        rows = cur.fetchall()
    else:
        cur.execute(
            "SELECT deck_id, slide_key, page_no, type_tag, customer_tag, media_tag, title "
            "FROM slides ORDER BY deck_id, page_no"
        )
        rows = cur.fetchall()

    # post-filter (FTS doesn't index tag columns, so we do it in Python)
    if args.customers:
        cs = set(args.customers); rows = [r for r in rows if r[4] in cs]
    if args.types:
        ts = set(args.types);     rows = [r for r in rows if r[3] in ts]
    if args.exclude_deck:
        es = set(args.exclude_deck); rows = [r for r in rows if r[0] not in es]

    rows = rows[: args.limit]

    print(f"{'deck':28s}  {'p#':>3s}  {'key':<24s}  {'type':<8s}  {'cust':<8s}  {'media':<6s}  title")
    print("-" * 110)
    for deck, key, pno, t, cust, med, title in rows:
        print(f"{deck:28s}  {pno:>3d}  {key:<24s}  {(t or '-'):<8s}  "
              f"{(cust or '-'):<8s}  {(med or '-'):<6s}  {(title or '')[:50]}")
    print(f"\n{len(rows)} candidates.")

    if args.emit_manifest:
        skeleton = {
            "host_pack": "rolling-deck",
            "splices": [
                {"outer_key": f"FILL_ME_{i+1:02d}",
                 "source_deck_id": deck,
                 "source_slide_key": key}
                for i, (deck, key, *_rest) in enumerate(rows)
            ],
        }
        print("\n# manifest skeleton — edit outer_key for each row:")
        print(json.dumps(skeleton, ensure_ascii=False, indent=2))

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
