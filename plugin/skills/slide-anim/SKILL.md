---
name: slide-anim
display_name: Slide 动起来（数字滚动 + 字逐字浮现 + 卡片错落）
author: ganyifan
kind: [效果, 交互]
version: "0.1"
input:  any deck whose slides use `.slide` / `.slide.active` convention
output: that deck, now with GSAP-driven entrance animations on every page-turn
triggers:
  - "让这个 deck 动起来"
  - "数字从 0 滚到目标"
  - "字逐字浮现"
  - "卡片错落出场"
  - "slide 动起来"
  - "slide-anim"
invocation: |
  # Conversational. Copy the 4 JS files in assets/ into the deck's
  # assets/slide-anim/ dir, then paste assets/inject.partial.html
  # right before </body> of the deck's index.html.
produces_layout_pack: false
description: |
  **入场动画引擎。** 把一份已经渲染好的 deck（feishu-deck-h5 / rolling-deck /
  手写）变成"会动"的 deck —— 翻页时自动编排入场动画：
    · 主标题逐字浮现（SplitText）
    · `.kicker` 从左滑入
    · 卡片组错落上升（cards-3 / hero-stats / goals-grid / ...）
    · 大图 Ken Burns 慢推
    · `[data-count]` / `.stat-num` 数字从 0 滚到目标值（自动保留前后缀
      "10×" / "98%" / "-58%" / "4.8" / "1,200" 都行）
    · `.bar-fill` 柱状图从 0 长出来
    · `.donut-arc` 环形图描边
    · `.timeline-line` 时间轴划线
    · 收尾横幅（`.synth-band` / `.band` 等）从下方淡入
    · `[data-anim="rise|fade|left|right|scale|blur"]` 自定义任意元素

  抽取自 `RollingAI 2026 Vibe / 0-Template / html-deck-template-single.html`
  的 GSAP 引擎，去掉了对那份模板的隐式依赖（`mode === "edit"` 之类的全局
  变量），改成独立 IIFE + 公开 API + MutationObserver 自动 hook，所以不需要
  你改 deck 的 show() 函数。

  跟 `rolling-deck` / `feishu-deck-h5` 同时存在：那两个是布局风格（决定页面
  长什么样），slide-anim 是效果（决定页面怎么进场）。一份 deck 可以同时
  用 layout pack + slide-anim。

  Triggers: "让这个 deck 动起来", "数字滚动", "字逐字浮现", "卡片错落出场"。
---

# slide-anim

把任何 deck 的翻页变成有节奏的入场动画。**4 个 JS + 6 行注入**，不动 deck
原本的逻辑，不动布局，不动文案。

## 🛑 STEP 0 — 先 plan，再装

**不要**直接装上 4 个 JS 就完事。每张 slide 的信息形态不同，节奏也不同 ——
封面跳过、表格淡入、关键阶段要"依次"、3-5 张卡可以"中等节奏"、数字想滚的
要打 `data-count`。直接装意味着所有 slide 都用默认节奏，结果就是该慢的不慢、
该滚的没滚。

**正确流程：**

1. **读 deck 一遍**：每张 slide 用了什么组件（`.cards-3` / `.hero-stats` /
   `calendar-wrap` / `ol` …）、有几条、信息形态是什么（流程 / 并列 / 表格 /
   单一数字）。
2. **逐页提案**：每张 slide 一行，写明 **建议节奏 + 需不需要 `data-count` /
   `data-stagger` / `data-anim`**。封面 + 收尾页明确"跳过"或"用默认"。
3. **等用户确认**这份 plan（可以全盘 OK / 改某几页 / 删某条增强）。
4. **再批量应用**：拷 JS、注入 bootstrap、按 plan 加 data-attr。
5. **浏览器验证**关键页（封面、数字滚动页、依次出场页）。

提案表的标准格式（直接给用户看就行）：

| # | slide key | 内容形态 | 默认动画 | 建议增强 |
|---|---|---|---|---|
| 1 | cover-hero | 封面 | 跳过 | — |
| 9 | effort-pricing | 人天 + 报价表 | 表格淡入 | 6 个金额加 `data-count`，含税总价是高潮 |
| 10 | milestones | 3 阶段卡 | 默认 0.09s 几乎同时 | `data-stagger="0.45"` 依次出场 |
| 11 | ai-boundaries | 5 张边界卡 | 默认错落 | 前 3 张 `data-stagger="0.25"` 中等节奏 |
| ... | ... | ... | ... | ... |

**关键判断原则：**
- **3 张以下的关键阶段卡** → `data-stagger="0.4-0.5"`（强调"依次")
- **3-5 张并列项** → 默认 0.09 即可，或 0.2-0.3 中等
- **6 张以上的密集 grid** → 默认 0.09，不能再慢，否则总时长爆掉
- **单一大数字 / 报价 / KPI** → 一定加 `data-count`
- **范围数字（"3-5天"）** → 不要加 `data-count`（引擎会自动跳过 "3-5" 这种）
- **多行 HTML 结构的 stat-num** → 不要加 `data-count`（引擎也会自动跳过）
- **封面、纯图、纯收口横幅** → 跳过

## 何时用

- 已经用 `rolling-deck` / `feishu-deck-h5` / 手写 H5 做完了一份 deck，想让
  它"动起来" —— 数字从 0 滚到目标、卡片一张张飞上来、标题逐字浮现。
- 路演 / 对客 pitch / 老板汇报，希望 deck 看着比 PowerPoint 更"现代"。
- 一份 deck 想分两个版本（演示版 / 安静版）—— 这套引擎自己识别
  `prefers-reduced-motion` 和 `body.static-mode`，无需双份维护。

**不要用于：**
- 用户只是要"PDF 导出"或截图 —— 动画反而会阻断那种用途（虽然引擎自带
  `beforeprint` 兜底跳到终态，但 PDF 里仍然是终态截屏，加动画没意义）。
- Deck 没有 `.slide` / `.slide.active` 这套 class 约定 —— 引擎依赖
  `.slide` 元素 + `.active` 类切换。所有现有 layout pack 都遵守这套，
  纯手写的小型 demo 可能不遵守。

## 安装（3 步，~30 秒）

```bash
# 1) 把 4 个 JS 拷到 deck 的 assets/slide-anim/
DECK=imports/<your-deck>/render-output-full
mkdir -p $DECK/assets/slide-anim
cp plugin/skills/slide-anim/assets/*.js $DECK/assets/slide-anim/

# 2) 把注入片段贴到 index.html 的 </body> 之前
#    (片段在 plugin/skills/slide-anim/assets/inject.partial.html)
```

**3) 浏览器打开 deck → 翻页 → 动画就有了。** 不需要改任何已有 JS。

## 工作原理

`slide-anim.js` 安装一个 `MutationObserver`，监听 `.slide` 元素的 `class`
属性变化。当任何一张 slide 拿到 `.active` 类时，引擎读取它内部的 DOM，
按"组件指纹"决定每个元素怎么入场（见下表），用 GSAP 时间轴一次性
编排完。

**没有"哪页该有动画"的判断 —— 全部页面统一处理**，遵守这些 skip 规则：

| 条件 | 行为 |
|---|---|
| `prefers-reduced-motion: reduce` | 完全跳过 |
| `body.static-mode` | 完全跳过（用户可手动切静态） |
| `body.edit-mode` | 完全跳过（编辑时不抢 DOM） |
| 当前 slide 有 `.cover-hero` 类 | 跳过（封面通常有自己的粒子动画） |

## 组件 → 动画对照表

下面这些选择器是**自动识别**的，slide 里只要 DOM 命中就会动：

| 选择器 | 动画 | 时序 |
|---|---|---|
| `.section-head h2` · `.goals-head h2` · `.divider-title` · `.quote-text` · `h1` | SplitText 逐字 y=36 → 0 透明度淡入 | 0.0s，stagger 0.016 |
| `.kicker` | 从左 x=-70 + 淡入 | 0.0s |
| `.copy` · `.divider-sub` · `.quote-by` · `.cover-lead` | 上移 y=24 + 淡入 | 0.25s |
| `.tenx-mega` · `.divider-num` | 从右 x=90 + 淡入 | 0.10s |
| `.cards-{2,3,4,6}` · `.hero-stats` · `.goals-grid` · `.agenda-list` · `.media-grid` · `.timeline-nodes` · `.team-grid` · `.logo-wall` · `.chart-kpis` · `.org-stack` · `.phase-strip` · `.incub-milestones` · `.video-side` · `[data-stagger]` | 子元素 y=54 上升，错落 0.09s | 0.30s |
| `.media-frame`（独立大图） | scale 0.94 → 1 淡入 | 0.25s + i×0.12s |
| `.media-bg`（全屏背景图） | scale 1.12 → 1 淡入 + 14s Ken Burns 缓推到 1.06 | 0.0s |
| `.media-overlay > *` | 上移 y=40 + 淡入 | 0.40s + i×0.14s |
| `.stat-num` · `[data-count]` | **数字 0 → 目标值滚动**（保留前后缀） | 0.45s |
| `.bar-fill` | scaleY 0 → 1 | 0.35s，stagger 0.12 |
| `.donut-arc` | stroke-dashoffset 描边到 `data-pct` | 0.45s |
| `.timeline-line` | scaleX 0 → 1 | 0.30s |
| `.synth-band` · `.cadence-note` · `.ceo-core` · `.coach-band` · `.goals-foot` · `.cover-note` · `.band` · `.end-contact` | 上移 y=30 + 淡入 | 0.65s |
| `[data-anim="rise\|fade\|left\|right\|scale\|blur"]` | 对应预设，可加 `data-anim-delay="0.4"` | 自定义 |

## 数字滚动（重点能力）

**最常被问到的就是这一条**，单独说清楚：

任意元素加 `data-count` 属性，或者直接命中 `.stat-num` 选择器，就会从 0
滚到目标值，**自动保留所有非数字前后缀**：

```html
<!-- 都能正确从 0 滚到目标 -->
<span data-count="10×">10×</span>          <!-- 0× → 10× -->
<b   data-count="98%">98%</b>              <!-- 0% → 98% -->
<div class="stat-num">-58%</div>           <!-- -0% → -58% -->
<div class="stat-num">4.8</div>            <!-- 0.0 → 4.8（保留小数位） -->
<span data-count="1,200">1,200</span>      <!-- 0 → 1,200（保留千位逗号占位） -->
<div data-count="¥542,720">¥542,720</div>  <!-- ¥0 → ¥542,720 -->
```

实现细节：用 `\-?\d[\d,]*\.?\d*` 提取第一个数字段，记下前缀（`¥` / `-`）
和后缀（`%` / `×` / `万` ...），动画结束后把 `textContent` 还原成原始
字符串（不仅是动画终值），避免 toFixed 把 "1,200" 变成 "1200"。

## 手动控制 — `[data-anim]`

引擎已识别的组件不需要标注。但如果你想给一个**自定义元素**也加入场动画，
加 `data-anim` 属性：

```html
<div data-anim="rise">       <!-- 从下方 y=46 升起 + 淡入 -->
<div data-anim="left">       <!-- 从左 x=-70 滑入 -->
<div data-anim="right">      <!-- 从右 x=70 滑入 -->
<div data-anim="scale">      <!-- 从 scale 0.86 放大 -->
<div data-anim="blur">       <!-- 从 blur(14px) 退焦 -->
<div data-anim="fade">       <!-- 纯淡入 -->

<!-- 也可以加延时（秒） -->
<div data-anim="rise" data-anim-delay="0.6">
```

如果一个容器没命中默认 group 选择器，但你想让它的子元素错落入场：

```html
<div data-stagger>  <!-- 子元素自动 stagger 0.09s 上升 -->
  <article>…</article>
  <article>…</article>
</div>
```

**调节节奏（"依次出场" vs "几乎同时"）：**

默认所有 group（`.cards-3` / `.hero-stats` / `.goals-grid` …）的子元素间隔
是 `0.09s`，看起来像"一组协调入场"。如果想要每张卡**清晰独立地依次落地**，
把 `data-stagger` 加上数值（秒）：

```html
<!-- 默认快节奏（0.09s 间隔） -->
<div class="cards-3">…</div>

<!-- "依次"节奏（每张卡 0.45s 间隔，前一张落定后后一张才开始） -->
<div class="cards-3" data-stagger="0.45">…</div>

<!-- 超长仪式感（0.8s 间隔，适合 3 张以下的关键阶段卡） -->
<div class="cards-3" data-stagger="0.8">…</div>
```

可选 `data-stagger-delay="0.6"` 改这组开始的时机（默认 `0.3s` 进入 slide
时间线后启动）。两个属性都加在 **group 容器**上，不是子卡。

## 公开 API（高级用法）

注入后，`window.RollingSlideAnim` 暴露这几个方法：

```js
RollingSlideAnim.animate(slideEl)  // 手动触发某张 slide 的动画
RollingSlideAnim.autoHook()        // 注入片段已经替你调用了；可重复（idempotent）
RollingSlideAnim.finish()          // 把当前在播的时间线跳到终态（导出 PDF 前会自动调用）
RollingSlideAnim.enable() / .disable()
RollingSlideAnim.config({ countDuration: 1.4, ... })  // 改默认 tuning
```

把 `body` 加 `static-mode` 类可以**全局关闭**动画（适合用户想要安静浏览）。

## 文件清单

```
plugin/skills/slide-anim/
├── SKILL.md                                 (本文件)
└── assets/
    ├── gsap-3.13.0.min.js                   (60 KB · 离线 GSAP 引擎)
    ├── gsap-splittext-3.13.0.min.js         (8 KB · 字逐字拆分插件)
    ├── gsap-textplugin-3.13.0.min.js        (11 KB · 文本动画插件)
    ├── slide-anim.js                        (10 KB · 自定义编排引擎)
    └── inject.partial.html                  (片段：5 行 script + 1 行 autoHook)
```

**全部离线**，不依赖任何 CDN，断网也能跑。GSAP 3.13 的"全插件免费"
许可，源代码注释里有原始许可证文本。

## 边界与限制

- 引擎假设 deck 用 `.slide` + `.slide.active` 切换页面。`rolling-deck` 和
  `feishu-deck-h5` 都遵守这套约定；纯手写的 demo 如果用别的类名（`.page`
  / `.is-current`），先把它们重命名再装这个 skill。
- 不会**反向播放**离开页的动画 —— 当前 slide 直接消失，新 slide 入场。
  GSAP 时间轴只编排"进"，不编排"出"。
- 长 deck（>60 页）每次翻页要重建一次 timeline，性能上完全没问题；但如果
  你的 slide 内含 1000+ 个 children 需要 stagger（极端情况），可以
  `RollingSlideAnim.config({ groupSel: "..." })` 缩小观察范围。
- 跟"安静浏览"诉求兼容：`prefers-reduced-motion` 自动跳过；用户在 body
  加 `static-mode` 类可手动切。

## 触发与组合

| 用户说 | 该做 |
|---|---|
| "让这个 deck 动起来" / "加入场动画" / "数字滚动" | 装这个 skill |
| "做一个新 deck"（暗含视觉效果） | 先 `slide-design` 选 layout pack 做出页面 → 再装 `slide-anim` |
| "动画太多" / "我演示时不想要动画" | 教用户 `<body class="static-mode">` |
| "改一下动画时长 / 缓动" | 改 inject 片段里 `RollingSlideAnim.config(...)` |
