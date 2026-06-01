#!/usr/bin/env python3
"""
load_stories.py — parse STORY-PROPOSAL.md, upsert stories + story_slides.

Parses the bulleted format:

    ## N. <story title>
    - **页**：A – B
    - **slides**：`slide-NNN`, `slide-MMM`, ...   (optional, overrides page range)
    - **type**: ...
    - **note**: ...

Story id is auto-generated as "<deck_id>/<slug>" where slug is derived
from the section title. Position inside story_slides follows page_no order.

Re-running is idempotent — existing rows get UPSERTed.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "slides.db"

# A slug-able subset of pinyin / latin chars from common Chinese titles
SLUG_MAP = {
    "封面": "cover", "团队": "team", "介绍": "intro", "能力": "capability",
    "客户": "clients", "总览": "overview", "全景": "panorama",
    "AI": "ai", "革命": "revolution", "趋势": "trend", "论证": "argument",
    "管理": "management", "模式": "model", "重塑": "remake", "论点": "thesis",
    "案例": "case", "日化": "fmcg", "销售": "sales", "数字化": "digital",
    "过程": "process", "飞鹤": "feihe", "营养师": "nutritionist",
    "训战营": "training", "保险": "insurance", "头部": "top",
    "外资": "foreign", "方法论": "methodology", "隐性": "implicit",
    "资产": "asset", "经营": "business", "智慧": "wisdom",
    "原型": "prototype", "组织": "org", "进化": "evolution",
    "员工": "employee", "价值": "value", "总结": "summary",
    "结尾": "ending", "铺垫": "lead-in",
}


def make_slug(title: str) -> str:
    s = title
    for cn, en in SLUG_MAP.items():
        s = s.replace(cn, "-" + en)
    s = re.sub(r"[^a-zA-Z0-9_/-]+", "-", s).strip("-").lower()
    s = re.sub(r"-+", "-", s)
    return s or "story"


def parse_proposal(text: str) -> list[dict]:
    """Walk the markdown and return list of {title, description, page_range,
    slides_explicit, note}."""
    stories = []
    cur: dict | None = None

    lines = text.splitlines()
    for ln in lines:
        # Section heading "## N. title"
        m = re.match(r"^##\s+\d+\.\s+(.+?)\s*$", ln)
        if m:
            if cur:
                stories.append(cur)
            cur = {"title": m.group(1).strip(), "pages": None,
                   "slides_explicit": None, "note": None}
            continue
        if not cur:
            continue
        # Bullet lines
        if re.match(r"^-\s+\*\*页\*\*", ln):
            m = re.search(r"(\d+)\s*[–\-]\s*(\d+)", ln)
            if m:
                cur["pages"] = (int(m.group(1)), int(m.group(2)))
        elif re.match(r"^-\s+\*\*slides\*\*", ln):
            # Extract any `slide-NNN` references
            keys = re.findall(r"slide-\d{3}", ln)
            if keys:
                cur["slides_explicit"] = keys
        elif re.match(r"^-\s+\*\*note\*\*", ln):
            cur["note"] = ln.split("：", 1)[-1].strip() if "：" in ln else None
    if cur:
        stories.append(cur)
    return stories


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck-id", default="kangshifu",
                    help="Deck id this proposal applies to")
    ap.add_argument("--proposal", type=Path,
                    default=ROOT / "data" / "STORY-PROPOSAL.md",
                    help="Path to the markdown proposal file")
    args = ap.parse_args()

    deck_id = args.deck_id
    if not args.proposal.is_file():
        sys.exit(f"ERROR: proposal not found at {args.proposal}")
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    proposals = parse_proposal(args.proposal.read_text(encoding="utf-8"))
    if not proposals:
        sys.exit("ERROR: parsed zero stories from STORY-PROPOSAL.md")

    print(f"Parsed {len(proposals)} stories.", file=sys.stderr)

    # Pre-load existing slides for this deck for page→slide_id lookup
    slide_by_page = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT page_no, id FROM slides WHERE deck_id = ? ORDER BY page_no",
            (deck_id,)
        )
    }
    slide_by_key = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT slide_key, id FROM slides WHERE deck_id = ?",
            (deck_id,)
        )
    }

    for prop in proposals:
        title = prop["title"]
        slug = make_slug(title)
        story_id = f"{deck_id}/{slug}"

        # Stories are now stored as a (start_page, end_page) range — see
        # schema.sql. We resolve the range from the proposal's `pages`
        # bullet directly. The `slides_explicit` hint is kept as a
        # back-compat path: derive a range from the min/max page of the
        # listed keys.
        start_page = end_page = None
        if prop["pages"]:
            start_page, end_page = prop["pages"]
        elif prop["slides_explicit"]:
            # Derive the bracket from the explicit list — assumes the
            # listed slides are consecutive (per the new story model).
            pages = []
            for k in prop["slides_explicit"]:
                if k in slide_by_key:
                    # slide_by_key maps slide_key → slide.id; we need page_no.
                    for pno, sid in slide_by_page.items():
                        if sid == slide_by_key[k]:
                            pages.append(pno)
                            break
                else:
                    print(f"  WARN: story '{title}' references unknown {k}",
                          file=sys.stderr)
            if pages:
                start_page, end_page = min(pages), max(pages)

        if start_page is None:
            print(f"  SKIP empty story: {title}", file=sys.stderr)
            continue

        # Upsert story (id is the natural key; range model — no
        # story_slides table).
        conn.execute(
            "INSERT INTO stories (id, title, description, deck_id, "
            "                     start_page, end_page, notes, "
            "                     created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
            "  description=excluded.description, "
            "  start_page=excluded.start_page, end_page=excluded.end_page, "
            "  notes=excluded.notes, updated_at=excluded.updated_at",
            (story_id, title, prop["note"], deck_id,
             start_page, end_page, prop["note"], now, now)
        )
        print(f"  ✓ {story_id}  (p{start_page}–{end_page})",
              file=sys.stderr)

    conn.commit()
    conn.close()
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
