#!/usr/bin/env python3
"""photo-wall — 把若干照片自动排成九宫格 / 十二宫格照片墙。

产出形态(--standalone 开关切换):
  * 默认       : 产出一个 raw layout slide,append 进 deck.json(可入库 / 可被
                 deck-splice 复用 / 可和别的页一起放映)。
  * --standalone: 额外吐一个能双击打开的 1920×1080 单页 HTML。

两条路共用同一段照片墙 HTML+CSS,只是外层壳不同。

排列策略(hero 大图):
  按张数选基准网格(auto: 9→3×3, 12→3×4, 16→4×4 …),若张数 < 格子数,第一张
  自动升格为 2×2 hero 占满空位,基本不留空洞。

裁切:
  --crop square   : object-fit:cover 统一裁成方格,网格最干净(默认)。
  --crop preserve : 保留原始宽高比(配合 hero 仍居中填充)。

图片处理复用 gen_thumbnails 的 Pillow 管线思路:长边压到 ~1600px、JPEG q85,
SHA256 命名落地、同图自动去重。

用法:
    python3 photo-wall.py <图片目录|图片1 图片2 ...> \\
        --grid auto|9|12|16 \\
        --crop square|preserve \\
        --deck imports/<deck>/render-output-full/deck.json   # append 进 deck
    python3 photo-wall.py ./photos --grid 9 --standalone --out wall.html
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("photo-wall 需要 Pillow:  pip install Pillow")

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
            ".heic", ".heif"}
LONG_EDGE = 1600          # 单边最大像素,避免几十张大图撑爆单页
JPEG_QUALITY = 85


def open_image(src: Path) -> "Image.Image":
    """打开图片,自动处理 HEIC/HEIF(iPhone 默认格式)。

    顺序:Pillow 直接读 → pillow-heif(若已装,跨平台)→ macOS `sips` 转 JPEG。
    都不行才报错。返回已 load() 的 PIL Image。
    """
    try:
        im = Image.open(src); im.load(); return im
    except Exception:
        pass
    if src.suffix.lower() in (".heic", ".heif"):
        try:                                   # 跨平台:pillow-heif
            import pillow_heif
            pillow_heif.register_heif_opener()
            im = Image.open(src); im.load(); return im
        except Exception:
            pass
        sips = shutil.which("sips")            # macOS 自带,零安装
        if sips:
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False); tmp.close()
            try:
                subprocess.run([sips, "-s", "format", "jpeg", str(src), "--out", tmp.name],
                               check=True, capture_output=True)
                im = Image.open(tmp.name); im.load(); return im
            finally:
                os.path.exists(tmp.name) and os.unlink(tmp.name)
    raise SystemExit(f"无法读取图片 {src.name}(HEIC 需 `pip install pillow-heif` 或 macOS sips)")

# ── 固定模板库 ───────────────────────────────────────────────────────
# 每个模板铺满 1920×1080 一页。cols/rows 是 CSS grid 轨道定义,hero 是第一张
# 大图的跨格 CSS(None=无 hero)。所有模板的网格高度都 == 画布高度(已实测)。
TEMPLATES = {
    "4-grid":  {"count": 4,  "label": "4 张 · 田字 2×2",  "wire": "2×2 均等",
                "cols": "repeat(2,1fr)", "rows": "repeat(2,1fr)", "hero": None},
    "4-hero":  {"count": 4,  "label": "4 张 · hero+3",   "wire": "1 大 + 3 竖排",
                "cols": "1.6fr 1fr", "rows": "repeat(3,1fr)",
                "hero": "grid-column:1; grid-row:1 / 4"},
    "6-grid":  {"count": 6,  "label": "6 张 · 平铺 3×2",  "wire": "3×2 均等",
                "cols": "repeat(3,1fr)", "rows": "repeat(2,1fr)", "hero": None},
    "6-hero":  {"count": 6,  "label": "6 张 · hero+5",   "wire": "1 大 + 5 围",
                "cols": "repeat(3,1fr)", "rows": "repeat(3,1fr)",
                "hero": "grid-column:1 / 3; grid-row:1 / 3"},
    "8-grid":  {"count": 8,  "label": "8 张 · 平铺 4×2",  "wire": "4×2 均等",
                "cols": "repeat(4,1fr)", "rows": "repeat(2,1fr)", "hero": None},
    "9-grid":  {"count": 9,  "label": "9 张 · 平铺 3×3",  "wire": "3×3 均等",
                "cols": "repeat(3,1fr)", "rows": "repeat(3,1fr)", "hero": None},
    "12-grid": {"count": 12, "label": "12 张 · 平铺 4×3", "wire": "4×3 均等",
                "cols": "repeat(4,1fr)", "rows": "repeat(3,1fr)", "hero": None},
}

# 张数 → 可用模板名(有的张数有多个风格,需让用户选)
COUNT_TEMPLATES = {
    4:  ["4-grid", "4-hero"],
    6:  ["6-grid", "6-hero"],
    8:  ["8-grid"],
    9:  ["9-grid"],
    12: ["12-grid"],
}
AVAILABLE_COUNTS = sorted(COUNT_TEMPLATES)   # [4, 6, 8, 9, 12]

# 张数 → (列, 行) 通用网格(--grid 自定义时的兜底,不在固定模板内)
GRID_PRESETS = {
    4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 12: (4, 3), 16: (4, 4),
    20: (5, 4), 25: (5, 5),
}


def match_template_count(n: int) -> tuple[int | None, int]:
    """按张数匹配模板。返回 (匹配到的模板张数, 需去掉的张数)。

    - n 正好有专属模板 → (n, 0)
    - n 无专属模板 → 往下取最近的模板张数,告知去掉多出的几张 → (c, n-c)
    - n 比最小模板还小 → (None, 0),交给通用网格兜底
    """
    if n in COUNT_TEMPLATES:
        return n, 0
    below = [c for c in AVAILABLE_COUNTS if c < n]
    if below:
        c = max(below)
        return c, n - c
    return None, 0


# ---------------------------------------------------------------- 收图

def collect_images(inputs: list[str]) -> list[Path]:
    """inputs 可以是目录、通配后的文件列表、或单个文件。返回排序后的图片路径。

    注意:目录只扫一层(不递归)—— 一个目录就是一个批次。要区分多个批次,
    给每个批次建一个子文件夹,生成时指向那个子文件夹(见 find_batches)。
    """
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and child.suffix.lower() in IMG_EXTS:
                    paths.append(child)
        elif p.is_file() and p.suffix.lower() in IMG_EXTS:
            paths.append(p)
        else:
            print(f"  ! 跳过(不是图片或不存在): {raw}", file=sys.stderr)
    return paths


def find_batches(inputs: list[str]) -> list[tuple[Path, int]]:
    """在给定目录的子文件夹里找「批次」(含图片的子文件夹)。

    返回 [(子文件夹路径, 图片数), ...]。用于:同事指向了父目录(如
    imports/photo-inbox)而非具体批次时,把里面的批次列出来引导他。
    """
    batches: list[tuple[Path, int]] = []
    for raw in inputs:
        p = Path(raw)
        if not p.is_dir():
            continue
        for child in sorted(p.iterdir()):
            if child.is_dir():
                n = sum(1 for f in child.iterdir()
                        if f.is_file() and f.suffix.lower() in IMG_EXTS)
                if n:
                    batches.append((child, n))
    return batches


def pick_latest_batch(parent: str) -> Path | None:
    """懒人模式:在 parent 下挑「最近改动」的含图子文件夹。

    用于「同事刚新建文件夹扔了照片、不命名也不报路径」的场景 —— 直接拿最新
    那批。按 mtime 取最大。没有任何批次则返回 None。
    """
    batches = find_batches([parent])
    if not batches:
        return None
    return max((path for path, _ in batches), key=lambda d: d.stat().st_mtime)


# ---------------------------------------------------------------- 图片归一

def smart_centering(w: int, h: int) -> tuple[float, float]:
    """裁方时的默认焦点(功能2·第0档,零依赖)。

    竖图(高 > 宽)裁成方块时,死板居中会把头顶切掉 —— 因为人/主体通常在画面
    上半部。所以竖图焦点往上偏到 0.40;横图/方图保持居中。
    """
    if h > w * 1.1:
        return (0.5, 0.40)
    return (0.5, 0.5)


def normalize_image(src: Path, crop_square: bool,
                    focus: tuple[float, float] | None = None) -> bytes:
    """读图 → 处理 EXIF 朝向 → (可选)按焦点裁方 → 压缩长边 → 返回 JPEG bytes。

    focus 是裁切焦点 (cx, cy),取值 0~1。来源(功能2):
      * Claude 视觉(第1档):我看一眼图、判断主体/人脸位置后传进来
      * 未指定 → smart_centering 兜底(第0档:竖图上偏)
    """
    im = open_image(src)
    im = ImageOps.exif_transpose(im)        # 修正手机照片朝向
    im = im.convert("RGB")
    if crop_square:
        w, h = im.size
        cx, cy = focus if focus else smart_centering(w, h)
        cx = min(max(cx, 0.0), 1.0); cy = min(max(cy, 0.0), 1.0)
        side = min(im.size)
        im = ImageOps.fit(im, (side, side), Image.LANCZOS, centering=(cx, cy))
    # 压缩长边
    w, h = im.size
    if max(w, h) > LONG_EDGE:
        scale = LONG_EDGE / max(w, h)
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def write_assets(images: list[Path], asset_dir: Path, crop_square: bool,
                 focus_map: dict | None = None) -> list[str]:
    """处理并落地每张图,SHA256 命名去重。返回相对 asset_dir 的文件名列表(保持顺序)。

    focus_map: {源文件名: [cx, cy]} —— 给某些图指定裁切焦点(Claude 视觉判断的),
    没列出的图走 smart_centering 兜底。
    """
    asset_dir.mkdir(parents=True, exist_ok=True)
    focus_map = focus_map or {}
    rels: list[str] = []
    seen: dict[str, str] = {}
    for src in images:
        focus = focus_map.get(src.name)
        data = normalize_image(src, crop_square, tuple(focus) if focus else None)
        digest = hashlib.sha256(data).hexdigest()[:16]
        if digest in seen:
            rels.append(seen[digest])              # 同图去重
            continue
        fname = f"{digest}.jpg"
        (asset_dir / fname).write_bytes(data)
        seen[digest] = fname
        rels.append(fname)
    return rels


def make_contact_sheet(images: list[Path], out_path: Path, cols: int = 4) -> Path:
    """给一批照片做一张「编号缩略图」联系表(功能1:让人选哪张当 hero)。

    每张图左上角标 1、2、3…,顺序与 collect_images 一致;用户看图报数字,
    生成时用 --hero N 指定那张当大图。
    """
    from PIL import ImageDraw
    n = len(images)
    cols = min(cols, n)
    rows = math.ceil(n / cols)
    th = 360                          # 单格缩略宽
    cw, ch = th, int(th * 0.72)
    pad = 10
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * pad,
                              rows * ch + (rows + 1) * pad), (24, 24, 30))
    draw = ImageDraw.Draw(sheet)
    for i, src in enumerate(images):
        r, c = divmod(i, cols)
        x = pad + c * (cw + pad); y = pad + r * (ch + pad)
        im = ImageOps.exif_transpose(open_image(src)).convert("RGB")
        im = ImageOps.fit(im, (cw, ch), Image.LANCZOS)
        sheet.paste(im, (x, y))
        # 编号角标
        badge = 30
        draw.rectangle([x, y, x + badge, y + badge], fill=(59, 130, 246))
        draw.text((x + 9, y + 6), str(i + 1), fill=(255, 255, 255))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "JPEG", quality=88)
    return out_path


# ---------------------------------------------------------------- 渲染 HTML

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_wall_html(rels: list[str], asset_prefix: str, tpl: dict,
                     crop_square: bool, key: str,
                     overlay: dict | None = None,
                     captions: list | None = None) -> str:
    """生成带 pw- 前缀作用域 CSS 的照片墙 HTML 片段(供 raw slide 内嵌)。

    tpl: 模板规格 dict(cols/rows/hero)。网格 height:100% 撑满 wrapper(==1080)。
    overlay: 模式1·统一主题。{"title","sub","pos":bottom|center,"glass":bool} 或 None。
    captions: 模式2·作品集。与 rels 等长的列表,每项 {"title","sub"} 或 None。
    """
    fit = "cover" if crop_square else "contain"
    hero_css = tpl.get("hero")
    tiles = []
    for i, rel in enumerate(rels):
        cls = "pw-tile pw-hero" if (hero_css and i == 0) else "pw-tile"
        cap = ""
        if captions and i < len(captions) and captions[i]:
            c = captions[i]
            sub = f'<span class="pw-cd">{_esc(c.get("sub"))}</span>' if c.get("sub") else ""
            cap = f'<figcaption><span class="pw-ct">{_esc(c.get("title",""))}</span>{sub}</figcaption>'
        tiles.append(f'<figure class="{cls}"><img src="{asset_prefix}{rel}" alt="">{cap}</figure>')
    tiles_html = "\n        ".join(tiles)
    ns = f"pw-{key}"   # 唯一作用域:用 slide-key 作 CSS 命名空间,避免 raw slide 互相打架
    hero_rule = f".{ns} .pw-hero {{ {hero_css}; }}" if hero_css else ""

    overlay_html = ""
    if overlay and overlay.get("title"):
        pos = overlay.get("pos", "bottom")
        glass = " glass" if overlay.get("glass") else ""
        sub = f'<div class="pw-sub">{_esc(overlay.get("sub"))}</div>' if overlay.get("sub") else ""
        overlay_html = (f'<div class="pw-overlay pos-{pos}{glass}"><div class="pw-textbox">'
                        f'<div class="pw-hl">{_esc(overlay["title"])}</div>{sub}</div></div>')
    return f"""<div class="{ns}">
      <style>
        .{ns} {{
          width: 100%; height: 100%; position: relative;
          display: block; box-sizing: border-box;
        }}
        .{ns} .pw-grid {{
          width: 100%; height: 100%;
          display: grid;
          grid-template-columns: {tpl['cols']};
          grid-template-rows: {tpl['rows']};
          gap: 14px;
          padding: 48px;
          box-sizing: border-box;
        }}
        .{ns} .pw-tile {{
          position: relative;
          margin: 0; overflow: hidden; border-radius: 16px;
          background: #0e0e12;
          box-shadow: 0 6px 20px rgba(0,0,0,.18);
        }}
        .{ns} .pw-tile img {{
          width: 100%; height: 100%; object-fit: {fit}; display: block;
        }}
        {hero_rule}
        .{ns} figcaption {{
          position: absolute; left: 0; right: 0; bottom: 0;
          padding: 20px 22px 18px; color: #fff;
          font-family: -apple-system, system-ui, "PingFang SC", sans-serif;
          background: linear-gradient(to top, rgba(0,0,0,.88) 0%, rgba(0,0,0,.42) 58%, transparent 100%);
        }}
        .{ns} .pw-ct {{ display: block; font-size: 26px; font-weight: 700; line-height: 1.25; }}
        .{ns} .pw-cd {{ display: block; font-size: 18px; font-weight: 400; color: rgba(255,255,255,.82); margin-top: 4px; }}
        .{ns} .pw-overlay {{
          position: absolute; inset: 0; pointer-events: none;
          display: flex; flex-direction: column;
          font-family: -apple-system, system-ui, "PingFang SC", sans-serif;
        }}
        .{ns} .pw-overlay.pos-bottom {{ justify-content: flex-end; padding: 72px;
          background: linear-gradient(to top, rgba(0,0,0,.84) 0%, rgba(0,0,0,.46) 16%, rgba(0,0,0,0) 40%); }}
        .{ns} .pw-overlay.pos-center {{ justify-content: center; align-items: center; text-align: center;
          padding: 72px; background: rgba(0,0,0,.42); }}
        .{ns} .pw-textbox {{ align-self: flex-start; max-width: 88%; }}
        .{ns} .pw-overlay.pos-center .pw-textbox {{ align-self: center; }}
        .{ns} .pw-overlay.glass .pw-textbox {{ backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
          background: rgba(0,0,0,.28); padding: 24px 30px; border-radius: 16px;
          width: fit-content; max-width: 88%; }}
        .{ns} .pw-hl {{ font-size: 62px; font-weight: 800; color: #fff; letter-spacing: 1px; }}
        .{ns} .pw-sub {{ font-size: 30px; color: rgba(255,255,255,.86); margin-top: 16px; }}
      </style>
      <div class="pw-grid">
        {tiles_html}
      </div>
      {overlay_html}
    </div>"""


def uniform_template(cols: int, rows: int) -> dict:
    """把通用 cols×rows 网格包成一个临时模板规格(供 --grid 自定义用)。"""
    return {"cols": f"repeat({cols},1fr)", "rows": f"repeat({rows},1fr)", "hero": None}


STANDALONE_SHELL = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>照片墙 · {key}</title>
<style>
  html,body{{margin:0;height:100%;background:#000;display:grid;place-items:center}}
  .pw-stage{{width:1920px;height:1080px;background:#15151b;position:relative;overflow:hidden}}
</style></head>
<body><div class="pw-stage">{body}</div></body></html>"""


# ---------------------------------------------------------------- 产出

def build_slide(rels, asset_prefix, tpl, crop_square, key, title,
                overlay=None, captions=None):
    html = render_wall_html(rels, asset_prefix, tpl, crop_square, key, overlay, captions)
    slide = {"key": key, "layout": "raw", "data": {"html": html}}
    if title:
        slide["title"] = title
    return slide


def append_to_deck(deck_path: Path, slide: dict):
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    deck.setdefault("slides", []).append(slide)
    deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")


def write_caption_draft(images: list[Path], out_path: Path):
    """写一份可编辑的 TSV 注释草稿(序号/文件名/标题/副标题),供逐图填写。

    序号与编号缩略图一致,人对着缩略图填标题/副标题列即可,再用 --caption-map 读回。
    """
    lines = ["序号\t文件名\t标题\t副标题"]
    for i, src in enumerate(images, 1):
        lines.append(f"{i}\t{src.name}\t\t")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_caption_map(path: str) -> dict:
    """读注释表,支持 .json 或 .tsv。返回 {文件名: {title, sub}}。

    TSV 容错:自动找含图片扩展名的列当文件名,后两列作标题/副标题;跳过表头与 # 注释。
    """
    p = Path(path)
    if p.suffix.lower() == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    out: dict = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = [c.strip() for c in line.split("\t")]
        idx = next((i for i, c in enumerate(cols)
                    if any(c.lower().endswith(e) for e in IMG_EXTS)), None)
        if idx is None:                       # 没有文件名列(表头等)→ 跳过
            continue
        title = cols[idx + 1] if len(cols) > idx + 1 else ""
        sub = cols[idx + 2] if len(cols) > idx + 2 else ""
        if title or sub:
            out[cols[idx]] = {"title": title, "sub": sub}
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="把若干照片自动排成九宫格/十二宫格照片墙")
    ap.add_argument("inputs", nargs="+", help="图片目录,或一串图片文件路径")
    ap.add_argument("--latest", action="store_true",
                    help="懒人模式:把 inputs 当父目录,自动挑里面最新改动的批次子文件夹")
    ap.add_argument("--yes", "-y", action="store_true",
                    help="跳过确认(--latest 选批次 / 往下取模板去图)")
    ap.add_argument("--template", "-t", choices=sorted(TEMPLATES),
                    help="指定固定模板(如 9-grid / 4-hero);不给则按张数自动匹配")
    ap.add_argument("--list-templates", action="store_true",
                    help="列出所有固定模板后退出")
    ap.add_argument("--hero", type=int, metavar="N",
                    help="hero 模板里用第 N 张(按排序,1 起)当大图;不给则用第 1 张")
    ap.add_argument("--contact-sheet", metavar="PATH",
                    help="只生成编号缩略图(供选 hero),不出照片墙;给输出路径")
    ap.add_argument("--focus-map", metavar="PATH",
                    help="JSON {文件名:[cx,cy]} 指定各图裁切焦点(Claude 视觉判断)")
    # ── 文字注释(模式1·统一主题 / 模式2·作品集,二选一)──
    ap.add_argument("--overlay-title", metavar="TEXT",
                    help="模式1:整墙统一标题(底部渐变蒙版上)")
    ap.add_argument("--overlay-sub", metavar="TEXT", help="模式1:副标题")
    ap.add_argument("--overlay-pos", choices=["bottom", "center"], default="bottom",
                    help="模式1:标题位置(默认左下)")
    ap.add_argument("--overlay-glass", action="store_true", help="模式1:文字区加毛玻璃衬底")
    ap.add_argument("--caption-map", metavar="PATH",
                    help="模式2:每图注释表,.json 或 .tsv(序号/文件名/标题/副标题)")
    ap.add_argument("--caption-draft", metavar="PATH",
                    help="模式2:先生成一份可编辑的 TSV 注释草稿(逐图填),不出照片墙")
    ap.add_argument("--grid", default=None,
                    help="高级:绕过模板,用自定义 cols×rows(填格子总数,如 16)")
    ap.add_argument("--crop", choices=["square", "preserve"], default="square")
    ap.add_argument("--key", default="photo-wall-001", help="slide key / 资产目录名")
    ap.add_argument("--title", default="", help="slide 标题(可选)")
    ap.add_argument("--deck", help="目标 deck.json 路径;给了就 append 进去")
    ap.add_argument("--standalone", action="store_true", help="额外产出单页 HTML")
    ap.add_argument("--out", help="单页 HTML 输出路径(默认 <key>.html)")
    args = ap.parse_args()

    if args.list_templates:
        print("固定模板:")
        for name, t in TEMPLATES.items():
            print(f"  {name:9} {t['label']:18} ({t['wire']})")
        print("\n按张数自动匹配:" + " · ".join(
            f"{c}→{'/'.join(COUNT_TEMPLATES[c])}" for c in AVAILABLE_COUNTS))
        return

    if args.latest:
        latest = pick_latest_batch(args.inputs[0])
        if not latest:
            sys.exit(f"--latest:{args.inputs[0]} 下没有任何含图片的批次子文件夹。")
        # 列出选中批次的概况,供人确认(mtime 可能误判,不直接生成)
        sample = sorted(f.name for f in latest.iterdir()
                        if f.is_file() and f.suffix.lower() in IMG_EXTS)
        print(f"  · 懒人模式选中最新批次:{latest}")
        print(f"    共 {len(sample)} 张:" + "、".join(sample[:5])
              + ("…" if len(sample) > 5 else ""))
        if not args.yes:
            if sys.stdin.isatty():
                # 终端里交互确认
                ans = input("    用这批吗?[回车=确认 / n=取消] ").strip().lower()
                if ans in ("n", "no", "否"):
                    sys.exit("已取消。请用 --grid 指定其它批次的具体路径。")
            else:
                # 非交互(Claude 代跑)—— 停下让上层确认,确认后带 --yes 重跑
                print("    ⏸ 非交互环境:确认无误后,加 --yes 重跑这条命令即可。",
                      file=sys.stderr)
                sys.exit(3)
        args.inputs = [str(latest)]

    images = collect_images(args.inputs)
    if not images:
        # 没在当前层找到图 —— 大概率是指向了父目录而非具体批次。把里面的
        # 批次子文件夹列出来引导,而不是甩一句冷冰冰的报错。
        batches = find_batches(args.inputs)
        if batches:
            print("没找到图片,但发现了这些批次子文件夹 —— 请指向其中一个:",
                  file=sys.stderr)
            for path, n in batches:
                print(f"    {path}    ({n} 张)", file=sys.stderr)
            example = batches[0][0]
            print(f"\n例如:\n    python3 {sys.argv[0]} {example} "
                  f"--grid 9 --standalone --out ~/Desktop/wall.html", file=sys.stderr)
            sys.exit(2)
        sys.exit("没有找到任何图片(检查路径,或确认目录里有 jpg/png/webp 等)。")

    # 功能1·选 hero 第一步:只出编号缩略图供人挑,不生成照片墙
    if args.contact_sheet:
        out = make_contact_sheet(images, Path(args.contact_sheet))
        print(f"  ✓ 编号缩略图:{out}")
        print(f"    看图报数字,生成时加 --hero N(共 {len(images)} 张)")
        return

    # 模式2·先出可编辑的注释草稿 TSV(逐图填),不生成照片墙
    if args.caption_draft:
        write_caption_draft(images, Path(args.caption_draft))
        print(f"  ✓ 注释草稿:{args.caption_draft}(共 {len(images)} 张)")
        print(f"    填好 标题/副标题 两列,再用 --caption-map {args.caption_draft} 生成")
        return

    # 功能1·选 hero 第二步:把第 N 张挪到最前 → 它成为 hero(也影响 grid 顺序)
    if args.hero:
        if not (1 <= args.hero <= len(images)):
            sys.exit(f"--hero {args.hero} 越界:本批共 {len(images)} 张。")
        i = args.hero - 1
        images = [images[i]] + images[:i] + images[i + 1:]
        print(f"  · hero 用第 {args.hero} 张:{images[0].name}")

    # 功能2·第1档:载入 Claude 视觉判断的裁切焦点
    focus_map = {}
    if args.focus_map:
        focus_map = json.loads(Path(args.focus_map).read_text(encoding="utf-8"))

    # 文字注释:模式1(统一主题)与模式2(作品集)互斥
    if args.overlay_title and args.caption_map:
        sys.exit("--overlay-title(统一主题)与 --caption-map(作品集)二选一,别同时给。")
    overlay = None
    if args.overlay_title:
        overlay = {"title": args.overlay_title, "sub": args.overlay_sub,
                   "pos": args.overlay_pos, "glass": args.overlay_glass}
    caption_map = {}
    if args.caption_map:
        caption_map = load_caption_map(args.caption_map)

    n = len(images)

    # ── 选模板 ──────────────────────────────────────────────────────
    # 优先级:--grid 自定义 > --template 指定 > 按张数自动匹配(含往下取)
    if args.grid:                                   # 高级:绕过模板用通用网格
        cells = int(args.grid)
        cols, rows = GRID_PRESETS.get(cells,
            (math.ceil(math.sqrt(cells)), math.ceil(cells / math.ceil(math.sqrt(cells)))))
        tpl = uniform_template(cols, rows)
        need = cols * rows
        if n > need:
            print(f"  ! {n} 张超过 {cols}×{rows}={need} 格,只用前 {need} 张。", file=sys.stderr)
        images = images[:need]
    elif args.template:                             # 显式指定模板
        tpl = TEMPLATES[args.template]
        need = tpl["count"]
        if n != need:
            print(f"  ! 模板 {args.template} 需 {need} 张,你有 {n} 张 → "
                  f"{'多的丢弃' if n > need else '不足留空'},用前 {min(n, need)} 张。",
                  file=sys.stderr)
        images = images[:need]
    else:                                           # 按张数自动匹配
        matched, removed = match_template_count(n)
        if matched is None:
            sys.exit(f"{n} 张照片太少(最小模板是 4 张)。用 --grid 自定义,或多放几张。")
        if removed > 0:
            # 数量对不上 —— 往下取最近模板,提示去掉多出的,不擅自丢图
            nxt = min((c for c in AVAILABLE_COUNTS if c > n), default=None)
            tip = f";或再补 {nxt - n} 张凑「{nxt} 张」模板" if nxt else ""
            print(f"  ! 你有 {n} 张,没有专属版式。为排版美观,建议用「{matched} 张」"
                  f"模板 —— 去掉 {removed} 张{tip}。", file=sys.stderr)
            if not args.yes:
                print(f"    确认后:删掉 {removed} 张照片重跑,或加 --yes 用前 {matched} 张。",
                      file=sys.stderr)
                sys.exit(4)
            images = images[:matched]
        # 选定张数的模板:多风格的取第一个(grid),Claude 选择时会展示线框让用户挑
        names = COUNT_TEMPLATES[matched]
        tpl = TEMPLATES[names[0]]
        if len(names) > 1:
            print(f"  · {matched} 张有多个风格:{' / '.join(names)};"
                  f"默认用 {names[0]},换风格加 --template {names[1]}", file=sys.stderr)

    crop_square = args.crop == "square"
    label = tpl.get("label", f"{args.grid} 自定义网格")
    print(f"  · {len(images)} 张图 → 模板「{label}」,裁切={args.crop}")

    # 决定资产落点:有 deck 就放在 deck 同目录的 assets/<key>/,否则放 out 同目录
    if args.deck:
        deck_path = Path(args.deck)
        asset_dir = deck_path.parent / "assets" / args.key
        asset_prefix = f"assets/{args.key}/"
    else:
        out_path = Path(args.out or f"{args.key}.html")
        asset_dir = out_path.parent / f"{args.key}-assets"
        asset_prefix = f"{args.key}-assets/"

    # 模式2:把 caption-map(按源文件名)对齐到最终图片顺序
    captions = None
    if caption_map:
        captions = [caption_map.get(src.name) for src in images]
        got = sum(1 for c in captions if c)
        print(f"  · 作品集模式:{got}/{len(images)} 张有注释")
    if overlay:
        print(f"  · 统一主题模式:「{overlay['title']}」({overlay['pos']}"
              f"{',毛玻璃' if overlay['glass'] else ''})")

    rels = write_assets(images, asset_dir, crop_square, focus_map)
    slide = build_slide(rels, asset_prefix, tpl, crop_square, args.key, args.title,
                        overlay, captions)

    if args.deck:
        append_to_deck(Path(args.deck), slide)
        print(f"  ✓ 已 append 进 {args.deck}  (slide key: {args.key})")

    if args.standalone or not args.deck:
        out_path = Path(args.out or f"{args.key}.html")
        body = render_wall_html(rels, asset_prefix, tpl, crop_square, args.key,
                                overlay, captions)
        out_path.write_text(STANDALONE_SHELL.format(key=args.key, body=body), encoding="utf-8")
        print(f"  ✓ 单页 HTML: {out_path}")


if __name__ == "__main__":
    main()
