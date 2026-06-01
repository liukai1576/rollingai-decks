#!/usr/bin/env python3
"""
refine_tags.py — second-pass tagging using story context.

After load_stories.py has populated story membership, this script:
  · propagates customer_tag from a story's title (e.g. "案例: 飞鹤 …"
    → all member slides get customer=飞鹤)
  · propagates type_tag from story title patterns (案例 / 方法论 /
    公司介绍 / 结尾)
  · flags slides not in any story with free_tag "needs-review"
  · improves a few specific weak titles (e.g. "(empty)", "￼ Rolling AI",
    short footers)

Safe to re-run.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"

# Customer names that may appear in a story title — order matters (longer
# first to avoid partial matches).
CUSTOMERS_IN_STORY_TITLE = [
    "飞鹤", "蒙牛", "周大福", "美宜佳", "极兔", "Amway", "安利",
    "双汇", "ZIROOM", "自如", "MARS", "玛氏", "可口可乐", "沃尔玛",
    "AIA", "友邦", "康师傅",
]

STORY_TYPE_MAP = [
    # (regex on title, type_tag override)
    (r"封面|开篇", "封面"),
    (r"公司介绍|能力|客户全景|客户.*总览", "公司介绍"),
    (r"案例", "案例"),
    (r"方法论", "方法论"),
    (r"总结|结尾|收尾", "结尾"),
    (r"趋势|论证|论点|铺垫", "方法论"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def propagate_from_stories(conn: sqlite3.Connection) -> None:
    """For each story, infer customer/type from title and propagate to members."""
    rows = conn.execute(
        "SELECT id, title FROM stories"
    ).fetchall()
    now = now_iso()
    for story_id, story_title in rows:
        # Detect customer in story title
        cust = next((c for c in CUSTOMERS_IN_STORY_TITLE
                     if c in story_title), None)
        # Detect type
        type_override = None
        for pat, t in STORY_TYPE_MAP:
            if re.search(pat, story_title):
                type_override = t
                break

        # Range-model membership: slides in this story = slides on the
        # deck whose page_no is between the story's start_page / end_page.
        # (story_slides M:N table was removed 2026-05-29 — see schema.sql.)
        slide_ids = [r[0] for r in conn.execute(
            "SELECT s.id FROM slides s "
            "JOIN stories st ON st.id = ? "
            " AND st.deck_id = s.deck_id "
            " AND s.page_no BETWEEN st.start_page AND st.end_page "
            "ORDER BY s.page_no",
            (story_id,)
        )]
        for sid in slide_ids:
            # Always set customer if story title carries one (override
            # auto-detection which may have missed)
            if cust:
                conn.execute(
                    "UPDATE slides SET customer_tag = ?, updated_at = ? "
                    "WHERE id = ?",
                    (cust, now, sid)
                )
            # Type: only override if current is generic ("其他" / "Section"
            # without an obvious section title content), to preserve
            # specific type tags that auto-tag got right
            cur_type = conn.execute(
                "SELECT type_tag FROM slides WHERE id = ?", (sid,)
            ).fetchone()[0]
            if type_override and cur_type in (None, "其他", "Section"):
                conn.execute(
                    "UPDATE slides SET type_tag = ?, updated_at = ? "
                    "WHERE id = ?",
                    (type_override, now, sid)
                )


def flag_unstoried(conn: sqlite3.Connection) -> None:
    """Slides not in any story → free_tags += 'needs-review'."""
    now = now_iso()
    # Orphan = slide on a deck where no story's [start_page, end_page]
    # range contains the slide's page_no.
    orphan_ids = [r[0] for r in conn.execute(
        "SELECT s.id FROM slides s "
        "WHERE NOT EXISTS ( "
        "  SELECT 1 FROM stories st "
        "  WHERE st.deck_id = s.deck_id "
        "    AND s.page_no BETWEEN st.start_page AND st.end_page "
        ")"
    )]
    for sid in orphan_ids:
        free = conn.execute(
            "SELECT free_tags FROM slides WHERE id = ?", (sid,)
        ).fetchone()[0] or "[]"
        try:
            tags = json.loads(free)
        except json.JSONDecodeError:
            tags = []
        if "needs-review" not in tags:
            tags.append("needs-review")
        conn.execute(
            "UPDATE slides SET free_tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tags, ensure_ascii=False), now, sid)
        )


def fix_weak_titles(conn: sqlite3.Connection) -> None:
    """Replace obviously-bad titles (empty / placeholder / corrupt) with
    a "(slide N · 待补)" stub so the slide is identifiable in the review."""
    now = now_iso()
    bad_patterns = [
        re.compile(r"^\s*$"),
        re.compile(r"^\s*\(empty\)\s*$"),
        re.compile(r"^\s*￼\s*Rolling\s*AI\s*$"),
        re.compile(r"^\s*\d+(\.\d+)?\s*%?\s*$"),     # just a number
        re.compile(r"^\s*￼\s*"),                     # leading ￼ char
    ]
    rows = conn.execute(
        "SELECT id, page_no, title, title_source FROM slides"
    ).fetchall()
    for sid, page_no, title, src in rows:
        if any(p.search(title or "") for p in bad_patterns):
            new = f"(p{page_no} · 待补标题)"
            conn.execute(
                "UPDATE slides SET title = ?, title_source = ?, updated_at = ? "
                "WHERE id = ?",
                (new, "stub", now, sid)
            )


def main():
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")

    print("Pass 1: propagate customer / type from story titles …")
    propagate_from_stories(conn)

    print("Pass 2: flag un-storied slides with needs-review …")
    flag_unstoried(conn)

    print("Pass 3: fix obviously-bad titles …")
    fix_weak_titles(conn)

    # Re-build FTS shadow rows (titles may have changed)
    conn.execute("DELETE FROM slides_fts")
    conn.execute(
        "INSERT INTO slides_fts(id, title, body_text) "
        "SELECT id, title, body_text FROM slides"
    )

    conn.commit()
    print("\nSummary:")
    for (lbl, q) in [
        ("total slides       ", "SELECT COUNT(*) FROM slides"),
        ("with customer tag  ", "SELECT COUNT(*) FROM slides WHERE customer_tag IS NOT NULL"),
        ("type=案例          ", "SELECT COUNT(*) FROM slides WHERE type_tag='案例'"),
        ("type=方法论        ", "SELECT COUNT(*) FROM slides WHERE type_tag='方法论'"),
        ("type=公司介绍      ", "SELECT COUNT(*) FROM slides WHERE type_tag='公司介绍'"),
        ("flagged needs-review", "SELECT COUNT(*) FROM slides WHERE free_tags LIKE '%needs-review%'"),
        ("stories            ", "SELECT COUNT(*) FROM stories"),
    ]:
        print(f"  {lbl}: {conn.execute(q).fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
