---
name: rolling-deck
display_name: RollingAI 风格 H5（粒子地球封面 · 磨砂玻璃）
kind: [布局风格]
version: "1.0"
input:  用户的 brief / 大纲 / 内容 (+ 可选：客户 logo)
output: 单文件 index.html（assets/ 同目录），浏览器直接打开放映
triggers:
  - "做一个 RollingAI 风格的 deck"
  - "用粒子地球封面那套模板"
  - "做一个网页版 PPT / HTML 演示"
  - "rolling-deck"
invocation: |
  # Conversational. Claude 复制 plugin/skills/rolling-deck/assets/template.html
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

## 最重要的原则：只换内容，不动引擎

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

## 工作流程

1. **复制模板**：把 `plugin/skills/rolling-deck/assets/template.html`
   拷到目标位置（一般是 `imports/<deck-id>/render-output-full/index.html`）
   并改名；把 `assets/` 里需要的 logo 一起带上（或换成用户的 logo）。
2. 按上面"四件事"替换内容。
3. **自测**：浏览器打开，翻一遍；试封面拖动 / 缩放；点右下 ⚙ 进编辑
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
