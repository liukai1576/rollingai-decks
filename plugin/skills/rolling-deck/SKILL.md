---
name: rolling-deck
display_name: RollingAI 风格 H5（粒子地球封面 · 磨砂玻璃）
author: ganyifan
kind: [布局风格]
version: "1.7"
input:  用户的 brief / 大纲 / 内容 (+ 可选：客户 logo)
output: 单文件 index.html（assets/ 同目录），浏览器直接打开放映
triggers:
  - "做一个 RollingAI 风格的 deck"
  - "用粒子地球封面那套模板"
  - "做一个网页版 PPT / HTML 演示"
  - "rolling-deck"
invocation: |
  # Conversational. Claude 复制 plugin/skills/rolling-deck/template.html
  # 到目标位置，按 reference.md 的组件库替换内容、改 brand-rail logo / 封面文字。
  # 不动 <style> 和 <script> —— 那是模板全部价值。
produces_layout_pack: true
---

# Rolling Deck — 高质感 HTML 演示模板

把一份 brief / 大纲 / 内容，套进这套成熟的单文件 HTML 演示框架。产出是
一个 `.html`，浏览器直接打开即放映。

跟 `feishu-deck-h5` 同一类（**布局风格**），不同的是：

| | feishu-deck-h5 | rolling-deck |
|---|---|---|
| 输入 | `deck.json`（结构化数据） | 用户 brief / 大纲 |
| 渲染 | Python `render-deck.py` 拼模板 | 复制 HTML 模板，手动 / LLM 替换 `<section class="slide">` |
| 输出 | 自带 chrome（翻页 / 全屏 / 编辑模式） | 自带 chrome（粒子地球 · 编辑 / 演示双模式 · 导出 PDF） |
| 适用 | Keynote 导入产物、结构化叙事 | 高质感单文件交付物、对客 pitch |

## 何时用

用户要做演示 / PPT / deck / 汇报 / 路演的**网页版（单文件 HTML）**，并且
偏好"暗色磨砂玻璃 + 粒子地球封面"质感时。如果用户明确要 `.pptx`（真正
的 PowerPoint），用 `pptx` skill；如果用户已有 `deck.json` 想换风格，
等 rolling-deck 加上 `render-deck.py` 适配器之后再用。

## 📦 v1.5 — 29 页版式 + Lucide 图标 + URL 直达

ganyifan 在 v1.5 把模板扩成 **29 页**，新增 **13 个通用版式**（除去原
"10× Transformation" 案例的 16 页内容外）：

| # | type | slide-key | 用途 |
|---|---|---|---|
| 17 | 章节过渡 | `tpl-divider` | 大编号水印 + 章节标题 |
| 18 | 目录 | `tpl-agenda` | 两列图标条目 |
| 19 | 全屏大图 | `tpl-full-image` | 整页背景图 + 左下文字 + Ken Burns |
| 20 | 图文分栏 | `tpl-media-split` | 左图右文 + 要点列表 |
| 21 | 多图网格 | `tpl-media-grid` | 三图 + 渐变图注 |
| 22 | 视频 | `tpl-video` | 本地 mp4 / B 站 / YouTube iframe，翻页自动暂停 |
| 23 | 数据图表 | `tpl-chart` | 柱状图生长 + 环形图描边 + KPI 数字滚动（纯 CSS/SVG） |
| 24 | 金句 | `tpl-quote` | 大引号 + 逐字浮现 |
| 25 | 对比 | `tpl-compare` | BEFORE/AFTER 双列 + VS 徽章 |
| 26 | 时间轴 | `tpl-timeline` | 横向划线 + 5 节点 |
| 27 | 团队 | `tpl-team` | 头像 / 姓名 / 角色 / 简介 × 4 |
| 28 | Logo 墙 | `tpl-logos` | 4×2 合作伙伴 |
| 29 | 结尾 | `tpl-end` | 金属扫光 Thank You + 联系方式 |

打开 `assets/index.html` 一页浏览 29 页缩略图，点击直达。

### 新 URL 直达参数

- `template.html?slide=22` —— 直接打开第 22 页（视频页）
- `template.html?slide=22&static=1` —— **静态模式**（关闭入场动画，适合截图 / 嵌入 iframe）

### Lucide 图标库

`assets/vendor/lucide.min.js` 已本地化，1500+ 图标统一描边网格，离线可用：

```html
<i data-lucide="rocket"></i>                              <!-- 任意位置 -->
<span class="ico-chip"><i data-lucide="compass"></i></span>      <!-- 彩色方块 -->
<span class="ico-chip blue|violet|green|fire">…</span>           <!-- 换主题色 -->
<b class="ico-inline"><i data-lucide="mail"></i>文字</b>          <!-- 行内 -->
```

图标名查 https://lucide.dev/icons 。新增图标无需 JS 改动；动态插入后调一次 `lucide.createIcons()`。

### 与 `slide-anim` 的关系

rolling-deck **内置** ganyifan 的 GSAP 入场动画引擎（`assets/vendor/gsap.min.js` + `SplitText.min.js` + `TextPlugin.min.js` + 内联编排脚本）。
**不要**再另外装 `slide-anim` skill —— 会双注册、重复动画。

`slide-anim` skill 是这套引擎的**独立提取版**，用途是把它装到**非 rolling-deck**的 deck（feishu-deck-h5、纯手写 H5、Keynote 导入产物等）上。如果用户已经选 rolling-deck，动画白拿。

## 🛑 头号原则：template 不是故事线，是**风格 + 组件库 + 标准页**

`template.html` 是 "10× Transformation" 这个老 case 的成片。它**不是**你
新 deck 的剧本。它给的是：

- 视觉系统（玻璃、配色、字体、动画）
- 组件库词汇表（见 `reference.md`：cards-3 / route-card / goals-grid /
  approach-grid / tl-weeks / calendar-wrap / synth-band …）
- 三种标准页：`cover-hero`（粒子封面）、`section-head`（章节头）、
  结尾收口
- 交互/动画引擎（粒子地球、翻页、缩放、编辑/演示双模式、导出 PDF）

它**不**给：
- 你 deck 的页数、章节顺序、收口节奏
- 你哪一页用哪个组件
- 你的内容标签（不要硬抄 "5 个 10×"、"3 阶段"、"向内/向外" 这些 10×
  case 的叙事）

**正确动作：**
1. 先读用户的原始素材（SOW / brief / 大纲），梳理出**它自己的故事
   线**——几个章节、每章几个论点、每个论点是什么信息形态。
2. 一页一页问"这页要讲的信息长什么样？"再去 `reference.md` 挑形态
   匹配的组件。
3. 标准页（cover-hero / section-head / 收口）直接套；中间内容页全部
   按素材的信息密度挑组件。
4. **绝对不能反过来**：先看 template 例子哪页好看就照搬版式，再把
   用户内容塞进去填满那个版式。如果原文只有 3 条目标，就用 3-card
   或 4-card grid，**不要**强行编出 4、5 凑齐 `lead-card + 4 cards`
   的 5 格版式。

## 🔍 自检：每张 slide 的空间利用率（必跑）

做完一份 deck 后，跑一次 **check-fill** 看每张 slide 内容有没有撑满 1080
垂直空间。`./assets/check-fill.js` 自带逻辑：

**三种用法（挑一种）：**

```bash
# 1) URL 加 ?check
#    把片段 <script src="assets/check-fill.js"></script> 放进 index.html
#    （或拷贝到 deck 的 assets/ 里），然后访问：
open "http://localhost:8766/index.html?check"
#    控制台自动打印每张 slide 的 fillPct + 汇总
```

```html
<!-- 2) HTML 里加一行，按需调用 -->
<script src="assets/check-fill.js"></script>
<script>RollingDeckCheck.printReport();</script>
```

```js
// 3) 开发者控制台手动 paste
fetch("/plugin/skills/rolling-deck/assets/check-fill.js")
  .then(r => r.text()).then(t => (new Function(t))()).then(() => RollingDeckCheck.printReport());
```

**它会输出什么：**

每张非 cover slide 一行，含：
- `fillPct` —— 内容底边 / 可用 874px 区域
- `verdict` —— `OK` (80-105%) · `缺` (< 80%) · `溢` (> 105%)
- `structure` —— 这页 .slide-fit 的直接子元素链（`div.section-head + div.approach-grid`）
- 汇总 `{ total, ok, underfill, overflow }`

**LKK SOW 这次 check 结果：**
```
12/12 OK · 0 缺 · 0 溢
```
所有 12 张内容页都精准 100%。

**什么时候必跑：**
- 拷模板做完 deck → **跑**
- 改了某张 slide 的内容（加/删卡片、改文案）→ **跑**
- 自定义了某页的 layout（hand-rolled `<div>` 不在标准组件库里）→ **跑**
- 看到底部一片黑或文字溢出 nav bar → **跑**

`缺` 的页面意味着：
- 用了 `<div data-stagger>` 这种**不是标准组件**的容器（不在 `.slide-fit` flex-1 列表里）—— 把它换成 cards-N / approach-grid / hero-stats 等标准组件
- 用了纯文字段落 `<p>` 当主内容 —— 包一层 `<div class="card">` 或者改成 cards-N
- 用了 `align-self: start` 的逃生口但忘了对应内容

`溢` 的页面意味着：
- 单卡 `min-height` 强制过大（旧版本的 workaround，现在可以删掉）
- 内容真的太多了，应该拆成两页

## ✅ 自动垂直填满 — 不要再手动操心了

从 v1.4 起，`.slide-fit` 是 flex 列容器：
- 顶端：`.section-head` / `.goals-head` / `.cover-wrap` / `.tl-section-label` / `.legend` — 自然高度
- 底端：`.synth-band` / `.band` / `.cadence-note` / `.ceo-core` / `.coach-band` / `.goals-foot` / `.end-contact` / `.cover-note` / `.phase-strip` — 自然高度
- **中间主内容块自动抢占剩余垂直空间，内容居中**：`.cards-{2,3,4,6}` / `.hero-stats` / `.goals-grid` / `.approach-grid` / `.tl-weeks` / `.org-stack` / `.calendar-wrap` / 直接 `<ol>`、`<ul>`

**所以现在你不需要：**
- 凑数据塞满版式（goals-grid 5 卡只有 3 条目标也不用编凑）
- 手动 `min-height` 让卡片膨胀
- 在 slide 上加 padding / margin 撑高度

引擎自己 flex 把内容居中到可用区域。短内容看起来"居中漂浮"，长内容自然撑满。

不想被居中、要让某一页内容继续顶到上方？给那个 main content 加一行 inline style：`style="align-self: start; flex: 0 0 auto;"`。

## 只换内容，不动引擎

模板里这些**绝对不要改**（它们是模板的全部价值）：

- `<style>` 里的整套设计系统（玻璃 token、液态金属边、背景、布局、
  `@media print`）
- `<script>` 里的全部逻辑：粒子地球、翻页 / 全屏 / 进度、自动缩放安
  全区、`slide-fit` 包裹、编辑/演示双模式、可编辑内容、导出 PDF

你的工作只有四件：

1. **品牌条 `.brand-rail`**：左 `rolling-logo` 永远是 RollingAI；右
   `client-logo` 换成本次客户的 logo（默认是个文字 `deck-label`，如果
   要做客户交付，建议把它改成客户 logo 的 `<img>`，CSS class 已建好
   `.client-logo`）。
2. **封面 `.cover-hero`**：改 `.cover-hero-title`（主标题）+
   `.cover-hero-sub`（副标题），左上 `.cover-hero-logo` 跟 brand-rail
   同步。粒子地球、背景、左下角布局都不动。
3. **逐张内容页**：每张是
   `<section class="slide" data-slide-key="唯一key" data-screen-label="02 标题">`。
   从 `reference.md` 的组件库里挑版式，填新内容。`data-slide-key` 用
   英文短横线唯一标识；`data-screen-label` 是给人看的"序号 + 标题"。
4. **增删页**：删掉用不上的 `<section>`，复制需要的版式再改。**DOM
   顺序 = 放映顺序**。第一张必须是 `.cover-hero` 封面。

### ⚠️ Splice 时千万别误删的"控制台 DOM 块"

最后一个 `</section>` 和 `</main>` 之间，有一整块**演示控制台 DOM**
（约 35 行，从 `<!-- Controls -->` 注释开始）：

```html
<!-- Controls -->
<div class="deck-progress">…</div>
<div class="deck-controls">↑ pageNo ↓ ⛶ …</div>
<div class="vertical-pager">…</div>
<button class="confirm-toggle" id="confirmToggle">⚙</button>
<aside class="confirm-panel">…模式 / 导出 / 待确认事项…</aside>
<div class="edit-badge">…</div>
```

JS 用 `getElementById("prevBtn")` / `…("modeSwitch")` 这些 id 硬挂。
如果你用 sed / python 批量替换"所有 section"，**很容易把这块和 section
后的内容一起删了** —— 表现：JS 不报错，但翻页 / 模式切换 / 全屏 /
导出全部静默失效，看着就像"播放器没启动"。

**做完 splice 一律跑：**

```bash
bash plugin/skills/feishu-deck-h5/assets/verify-deck-shell.sh <deck-dir>
```

### ⚠️ 加自定义 slide 类时千万别覆盖 `display`

模板用这套机制一次只显示一张幻灯片：

```css
.slide { display: none; }
.slide.active { display: block; animation: reveal .28s ease-out; }
```

当你为某种自定义页（金句页、特殊封面、收口页）写新样式时，**绝对不要**
在 `.slide.<你的类>` 上直接覆盖 `display`：

```css
/* ❌ BAD —— 2-class 同优先级，但你的 CSS 在后面，赢过 .slide.active。
   所有 .slide.quote-page 永远 display:flex，全部堆在一起；
   最后渲染的那张盖在最上面，看起来每一页都是同一张。 */
.slide.quote-page { display: flex; align-items: center; ... }
```

正确写法 —— 把 flex 行为约束在 `.active` 上，让选择器升到 3-class，
胜过 `.slide.active`：

```css
/* ✅ GOOD */
.slide.quote-page { padding: 60px 80px; }   /* 不影响 display 的属性写这里 */
.slide.quote-page.active { display: flex; align-items: center; justify-content: center; }
```

**症状识别：** 翻页按钮还能按，但每页都是同一张内容（通常是 DOM 顺序
最后那张，因为它绘制最晚、覆盖在最上）。看起来像"播放器卡住了"。

它会自动识别 pack 是 rolling-deck，逐一检查 14 个控件 id 是否齐全。
出红字就把模板里那段 Controls 重新塞回 `</main>` 前。

## 工作流程

1. **复制模板**：把 `plugin/skills/rolling-deck/template.html`
   拷到目标位置（一般是 `imports/<deck-id>/render-output-full/index.html`）
   并改名；把 `assets/` 里需要的 logo 一起带上（或换成用户的 logo）。
2. 按上面"四件事"替换内容。
3. **跑 verifier**：`bash plugin/skills/feishu-deck-h5/assets/verify-deck-shell.sh <deck-dir>` —— 必须打印 `==> OK: rolling-deck deck shell wiring looks correct.` 才算合格。
4. **自测**：浏览器打开，翻一遍；试封面拖动 / 缩放；点右下 ⚙ 进编辑
   模式改两个字、点「✓ 完成编辑」；试导出 PDF。

## 入库（让 admin UI 能看到）

完成 HTML 后，跑：

```bash
# 1. 合成 deck.json（一段 Python 提取每个 <section> → slides[]）
python3 plugin/skills/rolling-deck/assets/build-deckjson.py \
  imports/<deck-id>/render-output-full/index.html

# 2. 入库
python3 library/db/ingest_deck.py <deck-id> \
  imports/<deck-id>/render-output-full/deck.json

# 3. 缩略图
python3 library/db/gen_thumbnails.py --deck <deck-id>

# 4. 在 platform/admin/server.py 的 DECK_PATHS 加一行
#    "<deck-id>": REPO / "imports" / "<deck-id>" / "render-output-full",
```

## 内置能力（不用自己写）

- **封面**：canvas 粒子地球——大陆点云、自动自转、拖动旋转带惯性、滚
  轮缩放、鼠标靠近粒子放大、表面喷射粒子、星空 + 太阳系轨道
- **画布**：固定 1920×1080，随窗口等比缩放居中（`--scale`）
- **导航**：底部控制条、右侧翻页、键盘 ↑↓←→、`F` 全屏、顶部进度条
- **安全区**：内容超高时自动 `.slide-fit` 等比缩小
- **双模式**：右下 ⚙ → 演示 / 编辑；编辑模式可直接点改所有文字、改
  待确认事项、「✓ 完成编辑」成稿；localStorage 持久化
- **导出 PDF**：编辑模式面板里「导出 PDF」→ 每页一张

## 让新内容自动获得能力

- 文字一律用**语义标签**：`h2/h3/p/li/td/span` → 自动纳入编辑模式 +
  自动可导出
- 卡片统一用 `.card`（已带磨砂玻璃 + 金属边）。**不要**给卡片设不透
  明背景
- 想分类强调用文字色 / 小徽章，不要回到大色块圆斑（模板刻意走"干净
  玻璃"风）

详见 `reference.md` 的组件库 + 速查。
