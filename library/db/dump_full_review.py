#!/usr/bin/env python3
"""
dump_full_review.py — comprehensive markdown audit of the current DB:
  · all slides table (with tags)
  · stories with their member slides
  · "needs-review" subset
  · tag axis statistics

Writes to library/db/data/FULL-REVIEW.md.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"
OUT = ROOT / "data" / "FULL-REVIEW.md"


def main():
    conn = sqlite3.connect(DB)
    lines: list[str] = []

    lines.append(f"# Slide & Story 评审报告\n")
    lines.append(f"_生成于 {datetime.now().isoformat(timespec='seconds')}_\n")
    lines.append("\n查看完后：\n")
    lines.append("- 单条修改：`sqlite3 library/db/data/slides.db` 然后 `UPDATE slides SET type_tag='...' WHERE id='...';`\n")
    lines.append("- 批量修改：`python3 export_csv.py` → 编辑 `data/slides.csv` → `python3 import_csv.py`\n")
    lines.append("- Web 浏览：`pip install datasette && datasette library/db/data/slides.db`\n")
    lines.append("\n---\n")

    # ----- Stories with their member slides -----
    lines.append("\n## 1️⃣ Stories（已入库）\n")
    stories = conn.execute(
        "SELECT id, title, description, deck_id, start_page, end_page "
        "FROM stories ORDER BY deck_id, start_page"
    ).fetchall()
    for sid, st_title, desc, deck_id, sp, ep in stories:
        # Range-model membership: any slide on the same deck whose
        # page_no falls inside [start_page, end_page]. (See schema.sql —
        # the old story_slides M:N table was removed 2026-05-29.)
        members = conn.execute(
            "SELECT s.page_no, s.title, s.type_tag, s.subtype_tag, "
            "       s.customer_tag, s.media_tag "
            "FROM slides s "
            "WHERE s.deck_id = ? AND s.page_no BETWEEN ? AND ? "
            "ORDER BY s.page_no",
            (deck_id, sp, ep)
        ).fetchall()
        lines.append(f"\n### {st_title}\n")
        lines.append(f"- id: `{sid}`\n")
        if desc:
            lines.append(f"- note: {desc}\n")
        lines.append(f"- slides ({len(members)}):\n")
        lines.append("\n| 页 | 标题 | 类型 | 细分 | 客户 | 媒体 |\n")
        lines.append("|---|---|---|---|---|---|\n")
        for n, t, typ, sub, cust, media in members:
            t_short = (t or "")[:40] + ("…" if t and len(t) > 40 else "")
            lines.append(f"| {n} | {t_short} | {typ or '·'} | "
                         f"{sub or '·'} | {cust or '·'} | {media or '·'} |\n")
    lines.append("\n---\n")

    # ----- Needs review -----
    lines.append("\n## 2️⃣ Needs review（未归入任何 story 的孤立 slide）\n")
    orphans = conn.execute(
        "SELECT s.page_no, s.id, s.title, s.type_tag, s.media_tag, s.free_tags "
        "FROM slides s "
        "WHERE NOT EXISTS ( "
        "  SELECT 1 FROM stories st "
        "  WHERE st.deck_id = s.deck_id "
        "    AND s.page_no BETWEEN st.start_page AND st.end_page "
        ") ORDER BY s.page_no"
    ).fetchall()
    lines.append("\n| 页 | id | 标题 | 类型 | 媒体 | free_tags |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for n, sid, t, typ, media, free in orphans:
        t_short = (t or "")[:50] + ("…" if t and len(t) > 50 else "")
        lines.append(f"| {n} | `{sid}` | {t_short} | {typ or '·'} | "
                     f"{media or '·'} | {free} |\n")
    lines.append("\n---\n")

    # ----- All slides flat table -----
    lines.append("\n## 3️⃣ 所有 slides（按页码）\n")
    lines.append("\n| 页 | 标题 | 类型 | 细分 | 客户 | 媒体 | story |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    rows = conn.execute(
        "SELECT s.page_no, s.title, s.type_tag, s.subtype_tag, "
        "       s.customer_tag, s.media_tag, "
        "       (SELECT GROUP_CONCAT(st.title) FROM stories st "
        "        WHERE st.deck_id = s.deck_id "
        "          AND s.page_no BETWEEN st.start_page AND st.end_page) "
        "FROM slides s ORDER BY s.page_no"
    ).fetchall()
    for n, t, typ, sub, cust, media, story_titles in rows:
        t_short = (t or "")[:35] + ("…" if t and len(t) > 35 else "")
        st_short = (story_titles or "")[:25] + ("…" if story_titles and len(story_titles) > 25 else "")
        lines.append(f"| {n} | {t_short} | {typ or '·'} | "
                     f"{sub or '·'} | {cust or '·'} | {media or '·'} | "
                     f"{st_short or '·'} |\n")
    lines.append("\n---\n")

    # ----- Tag stats -----
    lines.append("\n## 4️⃣ 标签统计\n")
    for col in ("type_tag", "subtype_tag", "customer_tag", "media_tag"):
        lines.append(f"\n### {col}\n\n")
        counts = conn.execute(
            f"SELECT {col}, COUNT(*) FROM slides "
            f"WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY COUNT(*) DESC"
        ).fetchall()
        for val, c in counts:
            lines.append(f"- {val}: {c}\n")

    # Free-tag breakdown
    lines.append("\n### free_tags\n\n")
    free_counter: Counter[str] = Counter()
    for (free,) in conn.execute("SELECT free_tags FROM slides"):
        try:
            for tag in json.loads(free or "[]"):
                free_counter[tag] += 1
        except json.JSONDecodeError:
            continue
    for tag, c in free_counter.most_common():
        lines.append(f"- {tag}: {c}\n")

    conn.close()
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
