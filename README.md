# RollingAI DeckBuilder

把 Keynote / PDF / 文案变成 1920×1080 的 HTML deck，按"小故事"为单位入库、检索、合并、再生。

仓库目录：

| 目录 | 是什么 |
|---|---|
| [`plugin/`](plugin/) | Claude Code 插件 + Skill。生成 / 导入 / 校验 deck 的所有脚本 |
| [`library/`](library/) | 故事库（纯文件系统，无数据库）。每个 `stories/<id>/` 是一个 4-5 页的小故事 |
| [`platform/`](platform/) | 管理平台 Web App（Vite + React，纯静态）。左侧标签/搜索，右侧 block view 多选 |

---

## 1. 致敬

本项目的渲染器 `feishu-deck-h5` 直接 fork 自我同事 **杰森** 的 **[`feishu-deck-h5`](https://github.com/FuQiang/feishu-deck-h5)**——一个简洁、扎实的 16:9 HTML deck 渲染框架。它给了我们：

- 一套稳定的 present-mode chrome（← → 翻页 / F 全屏 / 进度条 / scroll mode）
- 一套基于 design tokens 的排版系统（字体 / 字号 / 间距 / 颜色变量化）
- 一套可组合的 layout 词汇表（`cover` / `agenda` / `section` / `content` / `stats` / `quote` / `image-text` / `table` / `flow` / `logo-wall` / `arch-stack` / `end` / `replica` / `raw`）

我们在它的基础上做了：

- 重命名品牌资产（飞书 logo / wordmark → RollingAI）
- 增加 `raw` layout 的逐元素绝对定位（保留 Keynote 原始排版）
- 增加 lazy-video（按当前页 ±1 加载视频，否则释放解码器槽位）
- 增加自动取首帧 poster
- 修复了 stagger-reveal animation 与 inline `opacity:` 冲突的关键 bug

**Hat tip 🎩 to 杰森。**

这个项目某种意义上是 **飞书团队** 和 **RollingAI 团队** 共同进化的结晶——一边把 16:9 HTML deck 的渲染底座打磨得越来越稳，一边把 AI 原生的内容生产链路接上去。代码是技术合作的载体，但更重要的，它也是 **两支队伍长期友谊的象征**。👬

---

## 2. 版本迭代日志

完整 changelog 见 [`plugin/CHANGELOG.md`](plugin/CHANGELOG.md)。本节做高维度回顾——**只记录 skill / 渲染器代码变更，不记录单个 deck 的内容微调**。

### v0.16 · 当前 — 架构拆分 + 多媒体 / 多版式文字
- **Plugin 拆分为 4 个解耦 skill**（见下文）。中间格式统一为 `deck.json`
- Keynote `.key`（Keynote 14.5+ 的 zip 单文件格式）原生支持，UTF-8 文件名修复
- 多 run 文字提取（同一 text box 内多字体 / 字号 / 颜色）
- Lazy-video + 自动 poster + 用户首次交互后自动 unmute
- AppleScript 通过 `--doc-name` 精准定位文档（之前会撞到 front document）

### v0.13 – v0.15 · 重设计系统 + 完整 62 页跑通
- 引入 `redesigns/slide-NN.html` 机制：不修改抽取脚本，用纯 HTML 替换坏页
- 强制 verbatim 规则：redesign 文案必须从源 Keynote 逐字搬运
- IWA 解析器：通过 keynote-parser 反查每个素材的真实尺寸 / 位置（绕开 AppleScript 不准的 bbox）

### v0.10 – v0.12 · CRITICAL FIX
- **opacity bug 根因定位**：feishu-deck-h5 的 stagger-reveal CSS 用 `animation` 强制 `opacity: 1`，静默覆盖所有 inline 透明度。修复后 22% / 30% 半透明叠层终于正常显示
- 容器型 shape（banner / pill / card 底框）保留为默认半透圆角
- `other:line`（Keynote 分隔线）保底渲染成 2px 细线

### v0.6 – v0.9 · 母版 / 透明度 / 形状
- 抽取 master / base-layout 子项并先于 slide 自身渲染（模板背景、页脚）
- opacity 从 Keynote 抽出，正确反映到 CSS
- shape + image 同 bbox 自动识别，合并为单一光栅 crop（恢复 Keynote 的"风格化图片占位符"视觉）

### v0.3 – v0.5 · 字体 / 形状 / 命中
- font-weight / font-style 从字体名后缀解析（`-Bold`, `-Black`, `-Light`, `_SC_Black`...）
- **CRITICAL FIX**：font-family stack 用单引号包裹（v0.4 用双引号导致样式属性被浏览器在第一个内嵌双引号处截断，丢字号 / 字重）
- 形状渲染 fill + border-radius + rotation

### v0.1 – v0.2 · 雏形
- AppleScript 遍历 iWork 元素，TSV 输出
- `build.py` 组合绝对定位 HTML
- PNG raster 兜底（处理 AppleScript 不支持的渐变 / 复杂填充）

---

## 3. 用户手册：有哪些 Skill 可以用

四个 skill 全部解耦，通过 `deck.json` 串联。安装：

```bash
bash plugin/install.sh   # 符号链接到 ~/.claude/plugins/
```

### 3.1 `keynote-to-html` — Keynote 导入

把 `.key` 文件转成 `deck.json`（每个非跳过的 slide 一条 `raw` 记录）+ 一份可直接打开的 `index.html`。

```bash
bash plugin/skills/keynote-to-html/assets/run.sh \
  customer-pitch.key out/ \
  [--limit 10] \
  [--rasters-dir DIR] \
  [--pdf PATH]
```

| 参数 | 说明 |
|---|---|
| `--limit N` | 只跑前 N 页（debug 用） |
| `--rasters-dir` | 给 `build.py` 提供 PNG raster 兜底目录（处理无法用 CSS 还原的渐变形状） |
| `--pdf` | 提供与 `.key` 同源的 PDF，用作 verbatim 校对 |

**触发词**："把这个 Keynote 转成 HTML" / "import .key 文件"

### 3.2 `slide-redesign` — 选择性重绘

对 `deck.json` 中指定的 slide，用手写 HTML 替换。适用于：dashboards / 复杂卡片网格 / 自定义 hero 页 / Keynote 难以还原的版式。

```bash
bash plugin/skills/slide-redesign/assets/apply.sh \
  out/deck.json out/redesigns/ [out/new-deck.json]
```

文件命名约定：

- `redesigns/slide-NN.html` — `NN` 是 1-based PDF 页码
- `redesigns/slide-NNN.html` — `NNN` 是 zero-padded slide key（如 `slide-024`）

**铁律**（见 [`slide-redesign/SKILL.md`](plugin/skills/slide-redesign/SKILL.md)）：

1. 文字必须从源 Keynote **逐字搬运**，不准编辑 / 总结 / 编造
2. 不准凭空发明 icon / emoji / 箭头
3. CSS 用 `data-slide-key="slide-NNN"` 精确 scope
4. 排版 / 配色 / 字体可以自由设计
5. **必须有 PPT 感**：title ≥ 56-88px，正文铺满 ≥ 80% 宽 + ≥ 70% 高

**触发词**："改 deck 第 24 页" / "重设计这张"

### 3.3 `feishu-deck-h5` — 渲染器（很少直接调用）

`deck.json` → 完整自包含的 HTML deck。其他 skill 默认自动调它，但你也可以手动：

```bash
python3 plugin/skills/feishu-deck-h5/deck-json/render-deck.py \
  out/deck.json out/
open out/index.html
```

产物：

- `index.html` — 内联所有 slide HTML
- `_renderer/` — 拷贝过来的 CSS + JS（present-mode chrome / 键盘导航 / lazy-video）
- `assets/` — 原始素材（由 `keynote-to-html` 写入）

### 3.4 `slide-design` — 新 slide 创作（scaffold）

为 deck 添加全新的 slide（不来自 Keynote）。**当前是占位 scaffold**，pipeline 脚本未实现；架构上保留位置。

### 典型工作流

```bash
# 1. 导入 Keynote
bash plugin/skills/keynote-to-html/assets/run.sh \
  customer-pitch.key out/

# 2. 识别坏页，手写 HTML
$EDITOR out/redesigns/slide-24.html
$EDITOR out/redesigns/slide-40.html

# 3. 应用重设计（覆盖 out/deck.json，留 .bak 备份）
bash plugin/skills/slide-redesign/assets/apply.sh \
  out/deck.json out/redesigns/

# 4. 重新渲染
python3 plugin/skills/feishu-deck-h5/deck-json/render-deck.py \
  out/deck.json out/

# 5. 启动本地服务器看效果
bash out/serve.sh   # 默认 http://localhost:8765
```

---

## 4. 智能体架构

`deck.json` 是核心枢纽——所有 skill 要么生产它，要么消费它，**没有任何 skill 在运行时依赖另一个 skill**。

### 4.1 数据流图

```
                    ┌────────────────────────────┐
                    │   feishu-deck-h5          │  ← 渲染器 + 设计系统
                    │   deck.json → index.html   │     （fork 自 feishu-deck-h5）
                    └─────────────▲──────────────┘
                                  │ deck.json
        ┌─────────────────────────┼─────────────────────────┐
        │ deck.json               │ deck.json               │ deck.json
        │                         │                         │
   ┌────┴──────────┐    ┌─────────┴────────┐    ┌───────────┴────────┐
   │ keynote-to-   │    │  slide-design    │    │  slide-redesign    │
   │ html          │    │  (scaffold)      │    │                    │
   ├───────────────┤    ├──────────────────┤    ├────────────────────┤
   │ .key → deck   │    │  user prompt →   │    │  deck.json +       │
   │ .json (1:1    │    │  new slide entry │    │  redesigns/*.html  │
   │ 抽取)         │    │  appended to     │    │  → deck.json       │
   │               │    │  deck.json       │    │  (指定 slide 替换) │
   └───────┬───────┘    └──────────────────┘    └──────────┬─────────┘
           ▲                                                ▲
           │                                                │
        .key 文件                                       手写 HTML 文件
   (AppleScript + IWA 解析)                         (人工设计判断)
```

### 4.2 设计原则

| 原则 | 意思 |
|---|---|
| **单一可信源 = `deck.json`** | 所有 skill 读 / 写它；renderer 是最终消费者 |
| **运行时零耦合** | 每个 skill 自带 assets 和脚本，只通过磁盘上的 `deck.json` 通信 |
| **renderer 是 flag，不是硬依赖** | `keynote-to-html --renderer <path>` 默认指向 `feishu-deck-h5`，但任何兼容的渲染器都能换 |
| **Redesign 是内容 / 排版覆盖，不是 extractor 补丁** | 如果 Keynote 导入结果难看，去写 `slide-NN.html`（设计工作），而不是改 `keynote-to-html` 的 Python（工程工作）。这条边界让导入器保持简洁，让设计判断留在 HTML/CSS 里 |
| **AI 辅助 + 人工拍板** | 导入后 Claude 提建议，UI 上人工确认；不做端到端自动化 |
| **小故事 = 4-5 页** | 复用粒度是叙事单位，不是版面单位 |

### 4.3 Skill 与 Agent 的关系

```
       ┌────────────────────────────────────┐
       │  Claude Code (Anthropic Agent SDK) │
       └──────────────┬─────────────────────┘
                      │ 触发词识别
                      ▼
       ┌──────────────────────────────┐
       │  SKILL.md (per-skill prompt) │  ← Claude 读这个文件来决定
       │  - 触发词                    │     何时调用、调用什么
       │  - 调用范例                  │
       │  - 输出契约                  │
       │  - 边界规则                  │
       └──────────────┬───────────────┘
                      │ Bash tool
                      ▼
       ┌──────────────────────────────┐
       │  assets/run.sh / apply.sh    │  ← 真正干活的脚本
       │  + Python / AppleScript      │     纯命令行，可独立运行
       └──────────────┬───────────────┘
                      │ 写 deck.json
                      ▼
       ┌──────────────────────────────┐
       │  下游 skill 或 renderer      │
       └──────────────────────────────┘
```

每个 skill 都是"一份 `SKILL.md` + 一坨脚本"：

- `SKILL.md` 是 Claude 读的"使用说明"——什么时候调它、调用边界、输出格式
- `assets/` 是真正的脚本——脱离 Claude 也能独立跑（CI / 别人 fork 后 cron）

所以这个仓库既是 **Claude Code 插件**（在对话中通过自然语言触发），也是 **独立 CLI 工具集**（命令行直接用）。

---

## 快速开始

```bash
# 1. 安装插件到 Claude Code（开发模式，符号链接到本地）
bash plugin/install.sh

# 2. 启动管理平台（开发模式）
cd platform/web && npm install && npm run dev

# 3. 在 Claude Code 里用 skill（自然语言触发）
# 「把 ~/Decks/customer.key 转成 HTML」
# 「改 deck 第 24 页」
```

## 状态

- ✅ `keynote-to-html` — 在 60+ 页的实际 deck 上跑通
- ✅ `slide-redesign` — 已重绘十几页
- ✅ `feishu-deck-h5` — 渲染器稳定
- 🚧 `slide-design` — scaffold，pipeline 待实现
- 🚧 `library/` — 入库格式已定，搜索 / 合并 UI 开发中
- 🚧 `platform/` — 基础 React app 已起，多选合并触发再生待接入

## License

MIT（renderer 部分继承 feishu-deck-h5 原作者的 license 条款）
