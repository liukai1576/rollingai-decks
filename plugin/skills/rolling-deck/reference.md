# Rolling Deck 组件库 & 速查

替换内容时从这里挑版式。所有 class 已在 `template.html` 的 `<style>` 里定义好——直接用，别新写样式。

---

## 配色 token（CSS 变量，用 `var(--x)`）
| token | 值 | 用途 |
|---|---|---|
| `--bg` | #0c0e12 | 页面底色 |
| `--text` | #f3f5f8 | 正文主色 |
| `--muted` | #aab2bf | 次要文字 |
| `--subtle` | #79828f | 更弱文字 / 标签 |
| `--yellow` | #fbbf24 | 强调 1（kicker、阶段 A） |
| `--blue` | #60a5fa | 强调 2（赛道 B） |
| `--violet` | #c4b5fd | 强调 3（赛道 C） |
| `--green` | #34d399 | 成功 / 确认 |
| `--fire` | #ff5b2e | 高亮 / 火热重点 |
| `--glass-bg` / `--glass-border` | — | 卡片磨砂玻璃（`.card` 已用，别覆盖） |

**强调文字**：`<span class="tenx-mark">10×</span>` 橙金渐变高亮词；`<span class="kicker">SECTION 01</span>` 黄色小标。

---

## 每页骨架
```html
<section class="slide" data-slide-key="唯一英文key" data-screen-label="02 这页标题">
  ...内容...
</section>
```
- 第一张必须是封面 `<section class="slide active cover-hero" ...>`（保留模板原样，只改标题/副标题）。
- `data-slide-key` 唯一、英文短横线（决定编辑持久化的 key）。
- `data-screen-label` = 序号 + 标题（人看的）。

---

## 标题区（几乎每页开头都用）
```html
<div class="section-head">
  <div><span class="kicker">01 · SECTION</span><h2>主标题<br>可两行</h2></div>
  <p class="copy">右侧导语，<strong>可加粗重点</strong>。</p>
</div>
```

---

## 版式组件

### 1. 统计数字格（概览常用）
```html
<div class="hero-stats">
  <div class="stat"><div class="stat-num">3</div><b>个阶段</b><span>说明</span></div>
  <!-- 重复 stat -->
</div>
```

### 2. 三/四列卡片
容器 `.cards-3`（3 列）或 `.cards-4`（4 列）。卡片基类一律 `.card`，再加修饰类：
```html
<div class="cards-3">
  <article class="card route-card">
    <div class="route-top"><span>PHASE 01</span><strong>2 DAYS</strong></div>
    <h3>卡片标题<br>可两行</h3>
    <p>一段描述。</p>
    <ul><li>要点一</li><li>要点二</li></ul>
    <div class="exit"><strong>输出：</strong>交付物</div>
  </article>
  <!-- ... -->
</div>
```
卡片修饰类可选：`route-card`（流程，含 route-top/exit）、`coach-card`（card-no + h3 + p）、`cadence-card`（card-no + h3 + p + ul）、`ceo-card`（cc-num + h3 + p）、`track-overview`（track-code + h3 + track-sub + ul + track-deliver）。结构按需取。

### 3. 目标网格（2 行 3 列，首格可占两行）
```html
<div class="goals-grid">
  <article class="goal-card lead-card">
    <span class="goal-num">GOAL 01</span>
    <h3 class="goal-headline">大标题</h3>
    <p class="goal-tag">一句话标签</p>
    <p class="goal-note">补充说明。</p>
  </article>
  <article class="goal-card"><span class="goal-num">GOAL 02</span>...</article>
  <!-- 共 5 个 -->
</div>
<div class="goals-foot">底部总结条，<strong>可加粗</strong>。</div>
```

### 4. 两栏对照
```html
<div class="approach-grid">
  <article class="card approach-card left">
    <h3>① 向内</h3>
    <p class="ac-sub">副标题</p>
    <ul class="approach-list"><li><b>要点</b><small>小字说明</small></li></ul>
  </article>
  <article class="card approach-card right">... </article>
</div>
```
可选 chips：`<div class="ref-chips"><span>标签</span>...</div>`

### 5. 日历表格（周计划 / 节奏）
```html
<div class="legend"><span><i style="background:var(--yellow)"></i>双方</span>...</div>
<div class="calendar-wrap">
  <table>
    <thead><tr><th>阶段</th><th>周</th><th>周一</th>...</tr></thead>
    <tbody>
      <tr>
        <td class="phase-cell" rowspan="2"><b>阶段名</b><span>PHASE 01</span></td>
        <td class="week-cell"><b>W1</b><span>第1周</span></td>
        <td class="cal-cell both"><b>事项</b><small>说明</small><span class="owner">双方</span></td>
        <td class="cal-cell us">...</td>     <!-- us=蓝 client=紫 both=黄 -->
      </tr>
    </tbody>
  </table>
</div>
```
单元格配色类：`both`(黄) / `us`(蓝) / `client`(紫)。

### 6. 三赛道表格 `track-table`（结构同上，class 换成 `tt-label/tt-cell/tt-code`，外面同样套 `.calendar-wrap`）。

### 7. 组织层级
```html
<div class="org-stack">
  <div class="org-layer l1">
    <div class="ol-label"><span class="ol-tag">决策层</span><span class="ol-name">名称</span></div>
    <div class="ol-body">说明<div class="org-sub"><span>角色A</span><span>角色B</span></div></div>
  </div>
  <!-- l1~l4 -->
</div>
```

### 8. 阶段里程碑条（放页尾）
```html
<div class="phase-strip">
  <div class="phase"><span>DAY 2</span><b>里程碑</b><small>说明</small></div>
  <!-- 4 个 -->
</div>
```

### 9. 强调横幅（放页尾收口）
任选其一，都是全宽磨砂条：`synth-band`（火橙）、`cadence-note`/`ceo-core`（黄）、`coach-band`（含 `coach-pill`）、`band`。
```html
<div class="synth-band">一句收口结论，<strong>重点加粗</strong>。</div>
```

### 10. 时间线 / 周次网格
```html
<div class="tl-section-label">PHASE 02 · 8 周冲刺</div>
<div class="tl-weeks">
  <div class="card tl-w tl-p1">
    <span>W1–W2</span><b>调研</b>
    <small>共同调研</small>
    <span class="tl-sum">形成机会图谱</span>
    <span class="tl-date">6/17–6/28</span>
  </div>
  <!-- 4 格。左边框色：tl-p1黄 tl-p2蓝 tl-p3紫 tl-p4绿；tl-prep黄 tl-ws火 -->
</div>
```
每格用 `.card .tl-w .tl-pN` —— `.card` 给玻璃质感，`.tl-pN` 给彩色左边框区分阶段。

### 11. 卡片角落大数字水印
给任意卡片加 `.has-watermark`，里面放一个超大半透明数字/字母：
```html
<article class="card approach-card has-watermark">
  <span class="dir-watermark">A</span>
  <h3><span class="dir-icon">🅰️</span>方向 A</h3>
  ...
</article>
```

---

## 注意事项
- 卡片只用 `.card` + 修饰类，**别加自定义不透明背景**（会盖掉玻璃质感和背后彩光）。
- 每页内容别堆太满——超高会被自动缩小，但太满仍不好看；一页一个核心论点。
- 文字用语义标签（h2/h3/p/li/td/span）→ 自动可编辑、可导出 PDF。
- 表格 / 满版页放在 `.calendar-wrap` 里能拿到玻璃壳。
- 页尾收口横幅是这套模板的标志性收束，建议每个内容章节结尾用一条。
- **导出 PDF**：模板的 `@media print` 已处理好——磨砂玻璃面板在打印时 `backdrop-filter` 会失效变透明，模板给它们加了实色暗背景兜底，并隐藏打印不干净的液态金属动画边、每页排成一张。生成后提醒用户：打印对话框里勾选「背景图形」、方向选「横向」，再「另存为 PDF」。
