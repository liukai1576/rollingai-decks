#!/usr/bin/env python3
"""
import_csv.py — read library/db/data/slides.csv (edited externally) and
upsert tag columns into the DB. Only changes columns the CSV contains;
all other columns left intact.
"""
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"
CSV_PATH = ROOT / "data" / "slides.csv"

UPDATABLE = ["title", "type_tag", "subtype_tag",
             "customer_tag", "media_tag", "free_tags", "notes"]

if not CSV_PATH.is_file():
    sys.exit(f"ERROR: {CSV_PATH} not found. Run export_csv.py first.")

conn = sqlite3.connect(DB)
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
n_changed = 0
with CSV_PATH.open(encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        slide_id = row.get("id")
        if not slide_id:
            continue
        sets, vals = [], []
        for col in UPDATABLE:
            if col in row:
                sets.append(f"{col} = ?")
                vals.append(row[col] or None)
        if not sets:
            continue
        sets.append("updated_at = ?")
        vals.append(now)
        vals.append(slide_id)
        conn.execute(
            f"UPDATE slides SET {', '.join(sets)} WHERE id = ?",
            vals
        )
        n_changed += 1
# Rebuild FTS shadow (titles may have changed)
conn.execute("DELETE FROM slides_fts")
conn.execute(
    "INSERT INTO slides_fts(id, title, body_text) "
    "SELECT id, title, body_text FROM slides"
)
conn.commit()
conn.close()
print(f"Updated {n_changed} rows.")
