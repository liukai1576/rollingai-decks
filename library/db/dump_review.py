#!/usr/bin/env python3
"""
dump_review.py — dump the slides table as a markdown table for human
review. Edit it freely; then re-load via `load_review.py` (TODO) when
the schema needs tag corrections fed back in.

Usage:
    python3 dump_review.py [deck_id]   # filter by deck (default: all)
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "slides.db"
deck_filter = sys.argv[1] if len(sys.argv) > 1 else None

conn = sqlite3.connect(DB)
cur = conn.execute(
    "SELECT id, page_no, title, title_source, type_tag, subtype_tag, "
    "       customer_tag, media_tag, free_tags FROM slides "
    + ("WHERE deck_id = ?" if deck_filter else "")
    + " ORDER BY deck_id, page_no",
    (deck_filter,) if deck_filter else (),
)

print("| # | 标题 (来源) | 类型 | 细分 | 客户 | 媒体 | 自由标签 |")
print("|---|---|---|---|---|---|---|")
for sid, n, title, src, t, sub, cust, media, free in cur:
    t_short = title[:35] + ("…" if len(title) > 35 else "")
    src_mark = " · auto" if src == "auto-summary" else ""
    print(f"| {n} | {t_short}{src_mark} | "
          f"{t or '·'} | {sub or '·'} | {cust or '·'} | {media or '·'} | "
          f"{free if free != '[]' else '·'} |")

conn.close()
