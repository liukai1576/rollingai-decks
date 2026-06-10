---
name: deck-splice
display_name: Deck Splice — 复用旧 deck 的 slide 到新 deck 里
author: liukai
kind: [创建]
version: "0.7"
input:  manifest.json（N 个 splice 条目：outer_key + source_deck_id + source_slide_key）+ 目标 deck 目录（已有 N 个空 `is-splice` placeholder section）
output: 修改后的目标 index.html（splice section 已填好）+ `assets/_borrowed/<src_deck>/...`（视频/图片素材已拷贝并改路径）
triggers:
  - "把 X deck 的 slide-NN 拼到 Y 里"
  - "splice 旧 deck 某一页过来"
  - "复用老 deck 的 slide"
  - "拼一份对客 pitch deck"
produces_layout_pack: false
---

# deck-splice

把旧 deck 的某些 slide 整段搬到一份新 deck 里 ——
**不是截图、不是 iframe、是真实 DOM**，视频可以播、文字可以选、PDF 导出
没问题。

## 何时用

- 对客 pitch deck，需要复用历史项目案例（"立白这 6 张直接搬"）
- 不同风格 pack 之间共享内容（feishu-deck-h5 → rolling-deck shell）
- 把零散 slide 重新打包成"快速 demo deck"

如果只是要把整份 deck 换风格、或者从头按结构化数据渲染——用
`feishu-deck-h5` / `rolling-deck` 的 render 入口，不用本 skill。

## 不做的事

- ❌ 决定**哪些 slide 要拼**（这是人的判断，对话出来；可以用
  `assets/pick.py` 辅助检索）
- ❌ 决定 deck 大纲、章节顺序、screen-label（人写 placeholder section，
  splice 只填内容）
- ❌ 创建新的封面 / Section 头 / 收口页（那是 `rolling-deck` 自己的活）
- ❌ 入库、出缩略图、做标签（用 `deck-ingest` + `thumb-gen`）
- ❌ 跑源 deck 的 JS / 动画（splice 是视觉层面，不复活 player）

## 工作流程（5 步）

### Step 1 — 调研选材
用 `pick.py` 在 slides.db 里搜：
```bash
python3 plugin/skills/deck-splice/assets/pick.py \
  --keywords 销售 渠道 培训 经销商 \
  --customers 立白 安利 美宜佳 \
  --exclude-deck lanyueliang-pitch \
  --limit 40
```
输出按 deck/page 排序的候选清单（含 type_tag/customer_tag/媒体类型/
标题）。

### Step 2 — 设计 deck 大纲
**人**写好目标 deck 的 18 张 section 顺序、screen-label、每一段属于
哪个 act。这一步不入 skill。

### Step 3 — 在目标 deck 里**留 placeholder**
新 deck 的 `index.html` 里，每个要 splice 的 slot 写一个空 section：

```html
<section class="slide is-splice"
         data-slide-key="liby-bc-recorder"
         data-screen-label="08 立白 · 销售随身记录"></section>
```

约定：
- `class` 必须包含 `slide` 和 `is-splice` 两个 token
- `data-slide-key` 是目标 deck 自己的命名（不是源 slide key）
- splice.py 只会**填这种空 section**，永远不会自己创建新的 section

### Step 4 — 写 manifest + 跑 splice
```json
{
  "host_pack": "rolling-deck",
  "splices": [
    {"outer_key": "liby-bc-recorder",
     "source_deck_id": "RollingAI分享",
     "source_slide_key": "slide-041"},
    {"outer_key": "amway-copilot",
     "source_deck_id": "AI案例分享",
     "source_slide_key": "slide-061"}
  ]
}
```
```bash
python3 plugin/skills/deck-splice/assets/splice.py \
  --target imports/<deck>/render-output-full \
  --manifest manifest.json
```

splice.py 做的事（每条 splice）：
1. 从 `imports/<source_deck_id>/render-output-full/index.html` 提取
   `<div class="slide" data-slide-key="<src_key>">…</div>`
2. **重命名 class**：`slide` → `src-slide`（防止跟 host pack 撞）
3. **重写选择器**：所有 `.slide` 但不是 `.slide-fit` / `.slide-frame` /
   `.slideXxx` → `.src-slide`（正则 lookahead 保平安）
4. 复制源 slide 引用的全部素材（img/video/source/poster + 内联
   `url()`）到 `<target>/assets/_borrowed/<source_deck_id>/<orig path>`，
   路径在 markup 里就地改写
5. 找目标 deck 里 `data-slide-key=<outer_key>` 的空 is-splice section，
   把渲染好的 markup 填进去
6. 给目标 deck 的 `<style>` 块加一段必备 CSS（幂等）：
   ```css
   .slide.is-splice { padding: 0 !important; }
   .src-slide { position: absolute; inset: 0; width: 1920px; height: 1080px; ... }
   .slide-fit > .src-slide { flex: 1 1 0; min-height: 0; }
   ```

### 一步到位的替代入口：insert.py（admin 购物车走这条）

如果你不想手写 placeholder + manifest，`insert.py` 把整条管线包成一步：

```bash
echo '{
  "target_deck_id": "lanyueliang-pitch",
  "after_page": 5,
  "items": [
    {"source_deck_id": "RollingAI分享", "source_slide_key": "slide-041"}
  ]
}' | python3 plugin/skills/deck-splice/assets/insert.py --spec -
```

它会：快照 index.html → 在第 N 页后自动生成 placeholder（key 唯一化
`sp-<源key>`）→ 调 splice.py 填充 → 重排 data-screen-label 序号 →
重建 deck.json（rolling-deck build-deckjson）→ 重新入库（已打标签
保留）→ 把源 slide 的标签拷给新行 → 只给新 slide 出缩略图 →
跑 verify.sh。失败自动回滚快照。

admin 管理平台的「购物车 → 加入 Deck」按钮生成的后台任务就是调它
（`POST /api/decks/{id}/insert-slides` → tasks 表 → worker 线程）。

### Step 5 — verify + 入库
```bash
bash plugin/skills/deck-splice/assets/verify.sh \
  imports/<deck>/render-output-full
```
verifier 检查：
- 没有 `.slide` 命名空间泄露（host pack 的 `querySelectorAll('.slide')` 拿到的数 = 外层 section 数）
- 注入的 CSS sentinel 在
- 没有空的 is-splice placeholder 漏填
- 每个 `assets/...` 资源文件存在

通过后跑 `deck-ingest` + `thumb-gen` 即可。

## 五个踩过的坑（这个 skill 替你避开）

| 坑 | 不处理会发生什么 |
|---|---|
| `.slide` 类名两边都用 | rolling-deck 的翻页 JS `querySelectorAll('.slide')` 多算一倍，翻页崩、`pageNo` 错乱 |
| `.slide` 正则没加 lookahead | `.slide-fit` / `.slide-frame` 一起被改成 `.src-slide-fit`，整个 player 引擎死 |
| rolling-deck JS 自动包 `.slide-fit` flex 列 | 内嵌内容塌成 0 高 → 屏幕上只看到一条横线 |
| 资源路径没重写 | `assets/_shared/video.mp4` 404 → 视频黑屏 |
| 跨 deck 的 `../../../plugin/...` CSS link | 拷给客户后路径断 → 整张 slide 没样式 |

## 局限

- **只是视觉 splice**：源 deck 的 inline `<script>`（动画、canvas 初始
  化）**不会跑**，因为 host pack 不会加载源 pack 的 player JS。绝大多
  数 slide 不依赖这个；如果发现某张 splice 后效果不对，多半就是源
  slide 依赖了某段 JS。
- **视频是例外，已完整处理**：splice 时自动物化懒加载视频
  （`data-src`→`src`，`preload=none`），并给 host deck 注入一段幂等的
  视频运行时（sentinel: `deck-splice video runtime`）：翻到该页才播放、
  离开自动暂停归零。该运行时管整个 deck 的所有 `<video>`（host 自带
  的也一样）。
- **声音是 opt-in 的，按 slide 打标签**：所有源 mp4 都带音轨（街拍
  环境音、AI 生成配乐都算），"该不该出声"是编辑意图，数据里没有。
  约定：在 admin 给源 slide 的自由标签加 `有声视频` → insert.py 拼接
  时给该页视频盖 `data-sound` 标记 → 运行时在用户首次交互（翻页就算）
  后解除这些视频的静音；没标签的视频永远静音。手写 manifest 时等价
  写法是给 splice 条目加 `"sound": true`。
  注意：`visibilityState: hidden` 的页面（如某些嵌入式预览面板）里
  Chrome 会拒播视频，这是浏览器省电策略，不是 bug。
- **共有类名风险**：源 slide 用了 `.card` / `.grid` 这种常见类，host
  pack 也定义了同名类 → 样式会被 host 覆盖。splice.py 会在 stderr
  打 ⚠ 警告，但不会自动改。需要人工 namespace 或挑选不冲突的源
  slide。
- **大文件素材**：视频会被实际拷贝（dedup 按 hash 在
  `assets/_borrowed/<src_deck>/...` 子树内），可能让 deck 目录
  从 5 MB 暴涨到几百 MB。这是为了让 deck 自包含、可打包发客户。
  如果不需要 portability，可以手动改成符号链接。

## 跟其它 skill 的边界

| Skill | 它管 | splice 不管 |
|---|---|---|
| `rolling-deck` / `feishu-deck-h5` | 提供 host pack 的 shell + template | splice 不创建外壳，只填 placeholder |
| `deck-ingest` | 把目标 deck 入库 | splice 后调一下就行 |
| `thumb-gen` | 出缩略图 | 同上 |
| `slide-design` / `slide-redesign` | 写新页 / 改单页 | splice 不写新页 |
| `slim-deck` | 给 deck 减肥 | splice 是反向操作（往里加内容）|

## 真实样例

`imports/lanyueliang-pitch/render-output-full/` 是首批 dogfooding 案例：
- 6 张新页（rolling-deck 风格）+ 11 张 splice（来自 `RollingAI分享` 和
  `AI案例分享` 两份历史 deck）= 17 张 splice + 1 张 cover = 18 张 deck
- 立白 6 张 case slide 整段搬，视频路径自动改写
- 总 252 MB 借来的素材，整个 deck 可打包独立交付
