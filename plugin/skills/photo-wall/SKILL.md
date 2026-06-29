---
name: photo-wall
display_name: 照片墙
author: liukai
kind: [创建]
version: "0.1"
input:  一组图片(目录 / 文件列表)+ 网格与裁切参数
output: 一个 raw layout slide(append 进 deck.json)和/或一个独立 1920×1080 HTML
triggers:
  - "把这些照片拼成一张"
  - "做个照片墙"
  - "九宫格排一下这些图"
  - "十二宫格"
  - "把这堆照片排成一页"
invocation: |
  python3 plugin/skills/photo-wall/assets/photo-wall.py <图片目录|图片...> \
      --grid auto|9|12|16 --crop square|preserve \
      [--deck <deck.json>] [--standalone] [--key photo-wall-001] [--title 标题]
requires:
  - "pip: Pillow"
produces_layout_pack: false
description: |
  把若干上传/收集来的照片自动排成一张照片墙(九宫格 / 十二宫格 / 十六宫格…),
  产出可直接放进 deck 的页面。用于"把这堆现场照片拼成一页""九宫格排一下"
  这类需求 —— 不是手工摆 HTML,脚本自动选网格、统一裁切、压缩落地。

  产出两种形态(同一段照片墙 HTML+CSS,外层壳不同):
    * 默认:产出一个 raw layout slide,append 进目标 deck.json。可入库、可被
      deck-splice 复用、可和别的页一起放映。
    * --standalone:额外吐一个能双击打开的 1920×1080 单页 HTML。

  排列用 hero 大图策略:按张数选基准网格,若张数不足填满,第一张自动升格为
  2×2 大图占住空位,基本不留空洞。

  Common triggers: "把这些照片拼成一张", "九宫格排一下这些图", "十二宫格".
---

# photo-wall —— 照片墙自动排列

上传/收集若干照片 → 自动排成一张照片墙页面(九宫格 / 十二宫格…)。脚本负责
选网格、统一裁切、压缩落地、生成自包含 HTML,**不要手工摆 HTML**。

## 它解决什么

用户给一堆照片(现场图、团队照、产品图),想要"拼成一页"放进 deck,或单独
出一张图墙。手工写 grid + 一张张调尺寸很繁琐,本 skill 一条命令搞定。

## 何时用 / 何时不用

| 场景 | 用什么 |
|---|---|
| 一堆照片排成规整网格(9/12/16 宫格) | **photo-wall**(本 skill) |
| 客户/合作方 logo 信任墙 | feishu `logo-wall` 或 rolling-deck `tpl-logos` |
| 3 张配图注的产品截图 | rolling-deck `tpl-media-grid` |
| 重新设计某一页的自由排版 | slide-redesign |

## 用法

### 1) 追加进现有 deck(默认形态)

```bash
python3 plugin/skills/photo-wall/assets/photo-wall.py \
    ./我的照片目录 \
    --template 9-grid --crop square \
    --key photo-wall-team --title "团队风采" \
    --deck imports/<deck-id>/render-output-full/deck.json
```

- 不给 `--template` 则按张数自动匹配并(必要时)提示往下取
- 图片处理后落到 deck 同目录的 `assets/<key>/<sha256>.jpg`(同图自动去重)
- 一个 `layout: raw` 的 slide 被 append 进 `deck.json`
- 之后照常 `render-deck.py` 渲染即可

### 2) 独立单页(快速给人看一张图墙)

```bash
python3 plugin/skills/photo-wall/assets/photo-wall.py \
    ./photos --template 12-grid --standalone --out wall.html
```

产出 `wall.html`(双击打开,1920×1080)+ 同目录 `photo-wall-001-assets/`。

### 3) 两者都要

加 `--deck ... --standalone`,同时 append 进 deck **并** 产出单页。

## 固定模板库(7 个)

| 模板名 | 张数 | 排版 |
|---|---|---|
| `4-grid` | 4 | 田字 2×2 均等 |
| `4-hero` | 4 | 1 大图 + 3 竖排 |
| `6-grid` | 6 | 平铺 3×2 |
| `6-hero` | 6 | 1 大图(2×2)+ 5 围 |
| `8-grid` | 8 | 平铺 4×2 |
| `9-grid` | 9 | 平铺 3×3 |
| `12-grid` | 12 | 平铺 4×3 |

`python3 …/photo-wall.py x --list-templates` 可随时列出。每个模板都铺满
1920×1080,**网格高度已实测 == 画布高度**(不会撑破、不会超框)。

## 🛑 标准交互流程(决策链 · Claude 必须照做)

用户给一批照片要做照片墙时,按这条链逐步走。**每个"选"的环节都要把
可视化(线框 / 缩略图 / 对比图)展示给用户再让其选,不要只甩文字、不要替用户默选。**
(这条链同时也是将来前端表单的字段映射。)

### ① 找照片(批次)
用户没指明路径 → `imports/photo-inbox` + `--latest` 自动挑最新批次 → **报给用户
确认**(哪个批次、几张)。mtime 可能误判,非交互环境脚本会 `exit 3` 停下等确认,
确认后 `--yes`。

### ② 选模板(按张数)
1. **数张数**,按张数匹配:`4→4-grid/4-hero` · `6→6-grid/6-hero` · `8→8-grid` ·
   `9→9-grid` · `12→12-grid`。
2. **展示候选模板线框**(`show_widget` 渲染 `assets/templates/templates-sheet.svg`
   或对应张数那几个),让用户肉眼看排版。
3. **多风格**(4/6 张有 grid/hero)→ 展示两个线框,问用户选哪个;
   **单一风格**(8/9/12)→ 展示该线框,确认即可。
4. **张数对不上**(无专属模板)→ **不擅自丢图**。告知:「你有 N 张,没有专属版式,
   建议用『M 张』模板去掉 (N−M) 张,或再补几张凑下一档」,由用户定删/补。
   脚本 `exit 4` 停下,删完重跑或 `--yes` 用前 M 张。往下取:`5→4·7→6·10→9·11→9`;
   `≤3` 张提示多放几张或 `--grid` 自定义。

### ③ 选 hero(仅 hero 模板)
选了 `4-hero`/`6-hero` → `--contact-sheet <out.jpg>` 出**编号缩略图**并展示,
我**看图给推荐**,用户报数字 → `--hero N`。不选默认第 1 张。

### ④ 裁切焦点(自动,通常不打扰用户)
`square` 裁方时:第0档自动给竖图上偏(防切头);第1档我**看图判主体/人脸**写
`--focus-map`(hero 大图尤其要做)。详见下「裁切焦点」节。**这步一般我自己做掉,
不用问用户**,除非用户对某张裁切不满意。

### ⑤ 文字注释(问用户)
1. **要不要加文字?** 不要 → 跳过。
2. 要 → **哪种模式?**(互斥)
   - **统一主题**(所有图同一件事,如一场活动):
     - 我**先看图自动拟一版标题 + 副标题**,**展示给用户确认/修改**,不擅自定稿
     - 选 **位置**:左下(默认)/ 居中
     - 选 **要不要毛玻璃衬底** → **出"纯渐变 vs 毛玻璃"对比图让用户挑**
       (毛玻璃面板只裹住文字,不横铺)
     - → `--overlay-title/--overlay-sub/--overlay-pos/--overlay-glass`
   - **作品集**(每图主题不同):
     - 我**逐张看图、自动写注释草稿**(标题 + 副标题,≤2 行)
     - **让用户确认/修改后再生成**。多图多文字时按下面的方便流程走。

**关键:文字我可以自动生成,但定稿前一定让用户确认/改,不直接拿去生成。**

#### 多图多文字怎么确认最方便(作品集模式)

照片多、每张都要文字时,这样最省事:

1. 先 `--contact-sheet sheet.jpg` 出**编号缩略图**(让用户和文字对得上号)。
2. 我把自动草稿用**编号表格**贴在对话里(`# | 内容 | 标题 | 副标题`),用户可
   **直接在对话里口头改**(「第 3 个标题改成 X、第 5 个副标题删掉」)—— 改几条最快。
3. 要**批量改**时:`--caption-draft caps.tsv` 生成可编辑 TSV(序号/文件名/标题/
   副标题),我把草稿填进去,用户在 Excel / 文本里随便改,存盘;再
   `--caption-map caps.tsv` 读回生成。`--caption-map` 同时支持 `.json` 和 `.tsv`。

### ⑥ 产出形态
**单页 HTML**(`--standalone --out`)和/或 **append 进 deck**(`--deck`)。
⚠️ 单页 = `html + 同名 -assets/ 文件夹`,**两个一起才完整**;交付/移动要一并带上,
别只发 html(否则图全黑)。

### ⑦ 生成后自检
渲染后**务必量一次网格高度 == 1080**(`getBoundingClientRect`),再给用户截图。
这是铁律——曾因 wrapper 没设高度导致网格撑破、只显示部分图。

## 裁切焦点(人脸/主体尽量居中)

`square` 裁方时,焦点决定保留画面哪一块。两层(均零依赖):

- **第0档·自动(常开)**:竖图焦点自动上偏到 `(0.5, 0.40)` —— 人/主体通常在
  上半部,避免「裁掉头顶」;横图保持居中。`smart_centering()` 实现。
- **第1档·Claude 视觉(推荐,做 hero 时尤其用)**:生成前我**看一眼图**,判断
  主体/人脸位置,写一个 `focus.json`(`{文件名: [cx, cy]}`,0~1),用 `--focus-map`
  传入,Pillow 按此裁切。**hero 大图最该这样做** —— 它面积大,裁歪最显眼。
  没列进 map 的图自动回退第0档。

> 不引入 opencv 等本地人脸库:门店/陈列照里脸小、侧脸多,Haar 误检多、收益低;
> Claude 视觉判主体比纯人脸检测更适合这类素材,且零装机摩擦。

## 文字注释(两种模式,互斥)

做 deck 时常要给照片墙配文字。两种场景:

### 模式 1 · 统一主题(整墙一个标题)

所有图是同一件事(如一场活动)→ 整墙最上层一道**底部渐变蒙版**,上面写大标题
+ 副标题。

```bash
… --overlay-title "10月8日 · 立白AI销售赋能工作坊" \
  --overlay-sub "与 20+ 一线销售共创 AI 赋能新范式" \
  [--overlay-pos bottom|center] [--overlay-glass]
```
- `--overlay-pos`:`bottom`(默认,左下编辑风)/ `center`(居中海报风)
- `--overlay-glass`:文字区加毛玻璃衬底(可选)

### 模式 2 · 作品集(每图各自注释)

每张图主题不同(作品集)→ 每张图**各自**底部渐变 + 自己的注释(1~2 行)。

```bash
… --caption-map captions.json
```
`captions.json` 形如 `{"源文件名.jpg": {"title": "门店外观", "sub": "主入口"}}`,
只标了的图才有注释,其余无。**Claude 视觉用法**:我看每张图,自动写注释草稿
(title 一行 + sub 一行)给你改,再写进 json 生成。

> 两者**互斥**:一份墙要么整体一个标题,要么逐图注释,同时给会报错。
> 注释是纯 HTML/CSS 内嵌在 raw slide 里,入 deck、渲染都正常。

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `inputs` | — | 图片目录,或一串图片文件路径(支持 jpg/png/webp/gif/bmp/tiff/heic) |
| `--template` `-t` | 自动 | 指定模板(`9-grid`/`4-hero`…);不给则按张数自动匹配 |
| `--list-templates` | — | 列出全部模板后退出 |
| `--crop` | `square` | `square`=居中裁方,网格最干净;`preserve`=保留原比例(contain) |
| `--key` | `photo-wall-001` | slide key 兼资产目录名(同 deck 内须唯一) |
| `--title` | 空 | slide 标题(写进 `slide.title`,raw 标题同步) |
| `--deck` | — | 给了就 append 进这个 deck.json |
| `--standalone` | off | 额外产出单页 HTML |
| `--out` | `<key>.html` | 单页 HTML 输出路径 |
| `--hero N` | 第1张 | hero 模板里用第 N 张(按排序,1 起)当大图 |
| `--contact-sheet PATH` | — | 只出编号缩略图供选 hero,不生成照片墙 |
| `--focus-map PATH` | — | JSON `{文件名:[cx,cy]}` 指定各图裁切焦点(Claude 视觉判断) |
| `--overlay-title TEXT` | — | 模式1:整墙统一大标题 |
| `--overlay-sub TEXT` | — | 模式1:副标题 |
| `--overlay-pos` | `bottom` | 模式1:`bottom`(左下)/ `center`(居中海报) |
| `--overlay-glass` | off | 模式1:文字区毛玻璃衬底 |
| `--caption-map PATH` | — | 模式2:每图注释表,`.json` 或 `.tsv`(序号/文件名/标题/副标题) |
| `--caption-draft PATH` | — | 模式2:先出可编辑的 TSV 注释草稿(逐图填),不生成 |
| `--yes` `-y` | off | 跳过确认(往下取去图 / `--latest` 选批次) |
| `--grid` | — | 高级:绕过模板用自定义 cols×rows(填格子总数,如 16) |

线框图资产:`assets/templates/templates-sheet.svg`(静态图)+ `wireframe.py`
(生成器,改模板后可重生成)。

## 图片处理

- EXIF 朝向自动修正(手机竖拍照片不会躺倒)
- `square` 用 `ImageOps.fit` 居中裁成 1:1
- 长边压到 1600px、JPEG q85,避免几十张大图把单页撑爆
- SHA256(前 16 位)命名,同一张图只落地一次

## 隔离与复用

- 输出 HTML 的 CSS 全部挂在 `.pw-<key>` 命名空间下,**多张照片墙 slide 共存
  不会样式打架**;`raw` slide 也不依赖任何模板。
- 产出的是标准 `raw` slide,天然能被 **deck-ingest** 入库、**deck-splice** 整页搬运。

## 入库(可选,做完三步走)

```bash
python3 library/db/ingest_deck.py <deck-id> imports/<deck-id>/render-output-full/deck.json
python3 library/db/gen_thumbnails.py --deck <deck-id>
```
