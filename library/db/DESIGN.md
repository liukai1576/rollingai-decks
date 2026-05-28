# Slide / Story 系统设计笔记

讨论沉淀。已经做的部分见 README.md；这份只记设计意图、未做的部分。

---

## 1. 多 deck 的去重、复用、血缘（远期）

整体目标：当用户从康师傅 deck **拷一部分内容做新 deck** 时，系统要：

- 知道哪些 slide 是同一个（不要重复存）
- 知道哪些 slide 是同一个的微改版（保留血缘）
- 知道哪些 story 是相同/相似的
- 物理上一个 200MB 视频只存一份

### 1.1 数据层：CAS（Content-Addressed Storage）

```
library/db/
├── data/slides.db
└── store/
    ├── ab/cdef1234...mp4
    └── ef/567890ab...jpg
```

```sql
CREATE TABLE assets (
  hash         TEXT PRIMARY KEY,       -- sha256(file_bytes)
  size_bytes   INTEGER NOT NULL,
  mime         TEXT,
  width        INTEGER, height INTEGER,
  duration_ms  INTEGER,
  stored_path  TEXT NOT NULL,
  first_seen   TEXT NOT NULL,
  first_origin TEXT
);
CREATE TABLE slide_assets (
  slide_id     TEXT NOT NULL,
  asset_hash   TEXT NOT NULL,
  role         TEXT,
  bbox         TEXT,
  PRIMARY KEY (slide_id, asset_hash, role)
);
```

- 入库前 SHA-256 每个素材，已存在则复用
- 渲染时 deck.json 引用 `/store/<hash>`，不引用 per-deck 路径
- 引用计数 → 孤儿 GC（先软删 N 天再真删）

### 1.2 slide 精确去重：content_hash

slides 表加 `content_hash`：canonical 规范化（去空白 + 按位置排序 + 把
asset 路径替换成 asset_hash）后取 SHA-256。`SELECT WHERE content_hash=?`
即 O(log N) 查重。

### 1.3 slide 相似匹配：四通道

单通道不够——纯背景图 / 视频为主的 slide 文本通道完全失效。多通道：

| 通道 | 适用 | 失效条件 |
|---|---|---|
| 文本 MinHash（128bit）| 文本 ≥ 10 token | 否则弃权 |
| Asset Jaccard | 所有 slide（视频 / 大图尤其有效）| 无 |
| Layout sig（type + 圆整 bbox + 字体） | 模板复用 | 无 |
| 视觉 pHash（64bit）| 视觉相似（含纯图 / 纯视频）| 没渲染时弃权 |

```python
similarity(A, B) = max over channels  # OR 关系，不是 AND
```

UI 里展示"相似 slide"列表时，每条标注**哪个通道**命中，让用户判断真血缘还是巧合。

视觉 pHash 需要渲染；推荐用 Playwright 在服务端 headless 截图（也复用给"再生成"用）。

### 1.4 story 相似匹配

- 精确：`composition_hash = sha256(|.join(slide.content_hash))`
- Jaccard：忽略顺序，看共享 slide 比例
- LCS：保留顺序的相似度
- 把 slide 的相似度传播上去：A 中的 slide 在 B 中有相似版本也算"共享"

---

## 2. 导入时去重（Phase A 现在要做的）

把指纹从"渲染后的 HTML 哈希"前推到"解析 .key 时直接算"。三个信号：

### 2.1 iWork UUID（最精确，但有限）

```python
slide_uuid = iwa_slide.identifier   # 类似 "Slide-abc-123"
```

- 命中 → 铁证血缘（"用户在 Keynote 里复制了这页"）
- 对不上 ≠ 不是同一页（用户从 PPT 转换 / 从头重画时 UUID 是新的）

### 2.2 结构指纹 element_sig（最实用）

```python
elements = [
  (e.type,
   round(e.x, -1), round(e.y, -1), round(e.w, -1), round(e.h, -1),
   sha256(e.text) if e.text else None,
   e.asset_hash if e.asset else None,
   e.font_family, round(e.font_size))
  for e in slide.elements
]
elements.sort()
element_sig = sha256(repr(elements))
```

- `round(x, -1)` = 10px 圆整，容忍微小坐标漂移
- 文本独立 hash，"中文换英文" / "粗体改普通" 都会变指纹

### 2.3 素材重叠（前面 1.3 的 asset Jaccard 通道）

对纯背景图 / 视频为主的 slide 补救信号 2 的盲点。

### 2.4 命中后做什么

```
导入新 deck：
  · 第 2 页: UUID 命中已有 → 链接（不复制）
  · 第 3 页: element_sig 相同 → 链接
  · 第 4 页: 与已有相似 0.73，文本差 12% → 新 slide + derived_from
  · 第 5 页: 素材 100% 重叠但结构差异大 → 新 slide，flagged 待人工
```

---

## 3. 架构改动：把 slide 与 deck 解耦（Phase B，远期）

当前 `slides.id = "{deck_id}/{slide_key}"`、`slides.deck_id` 固定。同一
slide 出现在多 deck 时这个模型崩。要拆：

```sql
-- slides 变成"内容核"
CREATE TABLE slides (
  id              TEXT PRIMARY KEY,    -- UUID
  iwa_uuid        TEXT,
  element_sig     TEXT NOT NULL,
  content_hash    TEXT NOT NULL,
  title           TEXT, ...tag列...,
  origin_source   TEXT,
  created_at      TEXT NOT NULL
);

-- deck → slide 关联
CREATE TABLE deck_slides (
  deck_id    TEXT NOT NULL,
  slide_key  TEXT NOT NULL,
  slide_id   TEXT NOT NULL,
  page_no    INTEGER NOT NULL,
  PRIMARY KEY (deck_id, slide_key)
);

-- decks 独立
CREATE TABLE decks (
  id            TEXT PRIMARY KEY,
  display_name  TEXT,
  source_path   TEXT,
  imported_at   TEXT NOT NULL
);
```

### 派生（版本树）

```sql
ALTER TABLE slides ADD COLUMN derived_from_slide_id TEXT;
ALTER TABLE slides ADD COLUMN derivation_diff       TEXT;  -- JSON
```

新 slide 与已有差 ~25% → 入新行 + derived_from 指向原行 + diff 记录改了哪几个元素。

---

## 实施顺序

| 阶段 | 内容 | 状态 |
|---|---|---|
| **A** | slides 表加 `iwa_uuid` / `element_sig`；写 `collect_fingerprints.py`<br>从康师傅 .key 读取并填上；导入新 .key 时查重报告（不阻断） | **当前** |
| **B** | 拆 `decks` / `deck_slides`；slides 去 deck_id；UI 适配 | 后 |
| **C** | CAS（assets + slide_assets）；素材物理去重 | 与 B 并行 |
| **D** | 文本 MinHash + LSH + layout_sig + 视觉 pHash | 远 |
| **E** | derived_from + 版本树 + diff UI | 远 |

A 不动 schema 的核心（只加列），不动现有 output，可以随时回滚。
