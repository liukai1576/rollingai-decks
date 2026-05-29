# deck.json schema · v2

> 这是 deck.json 的契约。所有 skill（importer / transformer / exporter / layout
> pack）都按这份文档读 / 写。任何 skill 修改 deck.json 时**必须**保持
> `version` 不变（除非是显式的版本升级 skill）。

---

## 顶层结构

```json
{
  "version": "2",
  "deck": {
    "title":       "RollingAI分享-康师傅",
    "language":    "zh-only",
    "mode":        "rewrite",
    "layout_pack": "rolling-deck-h5"
  },
  "slides": [ ... ]
}
```

### `version` (string, required)
当前版本固定为 `"2"`。读到不认识的 version 时 skill 应当报错而不是猜。

### `deck.title` (string, required)
deck 的展示名（一般来自原始 .key 文件名）。

### `deck.language` (string)
`"zh-only"` / `"en-only"` / `"bilingual"` 等。播放器据此决定字体栈。

### `deck.mode` (string)
`"rewrite"`（导入产物，可被各类 skill 修改）/ `"preserve"`（原样保留，少改）。

### `deck.layout_pack` (string)
渲染时使用的布局包 id。Player 据此加载该包的 CSS / JS / layout 模板。
v2 默认 `"rolling-deck-h5"`，对应 `plugin/skills/rolling-deck-h5/`。

---

## `slides[]` 数组

每个元素：

```json
{
  "key":          "slide-007",
  "title":        "立白项目目标",
  "notes":        "",
  "layout":       "raw",
  "screen_label": "07",
  "data": {
    "html": "<style>...</style><div class='el' style='...'>...</div>"
  }
}
```

### `key` (string, required)
slide 的稳定标识符。同 deck 内唯一。导入 Keynote 时格式是 `slide-NNN`
（NNN = Keynote 内部编号，包含跳过的页）。

### `title` (string, required) ⭐ **v2 新增**
slide 的标题——**一等字段**。
所有"改文案"类 skill 应当**只动这个字段**，不要直接动 `data.html` 里的
title 元素文字。导入 / 渲染时由 builder / player 负责把 `slides[].title`
同步进可见 HTML（详见 §"raw layout 的 title 同步"）。

来源：
- 导入时由 importer 选取（典型：取 slide 内最大字号的文本）
- 后续由 transformer skill 修改

如果一张 slide 真没有任何文字，title 设为空串 `""`，不要塞占位文本。

### `notes` (string, optional, v2 新增)
slide 的备注 / 编辑批注 / 上下文。

### `layout` (string, required)
- `"raw"`：`data.html` 是完整的 inline HTML，**自带定位 + 样式**。
  Keynote / PPT / 图片导入产物默认是这个。
- 其他：由当前 `deck.layout_pack` 注册的命名 layout（例如 `"cover"`,
  `"content-2col"`, `"matrix-2x2"` 等）。每个 layout 自己定 `data` 的结构。

### `screen_label` (string)
播放时显示的页码（"07" / "1.3"）。

### `data` (object, required)
跟着 `layout` 走：
- `layout: "raw"` 时 → `{ "html": "<...>" }`
- 命名 layout 时 → 该 layout 在 layout pack manifest 里定义的 schema

---

## raw layout 的 title 同步规则

raw layout 的 `data.html` 自带 title 元素（最大字号那段文字）。
为了让"只改 `slides[].title` 就能体现到渲染"这件事工作，约定：

1. **导入时**：importer 在 title 元素上加 `data-role="title"` 属性。
   例：
   ```html
   <div class="el" data-role="title" style="font-size:40px;...">立白项目目标</div>
   ```
2. **修改 title 时**：skill 同时改 `slides[].title` 和 `data.html` 里
   `data-role="title"` 元素的 innerText。或者只改 `slides[].title`，让
   下一个 render 步骤来对齐（player 的渲染管线读 `slides[].title` 时，
   若与 HTML 里 `data-role="title"` 元素文字不一致，以 `slides[].title`
   为准并 inplace 替换）。

如果一张 raw slide 找不到合适的 title 元素，导入时**不要硬塞**
`data-role="title"`——这种 slide 的 title 同步等于 best-effort，
`slides[].title` 仍然作为元数据维护。

命名 layout（cover / 2col 等）不存在这个问题：layout 模板直接读
`slides[].title`，HTML 是渲染出来的。

---

## 兼容性

v1（旧）→ v2 的最小升级：
- 顶层加 `"version": "2"`
- 每个 slide 加 `"title"` 字段
- raw HTML 的 title 元素加 `data-role="title"`

v1 deck 没有 `slides[].title`，importer 重跑一遍即可生成。
读 v1 的 skill 应当先调用 `_lib/migrate.py` 升到 v2 再处理（或拒绝）。

---

## 字段索引（速查）

| 路径 | 类型 | required | 说明 |
|---|---|---|---|
| `version` | string | ✓ | `"2"` |
| `deck.title` | string | ✓ | deck 展示名 |
| `deck.language` | string |   | `zh-only` / ... |
| `deck.mode` | string |   | `rewrite` / `preserve` |
| `deck.layout_pack` | string |   | 默认 `rolling-deck-h5` |
| `slides[].key` | string | ✓ | 同 deck 唯一 |
| `slides[].title` | string | ✓ | **v2 新增** · 一等字段 |
| `slides[].notes` | string |   | **v2 新增** |
| `slides[].layout` | string | ✓ | `raw` 或注册 layout |
| `slides[].screen_label` | string |   | 显示页码 |
| `slides[].data` | object | ✓ | layout 决定结构 |
