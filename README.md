# RollingAI DeckBuilder

做 deck（PPT / 演示 / pitch / 汇报）的工作台。把 Keynote / PDF / 一段文案变成
**1920×1080 的单文件 HTML deck**，再按"页 / 小故事"为单位**入库、检索、拼接、再生**。

> **最简单的用法：** 在 Claude Code 里用自然语言描述需求——"帮我做个 pitch deck"、
> "把这个 Keynote 转成网页"、"把立白那几页搬过来"，Claude 会自动调用对应 skill，
> 无需记忆命令。详见 [§2 上手场景](#2-上手从你的场景出发新人从这里开始)。

项目由这几部分组成：

| 目录 | 是什么 | 给谁用 |
|---|---|---|
| [`plugin/`](plugin/)（构建器） | 16 个 skill + 渲染器：生成 / 导入 / 拼接 / 校验 deck | 做 deck 的人（在 Claude Code 里） |
| [`platform/admin/`](platform/admin/)（管理端） | slides.db 的 Web 控制台：检索、改标签、购物车拼 deck、入库 | 找素材 / 管资产的人（浏览器里） |
| [`library/`](library/)（资产库） | slides.db（SQLite + 全文搜）+ 入库 / 缩略图 / 查重 / 标签工具 | 底座，构建器和管理端都连它 |

它们通过一个中间格式 **`deck.json`** 串起来——构建器生产它，资产库消费它，
管理端展示它。**彼此在运行时不硬依赖。**

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

## 2. 上手：从你的场景出发（新人从这里开始）

绝大多数情况，**在 Claude Code 里用自然语言描述需求**即可，Claude 会自动调用对应
skill；也可以使用 `/deck-` 开头的 slash 命令。按你要做的事对号入座：

| 我想…… | 说这句话 / 命令 | 背后是 |
|---|---|---|
| **做一个新 deck** | "帮我做份 pitch deck 讲 X" · `/deck-new` | 先选模板（rolling-deck / feishu），再填内容 |
| **改一个已有的 deck** | "重新设计第 24 页" · "把这页改成…" | slide-redesign |
| **从 Keynote 导入 deck** | "把这个 .key 转成网页" · `/deck-keynote` | keynote-to-html |
| **管理 / 入库 / 搜索 deck** | "把这份 deck 入库" · `/deck-ingest`，或开管理端浏览器搜 | deck-ingest + admin（:8123） |
| **复用历史 deck 的某几页** | "把立白那 6 张搬过来" · `/deck-splice` | deck-splice |
| **让 deck 动起来** | "给这页加数字滚动 / 逐字浮现" · `/deck-animate` | slide-anim |
| **了解系统能力** | "这套系统都能做什么" · `/deck-help` | — |

> ⚠️ **做新 deck 的第一步永远是选模板**（三种风格，见 [§3 构建器](#3-构建器plugin)）。
> Claude 会列选项让你选，默认 **rolling-deck**（粒子地球那套）。

三个入口，按使用习惯选择：

- **Claude Code 自然语言**（最常用）—— 上表所有操作都可由此触发。
- **管理端浏览器**（找素材 / 拼 deck）—— `python3 platform/admin/server.py` →
  http://127.0.0.1:8123 ，按标签 / 全文搜、预览每页、勾选 slide → 购物车拼进某份 deck。
- **命令行 CLI**（跑脚本 / 接 CI）—— 每个 skill 的 `assets/` 都能独立跑，例如入库三连：
  ```bash
  python3 library/db/ingest_deck.py <deck-id> imports/<deck-id>/render-output-full/deck.json
  python3 library/db/gen_thumbnails.py --deck <deck-id>
  # admin UI 自动发现 imports/ 下的 deck，无需注册
  ```

---

## 3. 构建器（`plugin/`）

Claude Code 插件，也是一套独立 CLI 工具集。安装（开发模式，符号链接到 `~/.claude/`）：

```bash
bash plugin/install.sh
```

### 3.1 三种 deck 风格（layout pack）——做新 deck 先选这个

| pack | 作者 | 大概长什么样 | 适合做什么 |
|---|---|---|---|
| **rolling-deck**（默认推荐） | ganyifan | 深色磨砂玻璃质感，封面是一颗会转的粒子地球，自带 29 种现成版式和动画 | 给客户的正式 pitch、追求质感的交付物 |
| **rolling-deck-v2**（影像玻璃） | ganyifan | 同款风格，但页面大量用实景照片叠在玻璃上，更有电影感 | 想用照片、要画面感的 deck |
| **feishu-deck-h5** | 杰森 | 更规整、偏商务的排版风格 | 从 Keynote / PDF 导入进来的内容 |

> 🛑 **注意**：rolling-deck 模板里那套样式和交互代码不要改动——它正是模板的价值所在。
> 做新 deck 时只替换内容即可，完成后跑一下自检脚本看排版有没有撑满。

### 3.2 全部 skill（按用途分组）

> skill 就是这套系统能帮你做的一件件事。下面按"你想干什么"列出来，
> 平时在 Claude Code 里用自然语言说一声，对应的 skill 就会自动跑起来。

| 用途 | skill | 作者 | 它帮你做什么 |
|---|---|---|---|
| **导入** | `keynote-to-html` | liukai | 把 Keynote（`.key`）文件转成能在浏览器直接打开的网页 deck，保留原来的排版 |
| **新建** | `slide-design` | liukai | 从一句话或一份大纲，生成全新的页面 / 整份 deck（开发中） |
| **拼接** | `deck-splice` | liukai | 把以前做过的 deck 里某几页，原样搬进新 deck——图片、视频都跟着过来 |
| **改单页** | `slide-redesign` | liukai | 把某一页重新排版设计（文字照搬原稿，不改写内容） |
| **加动画** | `slide-anim` | ganyifan | 给页面加动效：数字滚动、文字逐字浮现、卡片依次出现 |
| **渲染** | `feishu-deck-h5` | 杰森 | 把内容生成最终的网页 deck（多数时候别的功能会自动用到它，不用手动碰） |
| **入库** | `deck-ingest` | liukai | 把做好的 deck 收进资料库：自动打标签、出预览图，之后能搜索、能复用 |
| **缩略图** | `thumb-gen` | liukai | 为每一页生成预览小图，方便在管理端翻看 |
| **标签** | `tag-refine` | liukai | 整理、统一资料库里的标签 |
| **瘦身** | `slim-deck` | liukai | 压缩 deck 体积、去掉用不到的图片视频，方便发送和保存 |
| **查重** | `dedup-probe` / `slide-fingerprint` / `asset-fingerprint` | liukai | 找出不同 deck 里重复或雷同的页面和素材 |

> 不确定用哪个，运行 `python3 plugin/skills/registry.py` 查看完整 skill 清单，避免自行发明流程。

### 3.3 渲染器内核

`plugin/_player/`（渲染调度 `render.py`）+ `_lib/` + `_spec/`。`deck.json` →
`index.html`（内联全部 slide）+ `_renderer/`（present-mode chrome / 键盘导航 /
lazy-video）+ `assets/`（原始素材）。手动渲染：

```bash
python3 plugin/skills/feishu-deck-h5/deck-json/render-deck.py out/deck.json out/
```

---

## 4. 管理端（`platform/admin/`）

FastAPI（:8123）+ 单文件 Alpine 前端，作为 `library/db/data/slides.db` 的控制台。
**这是日常找素材 / 拼 deck 的主入口。**

```bash
pip install -r platform/admin/requirements.txt
python3 platform/admin/server.py        # → http://127.0.0.1:8123
```

功能：

- **左栏过滤 + 顶部全文搜**：类型 / 客户 / 媒体 / needs-review 一键筛选；FTS5 搜标题 + 正文
- **点 slide → 抽屉**：iframe 预览实际渲染 + 标签 inline 编辑保存
- **购物车拼 deck**：勾若干 slide → 加入某份 deck（后台调 `deck-splice` 的 `insert.py`，
  自动处理类名隔离 / 素材拷贝 / 视频物化 / 重新入库）
- **任务队列**：拼接 / 重入库走后台 worker，`/api/tasks` 看进度
- **deck 文件代理**：`/decks/<id>/*` 只读服务渲染产物给预览 iframe

> 另有一个更轻的 [`platform/web/`](platform/web/)（早期 React 只读浏览器，:5174，
> 基于 `library/index.json` 纯静态）——只读浏览 stories 用。日常管理用 **admin** 那个。

---

## 5. 资产库（`library/`）

整套系统的底座，构建器和管理端都连它。

| 路径 | 是什么 |
|---|---|
| `library/db/data/slides.db` | SQLite + FTS5 全文索引。每张 slide 一行：标题 / 正文 / 标签 / 媒体类型（**gitignore**，客户内容） |
| `library/db/ingest_deck.py` | 把 `deck.json` 入库（默认保留人工标签，`--retag` 才强制重打） |
| `library/db/gen_thumbnails.py` | 驱动 Chrome 给每页出缩略图 |
| `library/db/{schema.sql,deck_mounts.py,refine_tags.py,…}` | 表结构 / deck 挂载发现 / 标签工具 / 查重探针 |
| `library/stories/` | 每个 `<id>/` 是一个 4-5 页的小故事（复用粒度 = 叙事单位）（**gitignore**） |
| `library/shared-assets/` | 跨 deck 共享素材 |

deck 在磁盘上的约定位置：`imports/<deck-id>/render-output-full/`，目录名即
`deck_id`，admin 会自动发现（`deck_mounts.py`）。

---

## 6. deck.json 扮演什么（两条相反的流向）

`deck.json` 是各部分之间的**交换格式**，但它**不是统一的"单一可信源"**——
谁是"源"取决于走哪条路，两类流程的流向正好相反。

**结构化 / 导入路**（feishu-deck-h5、Keynote 导入）——deck.json 在**上游**，渲染成 HTML：

```
keynote-to-html / slide-design ──写──▶ deck.json ──render-deck.py──▶ index.html
   (.key / 大纲 → 结构化字段)           (源)                           (成品)
```

**rolling-deck 路**（默认对客流程，rolling-deck / v2）——index.html 是**源**，deck.json 是**派生**：

```
手填 template.html ─▶ index.html ─build-deckjson.py─▶ deck.json ─ingest─▶ slides.db
   (源)               (成品)        (派生的检索/拼接索引)
```

rolling-deck 的 deck.json 只是把成品 HTML 切片塞进 JSON 壳（每页 `layout:"raw"`、
`data.html` = 整段 markup），**给入库 / 检索 / 拼接用，不拿来渲染**。

| 实际原则 | 意思 |
|---|---|
| **deck.json 是交换格式，不是唯一源** | 导入路它在上游（→ HTML）；rolling-deck 路它在下游（HTML →，只当库索引） |
| **渲染器按 pack 分发，两套互不通用** | `_player/render.py` 读 `layout_pack` → 调对应 pack 的 `render_entry`。feishu 是结构化渲染（字段→fragment），rolling-deck 是 raw 套壳（HTML→壳），各认各的 deck.json 方言 |
| **运行时零耦合** | 每个 skill 自带 assets，只通过磁盘上的 `deck.json` 通信，可独立 CLI 运行 |
| **AI 辅助 + 人工拍板** | 导入后 Claude 提建议，UI 上人工确认；不做端到端全自动 |
| **小故事 = 4-5 页** | 复用粒度是叙事单位，不是单张版面 |

---

## 7. 目录地图（速查）

| 路径 | 是什么 |
|---|---|
| `plugin/skills/<name>/SKILL.md` | 每个 skill 的操作手册（做事前先读对应这份） |
| `plugin/skills/registry.py` | skill 清单 / 校验 |
| `plugin/_player/render.py` | 渲染调度入口 |
| `plugin/CHANGELOG.md` | 完整版本日志 |
| `imports/<deck-id>/render-output-full/` | 每份 deck 的成品（**gitignore**，客户内容） |
| `library/db/` | slides.db + 入库 / 缩略图 / 查重工具 |
| `platform/admin/` | 管理后台（FastAPI :8123 + Alpine） |
| `platform/web/` | 早期只读浏览器（React :5174） |
| `.claude/commands/` | `/deck-*` slash 命令 |
| `CLAUDE.md` | 给 Claude 的项目级路由规则 |

---

## 8. 红线

- **不要把 `imports/`、`library/db/data/`、`library/stories/` 的内容提交进 git**（客户机密，已 gitignore）
- **不要修改 rolling-deck 模板的 `<style>` / `<script>`**（模板的全部价值）
- 重新入库不会洗掉人工标签（`ingest_deck.py` 默认保留 tags）；想强制重打用 `--retag`
- splice 旧 slide 用 `deck-splice`，不要手工拷 HTML（类名隔离 / 素材路径 / 视频它都替你处理了）

完整版本迭代历史见 [`plugin/CHANGELOG.md`](plugin/CHANGELOG.md)。

## License

MIT（renderer 部分继承 feishu-deck-h5 原作者的 license 条款）
