# library/db/ — Slide & Story 数据库

两层结构：每张 slide 一个条目 + 故事（Story）把相关 slides 串成叙事单位。
本地 SQLite，配套 Python 脚本批量处理；可选 Datasette 做 Web 浏览。

## 数据库文件

`data/slides.db` —— SQLite 单文件数据库（已 gitignore，因为存储客户标
注内容）。schema 见 [`schema.sql`](schema.sql)。

```
slides         一行一页，4 个固定 tag 列 + JSON 自由 tag
stories        故事元信息
story_slides   多对多 + position（同一 slide 可被多 story 复用）
slides_fts     全文索引（FTS5）
```

## 常用命令

```bash
# 全套 from scratch
python3 ingest_deck.py kangshifu \
    ../../imports/RollingAI分享-康师傅/render-output-full/deck.json
python3 load_stories.py        # 读 data/STORY-PROPOSAL.md
python3 refine_tags.py         # 第二轮：基于 story 上下文细化 tag

# 评审
python3 dump_full_review.py    # 生成 data/FULL-REVIEW.md（最完整）
python3 dump_review.py kangshifu > data/REVIEW.md   # 紧凑版

# 批量改 tag
python3 export_csv.py          # 写 data/slides.csv
# … 用 Numbers / Excel 编辑 …
python3 import_csv.py          # 把改动写回 DB

# 直接 SQL
sqlite3 data/slides.db
> SELECT page_no, title FROM slides WHERE customer_tag='飞鹤';
> SELECT * FROM slides_fts WHERE slides_fts MATCH '案例 飞鹤';

# Web UI
pip install datasette
datasette data/slides.db
# → 浏览器打开 http://localhost:8001
```

## 4 个固定标签维度

| 列名 | 取值（自由扩展） | 说明 |
|---|---|---|
| `type_tag` | 封面 / 公司介绍 / 案例 / 方法论 / 数据图表 / Section / 结尾 / 其他 | 主类型 |
| `subtype_tag` | 产品介绍 / 项目效果 / 客户痛点 / 团队 / 时间线 / 矩阵 / 流程图 / 金句 / ... | 细分（主要用于案例 / 方法论） |
| `customer_tag` | 蒙牛 / 飞鹤 / 周大福 / 美宜佳 / ... / NULL | 涉及的客户。NULL = 通用 slide |
| `media_tag` | 图文 / 视频 / 表格 / 纯文字 | 媒体形式 |

加上：
- `free_tags`（JSON 数组）—— 任意自由标签（"金句页"、"内部使用"、`needs-review` 等）

## 自动打标管线

```
deck.json → ingest_deck.py
            ├─ HTML 剥 → body_text
            ├─ 选最大字号元素 → title (extracted)
            │  失败则取第一句话 → title (auto-summary)
            ├─ 计算 img/video 数 → media_tag
            ├─ body_text 关键词扫描 → type_tag / subtype_tag
            ├─ body_text 匹配客户名 → customer_tag
            └─ INSERT slides

STORY-PROPOSAL.md → load_stories.py
                    ├─ 按页码范围划分
                    └─ INSERT stories + story_slides

第二轮 → refine_tags.py
        ├─ 从 story 标题反推 customer（"案例：飞鹤" → 成员 customer=飞鹤）
        ├─ 从 story 标题反推 type（"方法论 X" → 成员 type=方法论）
        ├─ 标记孤立 slide → free_tag "needs-review"
        └─ 修垃圾标题（empty / 占位符 / 纯数字）→ "(p42 · 待补标题)"
```

## 加新的 deck

```bash
# 1. 用 keynote-to-html 跑出 deck.json
bash plugin/skills/keynote-to-html/assets/run.sh foo.key out/

# 2. 入库
python3 library/db/ingest_deck.py foo out/deck.json

# 3. 手工写 library/db/data/STORY-PROPOSAL-foo.md
#    （参考已有 STORY-PROPOSAL.md 格式）

# 4. 加载 story
python3 library/db/load_stories.py \
    --deck-id foo \
    --proposal library/db/data/STORY-PROPOSAL-foo.md

# 5. 第二轮 refine + 出报告
python3 library/db/refine_tags.py
python3 library/db/dump_full_review.py
```
