# 照片墙 photo-wall · 同事上手教程

把若干照片自动排成一张九宫格 / 十二宫格图墙。3 分钟上手。

---

## ① 照片放哪?(最常问)

**没有上传按钮。把照片放进一个文件夹,就算"上传"了。**

推荐用项目里的固定收件夹,**一个批次建一个子文件夹**:

```
imports/photo-inbox/
  ├── 2026-06-29-立白活动现场/     ← 批次 A(把这批照片拖进来)
  ├── 2026-06-30-康师傅团队照/     ← 批次 B
  └── 2026-07-01-门店开业/         ← 批次 C
```

**子文件夹叫什么名字都行 —— 没有强制命名规则。** 脚本只读文件夹里的图片,
不看名字。「新建文件夹」「未命名」「aaa」照样跑。`日期-主题` 只是建议,方便
你以后翻找而已。
> `imports/` 不入库,放客户照片安全。也可以用桌面上任意文件夹,记住路径就行。

**懒人玩法(推荐给同事):** 同事只要「新建个文件夹、把照片扔进去」,不用命名、
不用记路径。生成时加 `--latest`,脚本自动挑收件夹里**最新改动的那批**:

```bash
python3 plugin/skills/photo-wall/assets/photo-wall.py imports/photo-inbox \
    --latest --standalone --out ~/Desktop/wall.html
```

不指定模板时,脚本**按张数自动匹配模板**(9 张→3×3,4 张→田字…),数量对不上
会提示你删/补几张。或者干脆跟 Claude 说「把我刚扔进 photo-inbox 的那批排成照片墙」,
Claude 会把候选模板的线框图展示给你看再让你选。

`--latest` 会**先报选中了哪批、几张、有哪些文件,让你确认**再生成(防止 mtime
误判选错批)。终端里弹 y/n;Claude 代跑时会把选中的批次转述给你,确认后才动手。

**⚠️ 不加 `--latest` 时,要指向具体的批次子文件夹,不是父目录 `photo-inbox`。**
万一指错了父目录,脚本会把里面的批次列出来提示你(不会瞎跑)。

---

## ② 怎么生成?两种方式,任选

### 方式 A · 跟 Claude 说大白话(推荐,不用记命令)

在 Claude Code 里直接说:

> 用 photo-wall 把 `imports/photo-inbox` 里的照片排成照片墙,出个单页给我看

Claude 会数张数、把候选模板线框图展示给你挑,再生成、截图给你看。换"保留原比例"
"加标题"都直接说。

### 方式 B · 自己跑一条命令

```bash
python3 plugin/skills/photo-wall/assets/photo-wall.py imports/photo-inbox \
    --template 9-grid --standalone --out ~/Desktop/wall.html
```

跑完桌面会出现 `wall.html`,**双击就能看**(1920×1080 整页)。
全部模板:`… x --list-templates`。

---

## ③ 常用调整

| 想要 | 加这个参数 |
|---|---|
| 按张数自动匹配模板 | 不加 `--template`(默认) |
| 指定某个模板 | `--template 12-grid` / `--template 4-hero` |
| 看所有模板 | `--list-templates` |
| 不裁切、保留原始比例 | `--crop preserve`（默认 `square` 居中裁方） |
| 给这页加标题 | `--title "活动现场"` |
| 直接拼进某个 deck | `--deck imports/<deck-id>/render-output-full/deck.json` |

---

## ④ 三个要知道的脾气

1. **裁切**:默认把每张图居中裁成正方形(网格最齐),人像可能被切。
   觉得切得狠 → 加 `--crop preserve`。
2. **张数对不上**:比如 7 张排 9 宫格 —— **一张都不会丢**,要么第一张升成
   2×2 大图补满,要么末尾留 1-2 个空位。
3. **太多张**:超过网格容量会只取前 N 张并提示,其余建议再排一页。

---

## ⑤ 完整体验(拿示例图先跑一遍)

`imports/photo-inbox/2026-06-29-示例批次/` 里已放了 7 张彩色示例图,直接:

```bash
python3 plugin/skills/photo-wall/assets/photo-wall.py \
    imports/photo-inbox/2026-06-29-示例批次 \
    --template 6-grid --standalone --out ~/Desktop/wall-demo.html
```

打开桌面的 `wall-demo.html` 看效果。满意后把示例图换成你自己的照片即可。
（7 张照片若不指定模板,脚本会建议你用「6 张」模板去掉 1 张,或补 1 张凑「8 张」。)
