# platform/admin/ — Slide & Story 管理 UI

FastAPI 后端 + 单文件静态前端，给 `library/db/data/slides.db` 当
管理控制台。

## 启动

```bash
pip install -r platform/admin/requirements.txt
python3 platform/admin/server.py
```

打开 → http://127.0.0.1:8123

## 架构

```
┌───────────────────────────────────────────────┐
│  Browser ── http://localhost:8123             │
│                                               │
│    static/index.html  (Alpine.js via CDN)     │
│         │                                     │
│         ▼  fetch(/api/...)                    │
└─────────┼─────────────────────────────────────┘
          │
┌─────────▼─────────────────────────────────────┐
│  server.py  (FastAPI, port 8123)              │
│  ├─ /api/slides     列表 / 过滤 / 全文搜       │
│  ├─ /api/slides/:id 详情 + 多 story 关联        │
│  ├─ PUT /api/slides/:id  改 tag                │
│  ├─ /api/stories    列表 / 创建 / 更新 / 删除   │
│  ├─ /api/stats      标签维度统计                │
│  ├─ /api/.../export-deck   预留：再生成 deck   │
│  ├─ /decks/:deck_id/*   read-only deck 文件代理 │
│  └─ /                  静态前端                 │
│         │                                     │
│         ▼ sqlite3                             │
└─────────┼─────────────────────────────────────┘
          │
       library/db/data/slides.db
```

## 现在做到了什么

- **左侧栏过滤**：类型 / 客户 / 媒体 / needs-review，点一下即过滤
- **顶部全文搜**：FTS5 across title + body_text
- **Slides 表**：62 条全部，带 chip 风格的 tag 染色
- **点 slide → 抽屉**：iframe 预览实际渲染 + 标签 inline 编辑 + 保存
- **Stories 视图**：故事卡片网格，点开看成员列表（目前是 alert，下次做成抽屉）
- **统计 pill**：顶部实时显示总数 / 待复核数

## 还没做（hooks 已留好）

- `POST /api/stories/{id}/export-deck` —— 已写桩，返回 deck.json
  scaffold，下一步真的渲染 → 调用 `plugin/skills/feishu-deck-h5/
  deck-json/render-deck.py`
- 多 slide 选中 → 合并成新 story
- "再生成"功能：选 slide → 调 `slide-redesign` 或 `slide-design`
- Story 详情抽屉（目前是 alert）
- 拖拽改 story 内 slide 顺序

## API 速查

```bash
# 列表（支持任意组合过滤）
curl 'http://localhost:8123/api/slides?type_tag=案例&customer_tag=飞鹤'
curl 'http://localhost:8123/api/slides?search=矩阵'
curl 'http://localhost:8123/api/slides?needs_review=true'

# 详情
curl 'http://localhost:8123/api/slides/kangshifu/slide-006'

# 改标签
curl -X PUT 'http://localhost:8123/api/slides/kangshifu/slide-006' \
  -H 'Content-Type: application/json' \
  -d '{"type_tag":"案例","customer_tag":"飞鹤","free_tags":["金句"]}'

# Story
curl 'http://localhost:8123/api/stories'
curl 'http://localhost:8123/api/stories/kangshifu/case-feihe-ai-nutritionist'

# 新 story（预留）
curl -X POST 'http://localhost:8123/api/stories' \
  -H 'Content-Type: application/json' \
  -d '{"id":"kangshifu/my-cut","title":"自定义节选","slide_ids":["kangshifu/slide-001","kangshifu/slide-038"]}'
```

OpenAPI doc: http://localhost:8123/docs （FastAPI 自动生成）

## 部署 / 多 deck 拓展

`server.py` 顶部 `DECK_PATHS` dict 加新条目：

```python
DECK_PATHS: dict[str, Path] = {
    "kangshifu": REPO / "imports" / "RollingAI分享-康师傅" / "render-output-full",
    "other-deck": REPO / "imports" / "其他客户" / "render-output-full",
}
```

将来如果 deck 数量多了，挪到一张 `decks` 表里读。

## Trouble-shooting

- **打不开 http://localhost:8123**：检查 port 是否被占用 →
  `lsof -i :8123`；改端口在 `server.py` 末尾 `uvicorn.run(...)`
- **/api/slides 返回 500**：DB 不存在。先跑
  `python3 library/db/ingest_deck.py kangshifu .../deck.json`
- **iframe 预览全黑 / 404**：检查 `DECK_PATHS` 路径是否指向有
  `index.html` 的目录
