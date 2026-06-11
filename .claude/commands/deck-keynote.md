---
description: Keynote (.key) 转网页版 deck — 解包、重建 slides、可入库
---

用户要把 Keynote 文件转成网页版 deck。参数：$ARGUMENTS（.key 文件路径，
没给就问）。

1. 读 `plugin/skills/keynote-to-html/SKILL.md`，按它操作。核心入口：
   ```bash
   bash plugin/skills/keynote-to-html/assets/run.sh "<path>.key" "imports/<deck-id>/render-output-full" [--limit N]
   ```
2. deck-id 用英文短横线命名，跟用户确认。
3. 转完先浏览器打开自测（翻页、图片、视频）。
4. 问用户要不要入库（标签 + 缩略图 → admin 可见）；要的话走 /deck-ingest 流程。
