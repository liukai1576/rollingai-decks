---
description: 让 deck 动起来 — 数字滚动、逐字浮现、卡片错落（GSAP 引擎）
---

用户要给某份 deck 加入场动画。参数：$ARGUMENTS（deck 路径或 deck-id，
没给就问）。

1. **先判断 deck 类型**：
   - rolling-deck 产物（含 `<main class="deck" id="deck">`）→ **已内置**
     动画引擎，不要重复安装！只需按需打动画钩子（见第 3 步）。
   - 其他（feishu-deck-h5 / 手写 H5 / keynote 导入）→ 装 slide-anim。
2. 安装 = 读 `plugin/skills/slide-anim/SKILL.md`：拷 4 个 JS 到 deck 的
   `assets/slide-anim/`，把 `assets/inject.partial.html` 粘到 `</body>` 前。
   **装之前先 plan**：SKILL.md 的 STEP 0 要求逐页设计节奏，不要默认一把梭。
3. 按页打钩子：`data-count`（数字滚动）、`data-anim="rise|fade|left|right|scale|blur"`
   （自定义入场）、`.bar-fill`（柱状图生长）。
4. 自测：浏览器翻一遍，确认每页节奏；封面不要动画。
