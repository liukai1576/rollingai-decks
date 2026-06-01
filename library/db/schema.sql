-- RollingAI DeckBuilder · slide & story database schema
--
-- Two-tier model:
--   slides       — one row per page across all decks
--   stories      — coherent narrative units (≈ 4-8 slides each)
--   story_slides — many-to-many link with explicit position
--
-- Canonical tags live as scalar columns on `slides`. Free-form tags live
-- as a JSON array (sqlite JSON1 is fine).
--
-- Apply to a fresh db:
--   sqlite3 data/slides.db < schema.sql

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS slides (
  id              TEXT PRIMARY KEY,    -- "{deck_id}/{slide_key}" e.g. "kangshifu/slide-006"
  deck_id         TEXT NOT NULL,       -- "kangshifu"
  slide_key       TEXT NOT NULL,       -- "slide-006"
  page_no         INTEGER NOT NULL,    -- 1-based PDF page
  title           TEXT NOT NULL,       -- extracted title or auto-generated summary
  title_source    TEXT NOT NULL,       -- 'extracted' | 'auto-summary'
  thumbnail_path  TEXT,
  body_text       TEXT,                -- stripped text content, for FTS

  -- Canonical single-value tags
  type_tag        TEXT,                -- 公司介绍 / 案例 / 方法论 / Section / 结尾   (see data/STORY-PROPOSAL.md)
  subtype_tag     TEXT,                -- 团队 / Offering / 产品介绍 / 项目效果 / 客户痛点 / 历史故事 / 历史对比 / 顶层思考 / 金句 / 矩阵 / ...
  customer_tag    TEXT,                -- 蒙牛 / 飞鹤 / 立白 / 友邦保险 / RollingAI (自我介绍页) / NULL (通用)
  media_tag       TEXT,                -- 图文 / 视频 / 表格 / 纯文字

  -- Free-form tags as JSON array (e.g. ["金句页","内部使用"])
  free_tags       TEXT DEFAULT '[]',

  notes           TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,

  -- Phase A 导入级指纹（从 .key 直接采集，不经渲染）
  iwa_uuid        TEXT,        -- iWork internal ID（"复制 slide" 时会沿用）
  element_sig     TEXT,        -- 严格：结构 + 素材 + 文字 storage_id（区分文字版本）
  template_sig    TEXT         -- 松：只看结构 + 素材，忽略文字（识别同模板）
);

CREATE INDEX IF NOT EXISTS idx_slides_deck     ON slides(deck_id);
CREATE INDEX IF NOT EXISTS idx_slides_type     ON slides(type_tag);
CREATE INDEX IF NOT EXISTS idx_slides_customer ON slides(customer_tag);
CREATE INDEX IF NOT EXISTS idx_slides_media    ON slides(media_tag);
CREATE INDEX IF NOT EXISTS idx_slides_iwa_uuid     ON slides(iwa_uuid);
CREATE INDEX IF NOT EXISTS idx_slides_element_sig  ON slides(element_sig);
CREATE INDEX IF NOT EXISTS idx_slides_template_sig ON slides(template_sig);

CREATE TABLE IF NOT EXISTS stories (
  -- A story is a (consecutive) range of slides given a name.
  -- Membership is implicit: any slide where slide.page_no BETWEEN
  -- start_page AND end_page belongs to this story. Stories may
  -- overlap (one slide can be in multiple stories). Section /
  -- transition pages can be filtered out at query time via
  -- slide.type_tag = 'Section'.
  id          TEXT PRIMARY KEY,        -- "kangshifu/case-feihe"
  title       TEXT NOT NULL,           -- "飞鹤 AI 营养师"
  description TEXT,
  deck_id     TEXT NOT NULL,
  start_page  INTEGER,                 -- inclusive
  end_page    INTEGER,                 -- inclusive
  notes       TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stories_deck  ON stories(deck_id);
CREATE INDEX IF NOT EXISTS idx_stories_range ON stories(deck_id, start_page);

-- (story_slides M:N table removed 2026-05-29: membership is now derived
-- from start_page / end_page range, since stories are always consecutive
-- slide sets. See DESIGN.md.)

-- ---------------------------------------------------------------------------
-- Content-addressed asset registry  (see library/db/collect_assets.py)
--
-- One row per unique asset content (keyed by SHA-256). Used for cross-deck
-- dedup: spotting when two decks reuse the same image / video binary.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assets (
  hash         TEXT PRIMARY KEY,  -- SHA-256 hex
  size_bytes   INTEGER NOT NULL,
  ext          TEXT,              -- ".png" / ".mp4" / ".jpeg" / ...
  filename     TEXT,              -- canonical filename inside the first .key bundle that produced this asset
  first_deck   TEXT,              -- deck_id where this hash first appeared
  first_seen   TEXT               -- ISO timestamp
);

CREATE INDEX IF NOT EXISTS idx_assets_first_deck ON assets(first_deck);

-- M:N link between slides and assets. A slide can use multiple assets;
-- the same asset can appear on many slides (the same logo across a deck,
-- or the same image reused across decks).
CREATE TABLE IF NOT EXISTS slide_assets (
  slide_id     TEXT NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
  asset_hash   TEXT NOT NULL REFERENCES assets(hash),
  role         TEXT,              -- 'image' / 'movie' / 'background' / ...
  iwa_data_id  INTEGER,           -- the iWork identifier inside the .key, for traceability
  PRIMARY KEY (slide_id, asset_hash, iwa_data_id)
);

CREATE INDEX IF NOT EXISTS idx_slide_assets_hash  ON slide_assets(asset_hash);
CREATE INDEX IF NOT EXISTS idx_slide_assets_slide ON slide_assets(slide_id);

-- Full-text search over title + body_text (queryable via slides_fts MATCH ...)
CREATE VIRTUAL TABLE IF NOT EXISTS slides_fts USING fts5(
  id UNINDEXED,
  title,
  body_text,
  tokenize = "unicode61 remove_diacritics 2"
);
