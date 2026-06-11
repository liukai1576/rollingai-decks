---
description: 这套系统能干什么 — 列出全部 deck 能力和对应入口
---

用户想了解这个工作台有哪些能力。做两件事：

1. 跑 `python3 plugin/skills/registry.py` 拿到当前全部 skill 清单（实时的，
   不要凭记忆列）。

2. 用人话输出一张「我能帮你做什么」的地图，按**用户想干的事**组织（不要
   按内部 skill 名组织），每条给：一句话说明 + 对应斜杠命令或说法。结构：

   **做一份新 deck** → `/deck-new`（引导选模板：rolling-deck 粒子地球风 /
   feishu-deck-h5 结构化渲染）
   **Keynote/PPT 转网页版** → `/deck-keynote`
   **复用历史 deck 的页面拼新 deck** → `/deck-splice` 或 admin 购物车
   **让 deck 动起来**（数字滚动/逐字浮现/卡片错落）→ `/deck-animate`
   **deck 入库**（进管理平台：标签+缩略图+故事）→ `/deck-ingest`
   **改某一页 / 重设计单页** → 直接描述需求（slide-redesign skill）
   **管理平台** → `cd platform/admin && python3 -m uvicorn server:app`，
   浏览 / 搜索 / 打标 / 购物车拼接全在里面
   **素材检索** → `pick.py --keywords … --customers …` 按标签/全文搜历史 slide

3. 最后提醒：直接用自然语言说需求也行（"把康师傅那几页拼到新 deck 里"），
   不一定要记命令。
