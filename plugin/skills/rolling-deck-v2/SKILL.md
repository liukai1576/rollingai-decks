---
name: rolling-deck-v2
display_name: RollingAI 影像玻璃 H5（粒子地球 · 实景影像 · 磨砂玻璃）
author: ganyifan
kind: [布局风格]
version: "1.1"
input:  用户的 brief / 大纲 / 内容 (+ 可选：客户 logo / 实景照片)
output: 单文件 index.html（assets/ 同目录），浏览器直接打开放映
triggers:
  - "做一个影像玻璃风格的 deck"
  - "用大幅实景照片 + 磨砂玻璃那套模板"
  - "粒子地球封面、但页面要压实景照片"
  - "rolling-deck v2"
invocation: |
  # Conversational. Claude 复制 plugin/skills/rolling-deck-v2/template.html
  # 到目标位置，按 reference.md 的咨询版式组件库替换内容、改 brand-rail logo /
  # 封面文字。不动 <style> 和 <script> —— 那是模板全部价值。
produces_layout_pack: true
---

# Rolling Deck v2 — 影像玻璃风格

**视觉风格名：影像玻璃（Cinematic Glass）。** 跟 `rolling-deck` 共用同一套引擎
（粒子地球封面、磨砂玻璃、固定 1920×1080 自动缩放、翻页 / 全屏 / 编辑文字 /
导出 PDF），底层设计 token 完全一致——**区别在视觉做法**：v2 把**大幅实景照片
压在磨砂玻璃面板下**（背景照、照片信息面板、全幅章节图），整体偏电影感 / 实景
质感；v1 则是干净的纯图形文字玻璃。

产出仍是一个 `.html`，浏览器直接打开即放映。引擎里**没有也不要**内置结构化
编辑器——结构编辑用我们既有的能力（admin / deck-splice），这个 skill 只管"布局"。

风格名描述的是**外观**，不是用途——具体讲什么内容由使用者填。pack 顺带提供了
一套适配这种影像质感的版式组件（见 `reference.md`），但用什么、讲什么是你的事。

## v1 还是 v2？

| | rolling-deck (v1) | rolling-deck-v2（影像玻璃） |
|---|---|---|
| 视觉做法 | 干净纯图形 / 文字玻璃，几乎不用照片 | 大幅实景照片 + 玻璃叠层，电影感 |
| 配套组件 | 通用版式（cards-N / goals-grid / tl-weeks / 13 个 tpl-*：图表 / 视频 / 时间轴 / 金句 / Logo 墙…） | 影像版式（照片背景 thesis / 照片信息面板 / 全幅章节图 / 矩阵看板 / 风险雷达 / 阶梯…） |
| 引擎 / 配色 token | 同一套（粒子地球 · 玻璃 · 自动缩放） | 同一套 |

页面想要**实景照片质感、电影感**（人物、场景、现场）→ 选 **v2**；想要**干净的
纯图形 / 数据 / 文字**、或要图表 / 视频 / 时间轴这些通用件 → 选 **v1**。不确定按 v1。

## 🛑 头号原则：template 不是故事线，是**风格 + 组件库 + 标准页**

`template.html` 是"企业 AI 转型与家庭教师方法论"这份成片（34 页）。它**不是**
你新 deck 的剧本。它给的是：

- 视觉系统（玻璃、配色、字体、动画）
- 咨询版式词汇表（见 `reference.md`：thesis-canvas / matrix-dashboard /
  visual-page+playbook-grid / mode-panel-grid / meeting-board / risk-command /
  business-ladder …）
- 标准页：封面 `cover-hero`、章节过渡 `chapter-*`、结尾收口

它**不**给：你 deck 的页数、章节顺序、内容标签（别硬抄"九宫格""六种服务模式"
"家庭教师"这些原 case 的叙事）。

**正确动作：**
1. 先读用户的原始素材，梳理出**它自己的方法论结构**——几个判断维度、几类
   对象、几种打法、几个阶段。
2. 一页一页问"这页的信息形态是什么？"再去 `reference.md` 挑匹配的咨询组件：
   - 总框架 / 核心判断 → `thesis-canvas`（编号路线）
   - 二维诊断（基础 × 风格、紧急 × 重要…）→ `matrix-dashboard` + `matrix-board`
   - 矩阵某一行 / 某一类对象的打法 → `visual-page` + `playbook-grid`（play-card K-V）
   - 一种交付模式 / 服务 → `mode-panel-grid`
   - 汇报节奏 / 利益相关方翻译 → `meeting-board` / `report-dashboard`
   - 风险 / 坑点 → `risk-command`（雷达 + 泳道 + 清单）
   - 商业模式 / 复制性阶梯 → `business-ladder` + 图表卡
   - 关系 / 利益相关方 → `media-split` + SVG 图
   - 阶段路径 → `timeline`；议程 → `agenda-list` + `map-route`；总结 → `summary-system`
3. **绝对不能反过来**：先看哪页好看就照搬，再把内容塞进去凑满。原文只有 4 类
   对象就别为了填满九宫格硬编出第 5、6 类。

## ✍️ 标题用咨询体（这套版式的灵魂）

标题要**结论先行、能直接念出来**，不要纯标签 / 黑话 / 空形容词：

- ✅ `X 的核心变量不是 A，而是 B` · `先做 X，再做 Y` · `用 X 降低 Y 风险` ·
  `同一份成果，要翻译成不同决策语言`
- ❌ 纯标签：`工作类型` `坑点` `分析元素状态`
- ❌ 黑话：`多主体交互下的组织变革非线性风险`
- ❌ 空形容词：`全面赋能` `深度升级` `智能化新范式`

服务模式用企业交付语言：`企业诊断 / 样板示范 / 实战陪跑 / 托管冲刺 /
组织信心建设 / 能力系统共建`；只有用户明确要"教育 / 培训"框架时才用"课"。

## 只换内容，不动引擎

模板里这些**绝对不要改**（它们是模板的全部价值）：`<style>` 整套设计系统 +
`<script>` 全部逻辑（粒子地球、翻页 / 全屏 / 缩放、`slide-fit` 包裹、编辑文字、
导出 PDF）。

你的工作只有四件（同 rolling-deck）：

1. **品牌条 `.brand-rail`**：左 logo 永远 RollingAI；右 logo 换本次客户（模板里
   现成的 `weimeizi-logo.svg` / `shuke-logo-transparent.png` 是原 case 的客户 logo，
   做新 deck 时换成你的客户）。
2. **封面 `.cover-hero`**：改 `.cover-hero-title` + `.cover-hero-sub`，粒子地球 /
   布局不动。
3. **逐张内容页**：每张 `<section class="slide" data-slide-key="唯一key"
   data-screen-label="02 标题">`，从 `reference.md` 挑咨询版式填内容。
4. **增删页**：删用不上的 `<section>`、复制需要的版式再改。**DOM 顺序 = 放映
   顺序**，第一张必须是 `.cover-hero`。

> ⚠️ Splice / 批量替换时别误删最后一个 `</section>` 和 `</main>` 之间的演示控制台
> DOM（`<!-- Controls -->` 起约 35 行，JS 用 id 硬挂）。删了表现为"播放器没启动"。
> 加自定义 slide 类时别在 `.slide.<你的类>` 上直接覆盖 `display`，要写
> `.slide.<你的类>.active`（详见 rolling-deck/SKILL.md 同名小节）。

## 🔍 自检：每张 slide 的空间利用率（必跑）

做完后跑 **check-fill** 看每张是否撑满 1080 垂直空间：把
`<script src="assets/check-fill.js"></script>` 放进 index.html，访问
`…/index.html?check`，控制台打印每张 `fillPct` + 汇总。`缺`（< 80%）换更密的组件
或加页尾收口横幅；`溢`（> 105%）拆成两页。矩阵 / 风险这类页天然撑满，一般直接 OK。

## 工作流程

1. **复制模板**：`plugin/skills/rolling-deck-v2/template.html` →
   `imports/<deck-id>/render-output-full/index.html`，连同 `assets/`（logo / SVG 业务图 /
   photos / slide-anim）一起带上。
2. 按上面"四件事"替换内容、按 `reference.md` 挑咨询版式。
3. **跑 verifier**：`bash plugin/skills/feishu-deck-h5/assets/verify-deck-shell.sh <deck-dir>`
   —— 必须打印 `OK: rolling-deck deck shell wiring looks correct.` 才算合格。
4. **自测**：浏览器翻一遍；试封面拖动 / 缩放；点 ⚙ 进编辑改两个字；试导出 PDF。

## 入库（让 admin UI 能看到）

```bash
# 1. 合成 deck.json
python3 plugin/skills/rolling-deck-v2/assets/build-deckjson.py \
  imports/<deck-id>/render-output-full/index.html --title "你的标题"
# 2. 入库
python3 library/db/ingest_deck.py <deck-id> \
  imports/<deck-id>/render-output-full/deck.json
# 3. 缩略图
python3 library/db/gen_thumbnails.py --deck <deck-id>
# admin UI 自动发现 imports/ 下的 deck，无需注册
```

## 配套素材（在 `assets/` 里，随模板一起带）

- `rolling-ai-logo.svg`（左品牌）、`weimeizi-logo.svg` / `shuke-logo-transparent.png`（原 case 客户 logo，做新 deck 时替换）
- SVG 业务图：`family-map.svg`（关系图谱）、`work-modes.svg`、`learning-system.svg`、`business-model.svg`——换主题时重画或换照片
- `photos/photo-cn-*.png`：6 张中国企业场景照（会议 / 培训 / 陪跑 / 治理 / 工作坊…）——换主题时替换成贴题图
- `slide-anim/`：GSAP 入场动画引擎（已内联编排，勿改）
- `build-deckjson.py` / `check-fill.js`：入库 & 自检工具
