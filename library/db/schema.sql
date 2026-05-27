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
  type_tag        TEXT,                -- 封面 / 公司介绍 / 案例 / 方法论 / 数据图表 / Section / 结尾 / 其他
  subtype_tag     TEXT,                -- 产品介绍 / 项目效果 / 客户痛点 / 团队 / 时间线 / 矩阵 / ...
  customer_tag    TEXT,                -- 蒙牛 / 飞鹤 / 周大福 / ...  (NULL when slide is not customer-specific)
  media_tag       TEXT,                -- 图文 / 视频 / 表格 / 纯文字

  -- Free-form tags as JSON array (e.g. ["金句页","内部使用"])
  free_tags       TEXT DEFAULT '[]',

  notes           TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_slides_deck     ON slides(deck_id);
CREATE INDEX IF NOT EXISTS idx_slides_type     ON slides(type_tag);
CREATE INDEX IF NOT EXISTS idx_slides_customer ON slides(customer_tag);
CREATE INDEX IF NOT EXISTS idx_slides_media    ON slides(media_tag);

CREATE TABLE IF NOT EXISTS stories (
  id          TEXT PRIMARY KEY,        -- "kangshifu/company-intro"
  title       TEXT NOT NULL,           -- "公司介绍"
  description TEXT,
  deck_id     TEXT,
  notes       TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stories_deck ON stories(deck_id);

CREATE TABLE IF NOT EXISTS story_slides (
  story_id   TEXT NOT NULL,
  slide_id   TEXT NOT NULL,
  position   INTEGER NOT NULL,         -- 0-based order within the story
  PRIMARY KEY (story_id, slide_id),
  FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
  FOREIGN KEY (slide_id) REFERENCES slides(id)  ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_story_slides_story ON story_slides(story_id);
CREATE INDEX IF NOT EXISTS idx_story_slides_slide ON story_slides(slide_id);

-- Full-text search over title + body_text (queryable via slides_fts MATCH ...)
CREATE VIRTUAL TABLE IF NOT EXISTS slides_fts USING fts5(
  id UNINDEXED,
  title,
  body_text,
  tokenize = "unicode61 remove_diacritics 2"
);
