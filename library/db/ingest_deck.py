#!/usr/bin/env python3
"""
ingest_deck.py — scan a deck.json + index.html, auto-tag each slide,
write to slides.db.

Heuristics for the auto-tag pass are intentionally conservative — the
output is a *first cut* for human review, not a final labeling. Re-run
freely; rows are upserted by primary key.

Usage:
    python3 ingest_deck.py <deck_id> <path-to-deck.json>
    python3 ingest_deck.py kangshifu ../../imports/RollingAI分享-康师傅/render-output-full/deck.json

Output:
    library/db/data/slides.db   (created if missing, schema applied)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / "schema.sql"
DB_PATH = ROOT / "data" / "slides.db"

# ---------- Known-name dictionaries (heuristics) -------------------------

CUSTOMERS = [
    "康师傅", "蒙牛", "飞鹤", "周大福", "AIA", "友邦", "MARS", "玛氏",
    "极兔", "J&T", "Amway", "安利", "双汇", "ZIROOM", "自如", "美宜佳",
    "可口可乐", "沃尔玛", "FOTILE", "方太", "Schneider", "施耐德",
    "Volvo", "BMW", "BEA", "东亚银行", "邮政储蓄", "邮储",
    "建设银行", "兴业银行", "HSBC", "汇丰", "九仙尊", "999", "三九医药",
    "HISUN", "海正药业", "DIAGEO", "SUNTORY", "三得利", "Unilever", "联合利华",
    "GUCCI", "李宁", "LI-NING", "华熙生物", "润百颜", "BIOHYALUX",
    "Naisnow", "奈雪", "SENHENG", "森杨", "华润",
    "盛业", "九方智投", "银泰", "复星", "FOSUN",
    "RENAULT", "NISSAN", "MITSUBISHI", "SCANIA", "MICHELIN", "米其林",
    "Cornerstone", "康诺思腾", "东阿阿胶", "元气森林", "liby", "立白",
]

# Type heuristics: keyword → 类型
TYPE_KEYWORDS = {
    "封面": ["AI 重塑", "AI重塑", "如何继续领先", "Agentic Business Builder"],
    "Section": [],     # section titles detected by short body + large font
    "公司介绍": ["商业咨询", "原生咨询", "成功案例", "Our Clients",
              "RollingAI", "全球领导者", "ai原生"],
    "案例": ["案例", "客户", "项目效果", "成功落地", "13个AI原型",
            "10天", "训战营", "AI 销售", "AI销售", "RM", "对话拆解",
            "营养师", "宠物", "销售代表", "经销商", "AI 角色扮演",
            "AI 销售助手", "AI 经销商助手", "AI销售助手"],
    # ⚠ "数据图表" type was retired (see data/STORY-PROPOSAL.md §1). Pages
    # with KPI / 数据 visuals are still 方法论 (论证某个方法论) or 案例
    # (具体客户的项目效果). The percent / RMB / 增长 keywords now fold into
    # 方法论's bucket.
    "方法论": ["方法论", "模式", "竞争壁垒", "新质生产力",
              "电力革命", "AI革命", "矩阵", "六大", "三大",
              "底层逻辑", "趋势", "落地", "原则", "支点", "撬动",
              "%", "￥", "RMB", "提升", "转化率", "增长"],
    "结尾": ["谢谢", "Thank you", "Q&A", "联系我们"],
}

SUBTYPE_KEYWORDS = {
    "项目效果": ["转化率提升", "销售提升", "日活", "RMB 价值", "用户",
                "时间节省", "节省 90%", "5.3M", "100M", "86M"],
    "产品介绍": ["产品", "工具", "助手", "AI 销售", "AI 经销",
                "AI 角色扮演", "AI 宝宝", "AI 科学育儿"],
    "客户痛点": ["问题", "痛点", "挑战", "焦虑", "高频痛点"],
    "团队": ["创始合伙人", "刘开", "LiuKai", "团队",
              "波士顿咨询", "客座教授"],
    "时间线": ["从2022年", "2022", "2023", "2024", "2025", "2026", "已经完成", "卸任"],
    "矩阵": ["矩阵", "六大", "三维", "维度"],
    "对比": ["对比", "vs", "VS", "前后", "改变"],
    "金句": ["金句", "做一艘船", "不要做柱子", "翻天覆地"],
    "流程图": ["流程", "横向", "纵向", "funnel", "漏斗", "step", "阶段"],
}

MEDIA_TAGS = ["视频", "图文", "表格", "纯文字"]


# ---------- HTML parsing -------------------------------------------------

_RE_TAG = re.compile(r"<[^>]+>")
_RE_STYLE_BLOCK = re.compile(r"<style[^>]*>.*?</style>", re.S | re.I)
_RE_SCRIPT_BLOCK = re.compile(r"<script[^>]*>.*?</script>", re.S | re.I)
_RE_FONTSIZE = re.compile(r"font-size\s*:\s*([\d.]+)px", re.I)
_RE_WS = re.compile(r"\s+")


def strip_html(html: str) -> str:
    """Remove tags / style / script, return plain text (single-spaced)."""
    s = _RE_STYLE_BLOCK.sub(" ", html)
    s = _RE_SCRIPT_BLOCK.sub(" ", s)
    s = _RE_TAG.sub(" ", s)
    # Decode the few entities that show up in our extracted HTML
    s = (s.replace("&nbsp;", " ")
           .replace("&amp;", "&")
           .replace("&lt;", "<")
           .replace("&gt;", ">")
           .replace("&quot;", '"'))
    s = _RE_WS.sub(" ", s).strip()
    return s


def extract_title(html: str, body_text: str) -> tuple[str, str]:
    """Return (title, source) where source is 'extracted' or 'auto-summary'.

    Heuristic for "extracted":
      Find the text element with the largest font-size (px); use its inner
      text if it's between 4 and 80 chars and doesn't look like junk
      (copyright footer, page number, etc.).

    Falls back to a summary of the first content sentence if no clear
    title found.
    """
    # Find candidate (font-size, text) pairs from inline styles
    candidates: list[tuple[float, str]] = []
    for m in re.finditer(
        r'<(?:div|h1|h2|h3|p|span)[^>]*style="[^"]*font-size\s*:\s*([\d.]+)px[^"]*"[^>]*>(.*?)</(?:div|h1|h2|h3|p|span)>',
        html, re.S | re.I,
    ):
        try:
            size = float(m.group(1))
        except ValueError:
            continue
        inner = strip_html(m.group(2))
        if inner:
            candidates.append((size, inner))

    # Sort by font-size desc and pick first reasonable one
    candidates.sort(key=lambda x: -x[0])
    JUNK = ("Confidential", "Proprietary", "Rolling ai Confidential",
            "Rolling AI Confidential", "页码", "page", "Page",
            "RollingAI", "￼")
    for size, txt in candidates:
        if size < 30:        # too small to be a real title
            continue
        if any(j in txt for j in JUNK):
            continue
        if len(txt) < 2 or len(txt) > 80:
            continue
        return (txt, "extracted")

    # Fallback: take first sentence-ish chunk from body_text
    summary = (body_text.split("。")[0] if body_text else "").strip()
    if not summary:
        summary = body_text[:40] if body_text else "(empty)"
    return (summary[:80], "auto-summary")


def count_media(html: str) -> tuple[int, int]:
    """Return (image_count, video_count) from <img>/<video> tags."""
    n_img = len(re.findall(r"<img\b", html, re.I))
    n_vid = len(re.findall(r"<video\b", html, re.I))
    return n_img, n_vid


def guess_media_tag(n_img: int, n_vid: int, body_len: int) -> str:
    if n_vid >= 1:
        return "视频"
    if "<table" in "" and False:  # placeholder for future
        return "表格"
    if n_img == 0 and body_len > 0:
        return "纯文字"
    return "图文"


def guess_customer(body_text: str) -> str | None:
    for c in CUSTOMERS:
        if c in body_text:
            return c
    return None


def guess_type(body_text: str, title: str, page_no: int,
               total_pages: int, n_img: int, n_vid: int) -> str:
    if page_no == 1:
        return "封面"
    if page_no == total_pages:
        return "结尾"
    # Section title: short body, single large title element
    if len(body_text) < 40 and len(title) > 0:
        return "Section"

    # Score each type
    scores: dict[str, int] = {}
    for typ, kws in TYPE_KEYWORDS.items():
        if not kws:
            continue
        for kw in kws:
            if kw in body_text or kw in title:
                scores[typ] = scores.get(typ, 0) + 1
    if scores:
        return max(scores.items(), key=lambda kv: kv[1])[0]
    return "其他"


def guess_subtype(body_text: str, title: str, type_tag: str) -> str | None:
    scores: dict[str, int] = {}
    for sub, kws in SUBTYPE_KEYWORDS.items():
        for kw in kws:
            if kw in body_text or kw in title:
                scores[sub] = scores.get(sub, 0) + 1
    if scores:
        return max(scores.items(), key=lambda kv: kv[1])[0]
    return None


# ---------- DB ----------------------------------------------------------

def open_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def upsert_slide(conn: sqlite3.Connection, row: dict, *, retag: bool = False) -> None:
    """Insert or update one slide row.

    On UPDATE (slide already in DB), human-curated fields are PRESERVED by
    default: type_tag / subtype_tag / customer_tag / media_tag / free_tags
    keep their existing values, notes and thumbnail_path only take the new
    value when the new value is non-null. Content-derived fields (page_no,
    title, body_text) always refresh — re-ingesting after an insert-slides
    task must renumber pages without losing a week of tagging work.

    Pass retag=True to force the auto-guessed tags over existing ones
    (the pre-2026-06 behaviour).
    """
    cols = ["id", "deck_id", "slide_key", "page_no", "title", "title_source",
            "thumbnail_path", "body_text",
            "type_tag", "subtype_tag", "customer_tag", "media_tag",
            "free_tags", "notes",
            "created_at", "updated_at"]
    placeholders = ", ".join(["?"] * len(cols))

    ALWAYS_REFRESH = {"deck_id", "slide_key", "page_no", "title",
                      "title_source", "body_text", "updated_at"}
    PRESERVE_UNLESS_RETAG = {"type_tag", "subtype_tag", "customer_tag",
                             "media_tag", "free_tags"}
    # nullable payload: only overwrite when the new value is non-null
    COALESCE_NEW = {"notes", "thumbnail_path"}

    parts = []
    for c in cols:
        if c in ("id", "created_at"):
            continue
        if c in ALWAYS_REFRESH or (retag and c in PRESERVE_UNLESS_RETAG):
            parts.append(f"{c}=excluded.{c}")
        elif c in COALESCE_NEW:
            parts.append(f"{c}=COALESCE(excluded.{c}, {c})")
        # PRESERVE_UNLESS_RETAG without retag: omit → keeps existing value
    updates = ", ".join(parts)
    sql = (f"INSERT INTO slides ({', '.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT(id) DO UPDATE SET {updates}")
    conn.execute(sql, [row[c] for c in cols])
    # FTS shadow is maintained by schema triggers (slides_fts_after_*) —
    # no manual sync here.


# ---------- Main --------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck_id", help="Short id for this deck, e.g. 'kangshifu'")
    ap.add_argument("deck_json", type=Path, help="Path to deck.json")
    ap.add_argument("--retag", action="store_true",
                    help="Force auto-guessed tags over existing DB tags "
                         "(default: existing tags are preserved on re-ingest)")
    args = ap.parse_args()

    deck = json.loads(args.deck_json.read_text(encoding="utf-8"))

    # deck.json version handling. v2 (current) has slides[].title /
    # slides[].notes as first-class fields — we MUST prefer them over
    # re-scraping HTML, otherwise edits to title via admin / transformer
    # skills get silently overwritten on the next ingest. v1.0 / unset
    # → fall back to HTML scraping.
    deck_version = str(deck.get("version", "1.0"))
    if deck_version not in ("1.0", "2"):
        sys.exit(f"ERROR: unknown deck.json version '{deck_version}' "
                 f"(supported: 1.0, 2). See plugin/_spec/deck-json-v2.md.")
    is_v2 = (deck_version == "2")

    slides = deck.get("slides", [])
    total = len(slides)
    if total == 0:
        sys.exit("ERROR: deck.json has no slides")

    conn = open_db()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"Ingesting {total} slides from {args.deck_id} "
          f"(deck.json v{deck_version}) …", file=sys.stderr)
    for idx, s in enumerate(slides, start=1):
        slide_key = s["key"]
        html = (s.get("data") or {}).get("html", "")
        body = strip_html(html)

        # v2: canonical title is slides[].title. v1: scrape from HTML.
        if is_v2 and "title" in s:
            title = s.get("title") or ""
            src = "extracted" if title else "stub"
            if not title:
                # Pure-image slide — keep the stub convention used elsewhere
                title = f"(p{idx} · 无标题)"
        else:
            title, src = extract_title(html, body)

        n_img, n_vid = count_media(html)
        type_tag = guess_type(body, title, idx, total, n_img, n_vid)
        sub_tag  = guess_subtype(body, title, type_tag)
        media    = guess_media_tag(n_img, n_vid, len(body))
        cust     = guess_customer(body)

        row = {
            "id": f"{args.deck_id}/{slide_key}",
            "deck_id": args.deck_id,
            "slide_key": slide_key,
            "page_no": idx,
            "title": title,
            "title_source": src,
            "thumbnail_path": None,
            "body_text": body[:5000],
            "type_tag": type_tag,
            "subtype_tag": sub_tag,
            "customer_tag": cust,
            "media_tag": media,
            "free_tags": "[]",
            # v2: pull notes from slides[].notes (transformer skills may have
            # added editorial context). v1: stays NULL.
            "notes": (s.get("notes") or None) if is_v2 else None,
            "created_at": now,
            "updated_at": now,
        }
        upsert_slide(conn, row, retag=args.retag)

    conn.commit()
    conn.close()
    print(f"  → {DB_PATH}", file=sys.stderr)
    print(f"Done. Open the DB with:  sqlite3 {DB_PATH}", file=sys.stderr)
    print(f"Or browse via:           pip install datasette && datasette {DB_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
