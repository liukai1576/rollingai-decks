---
description: deck 入库 — 进管理平台（自动标签 + 缩略图 + 可拼接可检索）
---

用户要把一份 deck 入库到管理平台。参数：$ARGUMENTS（deck-id 或路径，
没给就 `ls imports/` 列出来问）。

完整三步（顺序固定）：

1. **deck.json**（没有的话生成）：
   - rolling-deck 产物 → `python3 plugin/skills/rolling-deck/assets/build-deckjson.py imports/<id>/render-output-full/index.html`
   - feishu-deck-h5 产物自带 deck.json，跳过
2. **入库**：`python3 library/db/ingest_deck.py <id> imports/<id>/render-output-full/deck.json`
   （自动打粗标签；重复跑安全——已有人工标签不会被洗掉）
3. **缩略图**：`python3 library/db/gen_thumbnails.py --deck <id>`

之后 admin 自动发现该 deck（无需注册）。收尾时提示用户：
- admin 里可精修标签（类型/客户/媒体/自由标签）
- 视频页如有"该出声的"，打 `有声视频` 自由标签
- 可以建故事（页码区间分组），购物车整组复用
