# HTML Deck Template（1920×1080 演示模板）

基于 `10x-transformation.html` 沉淀的通用 HTML 演示模板：深色玻璃拟态风格，内置翻页、编辑模式、PDF 导出、GSAP 动效引擎，共 **29 页**（16 页原内容页 + 13 页通用模板页）。

## 使用方式

- 直接双击打开 `template.html`（GSAP 已本地化，无需联网）
- 翻页：`↑/↓/←/→` 或底部按钮；`F` 全屏
- 右下角 ⚙ → **编辑模式**：点击页面任意文字直接改，自动存到 localStorage
- 右下角 ⚙ → **导出 PDF**：每页一张 1920×1080
- 复用：复制任意 `<section class="slide">` 即新增一页；删除整个 `<section>` 即删页（页码、进度条自动更新）

## 页面清单

| # | 类型 | slide-key | 说明 |
|---|------|-----------|------|
| 01 | 粒子封面 | `cover-hero` | 可拖拽 3D 粒子地球 + 金属扫光标题 |
| 02–16 | 内容页 | — | 原 10x 方案页：概览/北极星/方法论/路线/工作坊/日历表/赛道/组织/节奏/CEO，全部可当版式复用 |
| 17 | **章节过渡页** | `tpl-divider` | 大编号水印 + 章节标题 |
| 18 | **目录页** | `tpl-agenda` | 两列图标条目 |
| 19 | **全屏大图** | `tpl-full-image` | 整页背景图 + 左下文字 + Ken Burns 缓推 |
| 20 | **图文分栏** | `tpl-media-split` | 左图右文 + 要点列表 |
| 21 | **多图网格** | `tpl-media-grid` | 三图 + 渐变图注 |
| 22 | **视频页** | `tpl-video` | 本地 mp4 / B站 / YouTube iframe，翻页自动暂停 |
| 23 | **数据图表** | `tpl-chart` | 柱状图生长 + 环形图描边 + KPI 数字滚动（纯 CSS/SVG，无图表库） |
| 24 | **金句页** | `tpl-quote` | 大引号 + 逐字浮现 |
| 25 | **对比页** | `tpl-compare` | BEFORE/AFTER 双列 + VS 徽章 |
| 26 | **时间轴** | `tpl-timeline` | 横向划线 + 5 节点（可增减） |
| 27 | **团队页** | `tpl-team` | 头像/姓名/角色/简介 ×4 |
| 28 | **Logo 墙** | `tpl-logos` | 4×2 合作伙伴 |
| 29 | **结尾页** | `tpl-end` | 金属扫光 Thank You + 联系方式 |

**模板总览**：打开 `index.html` 可一页浏览全部 29 页真实缩略图（`assets/thumbs/`），点击直达对应页；直达链接格式 `template.html?slide=22`，加 `&static=1` 可关闭入场动画（截图/嵌入用）。

每个模板页顶部都有 HTML 注释写明替换方法。

## 替换图片 / 视频

- **图片**：把文件放进 `assets/`，替换 `<img src="assets/placeholders/photo-x.svg">` 为你的路径。占位图标明了建议尺寸
- **本地视频**：mp4 放进 `assets/`，改 `<source src="assets/your-video.mp4">`
- **B 站**：`<iframe src="//player.bilibili.com/player.html?bvid=BV号&autoplay=0" allowfullscreen></iframe>`
- **YouTube**：`<iframe src="https://www.youtube.com/embed/视频ID" allowfullscreen></iframe>`

## 图标库（Lucide）

选型结论：**Lucide**（Feather 继任者，shadcn/ui 同款）——MIT/ISC 协议、1500+ 图标、统一 24px 描边网格，和本模板细线条玻璃风格最契合。已本地化在 `assets/vendor/lucide.min.js`，离线可用。

**用法**（图标名查 https://lucide.dev/icons）：

```html
<i data-lucide="rocket"></i>                          <!-- 任意位置插图标 -->
<span class="ico-chip"><i data-lucide="compass"></i></span>   <!-- 彩色图标方块 -->
<span class="ico-chip blue|violet|green|fire">…</span>        <!-- 换主题色 -->
<b class="ico-inline"><i data-lucide="mail"></i>文字</b>      <!-- 行内随文字大小 -->
```

新增图标后无需任何 JS 改动（页面加载时统一渲染）；若用 JS 动态插入，再调一次 `lucide.createIcons()`。目录页、视频看点、图表标题、对比页、时间轴、团队角色、结尾联系方式已带示例。

## GSAP 动效引擎

GSAP 3.13 本地化在 `assets/vendor/`（核心 + SplitText + TextPlugin，3.13 起全部插件免费）。翻到每页时自动编排入场动画：

**自动识别（零配置）**
- 主标题（h1/h2/金句）**逐字浮现**（SplitText，结束后还原 DOM，不影响编辑模式）
- kicker 左滑入、引导文案上浮
- 所有卡片网格（cards-2/3/4/6、stats、team、agenda…）**错落上升**
- `.stat-num` 与 `[data-count]` **数字滚动**（支持 `10×`、`-58%`、`4.8` 等带前后缀格式）
- 柱状图 `scaleY` 生长、环形图 `stroke-dashoffset` 描边、时间轴横线划入
- 全屏大图 Ken Burns 缓推、媒体框缩放浮现
- 收尾横幅（synth-band 等）最后浮入

**手动标注（加属性即可）**
```html
<div data-anim="rise">上浮</div>      <!-- rise / fade / left / right / scale / blur -->
<div data-anim="left" data-anim-delay="0.5">延迟 0.5s 左滑入</div>
<ul data-stagger>…</ul>              <!-- 子元素自动错落入场 -->
<span data-count="98%">98%</span>    <!-- 数字滚动 -->
```

**安全设计**：快速翻页时上一页动画先跳终态再销毁（不会冻结半透明）；导出 PDF / 打印前自动跳终态；编辑模式下关闭动画；尊重系统"减弱动态效果"设置。

## GSAP 还能做什么（按需加）

- **Flip 插件**：两页之间同一元素的"魔法移动"（类似 Keynote Magic Move）
- **MorphSVG**：图形形变（logo → 图标）
- **DrawSVG**：SVG 线条手绘描边
- **MotionPath**：元素沿路径飞行（流程图连线动画）
- **ScrambleText**：数字/代码乱码翻牌效果
- **CustomEase / physics**：弹性、惯性、抛物线
- 滚动驱动（ScrollTrigger）对翻页式 deck 不适用，长页面版才需要

全部插件已随 3.13 免费，需要时从 `https://cdn.jsdelivr.net/npm/gsap@3.13.0/dist/<插件>.min.js` 下载到 `assets/vendor/` 并在 `template.html` 底部加一行 `<script>` 即可。
