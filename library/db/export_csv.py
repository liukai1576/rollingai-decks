#!/usr/bin/env python3
"""
export_csv.py — dump slides to CSV for batch tag editing in a spreadsheet.
Edit the file (preserving id column), then re-import via import_csv.py.
"""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"
CSV_PATH = ROOT / "data" / "slides.csv"

EDITABLE_COLUMNS = [
    "id", "page_no", "title", "type_tag", "subtype_tag",
    "customer_tag", "media_tag", "free_tags", "notes",
]

conn = sqlite3.connect(DB)
rows = conn.execute(
    f"SELECT {', '.join(EDITABLE_COLUMNS)} FROM slides ORDER BY deck_id, page_no"
).fetchall()
conn.close()

with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(EDITABLE_COLUMNS)
    for r in rows:
        w.writerow(r)
print(f"Wrote {CSV_PATH} ({len(rows)} rows).")
print("Edit in Excel / Numbers / etc., then run: python3 import_csv.py")
