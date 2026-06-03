#!/usr/bin/env python3
"""
Re-apply the user's 10-item slide fixes to deck.json (so they survive
re-renders). Then re-render index.html. Items #3 (slide 5 phone frames)
and #4 (slide 6 column animation) are skipped — they require visual
co-design with the user.
"""
import json, re, sys
from pathlib import Path

DECK = Path("/Users/liukai/dev/RollingAI DeckBuilder/imports/RollingAI分享/render-output-full/deck.json")
data = json.loads(DECK.read_text(encoding="utf-8"))


def slide(key):
    for s in data["slides"]:
        if s["key"] == key:
            return s
    raise KeyError(key)


def edit_html(key, fn):
    s = slide(key)
    old = s["data"]["html"]
    new = fn(old)
    if old == new:
        print(f"  [{key}] no change")
        return False
    s["data"]["html"] = new
    return True


# ── #1 · slide-001: enlarge the black block over 豆包生成 watermark ─────────
def fix1(html):
    # Current: <div class="el iwa-fill" style="left:1669...top:1020px;width:304px;height:105px;background:rgba(6,6,4,1.000);..."
    # Enlarge to cover bottom-right more generously.
    return re.sub(
        r'(<div class="el iwa-fill" style="left:)1669px;top:1020px;width:304px;height:105px(;background:rgba\(6,6,4,)',
        r'\g<1>1500px;top:1010px;width:420px;height:70px\g<2>',
        html,
    )
print("#1 slide-001 enlarge black watermark cover")
edit_html("slide-001", fix1)


# ── #2 · slide-002: brighten + bullet-ify + line-height the bio ──────────
def fix2(html):
    # Find the bio div (left:1001 top:460 width:852 ...)
    pattern = re.compile(
        r'<div class="el" style="left:1001\.0px;top:460\.0px;width:852\.0px;'
        r'min-height:371\.0px;color:#FEFFFE;font-family:[^"]*;font-size:28\.0px;'
        r'font-weight:100;font-style:normal;line-height:1\.4;text-align:left;">'
        r'(.*?)</div>',
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return html
    raw = m.group(1)
    # Split on <br>
    items = [x.strip() for x in raw.split("<br>") if x.strip()]
    # Build <ul>. Use • prefix character approach via list-style-type:disc.
    # font-weight: 100 → 400 (much more legible at small size).
    bullets = "\n".join(f"<li>{x}</li>" for x in items)
    new_div = (
        f'<div class="el" style="left:1001.0px;top:460.0px;width:852.0px;'
        f'min-height:371.0px;color:#FFFFFF;'
        f"font-family:'PingFang SC','Microsoft YaHei','Source Han Sans SC','Noto Sans SC',sans-serif;"
        f'font-size:28.0px;font-weight:400;font-style:normal;line-height:1.8;'
        f'text-align:left;">'
        f'<ul style="margin:0;padding-left:1.4em;list-style:disc;">'
        f'{bullets}'
        f'</ul></div>'
    )
    return pattern.sub(new_div, html, count=1)
print("#2 slide-002 bio bullets + brightness + spacing")
edit_html("slide-002", fix2)


# ── #6 · slide-036: wrap "翻天覆地" in white-space: nowrap ────────────────
def fix6(html):
    return html.replace(
        "世界每6个月就翻天覆地",
        '世界每6个月就<span style="white-space:nowrap;">翻天覆地</span>',
    )
print("#6 slide-036 翻天覆地 nowrap")
edit_html("slide-036", fix6)


# ── #7a · slide-052 (page 33): left-align text, line 1 green, 2-3 white ──
def fix33(html):
    pattern = re.compile(
        r'(<div class="el shape" style="[^"]*color:)#22FF09([^"]*line-height:1\.35;padding:8px 16px;)'
        r'text-align:(center)(;display:flex;align-items:center;justify-content:)(center)(;[^"]*">)'
        r'建立竞争壁垒<br>从显性资产堆叠，到隐性资产的萃取<br>做一艘船，不要做柱子'
        r'(</div>)',
    )
    repl = (
        # Outer div: align stays center vertically; horizontal flex switch to flex-start
        # (we'll render three <div>s inside so each line is its own block, left-aligned).
        r'\g<1>#FFFFFF\g<2>text-align:left\g<4>flex-start\g<6>'
        '<div style="width:100%;">'
        '<div style="color:#22FF09;">建立竞争壁垒</div>'
        '<div>从显性资产堆叠，到隐性资产的萃取</div>'
        '<div>做一艘船，不要做柱子</div>'
        '</div>'
        r'\g<7>'
    )
    return pattern.sub(repl, html, count=1)
print("#7 (item 7) slide-052 (page 33) text recolor + left-align")
edit_html("slide-052", fix33)


# ── #8 · slide-063: preserve RollingAI logo aspect ratio ─────────────────
def fix8(html):
    # Image natural ratio is 372/75 = 4.96. Display 186×24 is ratio 7.75 (squished).
    # Use displayed width 186, correct height = 186/4.96 = 37.5.
    # Also pin top so the logo bottom still sits near y=1054.
    return re.sub(
        r'(<img class="el" src="assets/slide-063/image4-25283\.png" style="left:58\.0px;)'
        r'top:1030\.0px;width:186\.0px;height:24\.0px(;object-fit:cover;">)',
        r'\g<1>top:1018.0px;width:186.0px;height:37.0px\g<2>',
        html,
    )
print("#8 slide-063 logo aspect ratio")
edit_html("slide-063", fix8)


# ── #9b · slide-067: change slide bg color so the white bar matches image ─
def fix9b(html):
    # The image starts at top:103px. Slide bg fills the 0..103 strip above.
    # Sample the image's top-edge color and use that as bg.
    from PIL import Image
    p = Path(DECK).parent / "assets" / "_shared" / "2537dc8e75be6222d6750-25353.jpeg"
    if not p.is_file():
        # try unshared
        p = list((Path(DECK).parent / "assets" / "slide-067").glob("*.jpeg"))
        p = p[0] if p else None
    if p:
        im = Image.open(p)
        # average the top row
        px = im.load()
        w = im.size[0]
        sample = [px[x, 0] for x in range(0, w, max(1, w // 50))]
        # average channels
        r = sum(c[0] for c in sample) // len(sample)
        g = sum(c[1] for c in sample) // len(sample)
        b = sum(c[2] for c in sample) // len(sample)
        bg = f"#{r:02X}{g:02X}{b:02X}"
        print(f"   slide-067 sampled top-edge color: {bg}")
    else:
        bg = "#E8E8EA"
    return re.sub(
        r"(\.slide\[data-slide-key='slide-067'\] \{ background: )#FFFFFF",
        r"\1" + bg,
        html,
    )
print("#9b slide-067 slide bg → match image top edge")
edit_html("slide-067", fix9b)


# ── #10 · slide-073 (page 52): video onended → reveal mask, no loop ──────
def fix10(html):
    # Strip `loop` from the video tag and add onended JS that fades in the mask.
    # The mask is the iwa-fill / shape div at (-14, -26, 1948×1132).
    # Strategy: give the video an id, give the mask an initial opacity:0
    # + transition, and onended set opacity:1.
    # Find the <video ...> tag for the 美宜佳 video.
    html = re.sub(
        r'(<video class="el [^"]*" data-src="[^"]*美宜佳[^"]*"[^>]*) loop ',
        r'\1 ',
        html,
    )
    # Add id + onended attribute
    html = re.sub(
        r'(<video class="el [^"]*"[^>]*data-src="[^"]*美宜佳[^"]*")(>)',
        r'\1 id="r52-vid" onended="document.getElementById(\'r52-mask\').style.opacity=1"\2',
        html,
    )
    # Find the mask div (-14, -26, 1948x1132) — that's the text overlay
    # Looking at slide-073 dump: the div at (-14, -26, 1948×1132) is the text
    # container. Give it an id + initial opacity:0 + transition.
    html = re.sub(
        r'(<div class="el[^"]*"\s+style="left:-14\.0px;top:-26\.0px;width:1948\.0px;'
        r'min-height:1132\.0px;)',
        r'<div id="r52-mask" class="el" '
        r'style="opacity:0;transition:opacity 0.6s ease-out;left:-14.0px;top:-26.0px;'
        r'width:1948.0px;min-height:1132.0px;',
        html,
    )
    return html
print("#10 slide-073 (page 52) video onended → mask appears, no loop")
edit_html("slide-073", fix10)


# ── #7 · slide-012 (page 7): 邮政储蓄银行 logo + vertical dividers ────────
# (a) 邮政储蓄银行 — without a visual I can't pinpoint by filename, but
#     it's typically a horizontal logo with "邮政储蓄银行" text in red. Often
#     image2-24575.png (1691, 321, 169×27) based on position. Shift right.
# (c) vertical dividers between industry columns.
def fix7(html):
    # Vertical dividers at x = 555, 827, 1099, 1375, 1652 (per earlier survey).
    # Each: 1px wide, light silvery gray, from y=275 to y=1000.
    dividers = "\n".join(
        f'<div class="el" style="left:{x}px;top:275px;width:1px;height:725px;'
        f'background:rgba(192,196,210,0.22);pointer-events:none;z-index:1;"></div>'
        for x in (555, 827, 1099, 1375, 1652)
    )
    # Insert dividers right before the first existing element (or right after </style>).
    style_end = html.find("</style>") + len("</style>")
    html = html[:style_end] + "\n" + dividers + html[style_end:]
    # 邮政储蓄银行 logo (image2-24575.png) — shift right by ~30px.
    html = re.sub(
        r'(<img class="el" src="assets/slide-012/image2-24575\.png" style="left:)1691\.0px',
        r"\g<1>1721.0px",
        html,
    )
    return html
print("#7 slide-012 vertical column dividers + 邮政储蓄银行 shift")
edit_html("slide-012", fix7)


# ── #7d · slide-012 (page 7) logo aspect fixes ──────────────────────────
# Three logos in the brand grid were being object-fit:cover-cropped to
# their middle band because the rendered bbox aspect didn't match the
# source file aspect:
#   · FOTILE 方太 (jpeg 517×232, displayed 193×31) → 179% mismatch
#   · 中国邮政储蓄银行 (png 624×53, displayed 206×42) → 58% mismatch
# For those two we switch to object-fit:contain so the full logo shows.
#   · Schneider (image8-25327.png) ships as Schneider+Midea bundled →
#     swap src to the pre-cropped image8-25327-schneider-only.png that
#     sits next to it.
def fix7d(html):
    html = html.replace(
        'src="assets/slide-012/478d0db1e3ecb40528d262a210911f6b-25334.jpeg" '
        'style="left:280.0px;top:918.0px;width:193.0px;height:31.0px;object-fit:cover;"',
        'src="assets/slide-012/478d0db1e3ecb40528d262a210911f6b-25334.jpeg" '
        'style="left:280.0px;top:918.0px;width:193.0px;height:31.0px;object-fit:contain;"',
    )
    html = html.replace(
        'src="assets/slide-012/已粘贴的影片-24567.png" '
        'style="left:868.0px;top:576.0px;width:206.0px;height:42.0px;object-fit:cover;"',
        'src="assets/slide-012/已粘贴的影片-24567.png" '
        'style="left:868.0px;top:576.0px;width:206.0px;height:42.0px;object-fit:contain;"',
    )
    html = html.replace(
        'src="assets/slide-012/image8-25327.png"',
        'src="assets/slide-012/image8-25327-schneider-only.png"',
    )
    return html
print("#7d slide-012 FOTILE + 邮政储蓄 contain + Schneider-only swap")
edit_html("slide-012", fix7d)


# ── #11 · slide-017 (page 11): user-curated curve background ────────────
def fix11(html):
    return html.replace(
        "assets/_shared/image-2-1-9202.png",
        "assets/slide-017/curve-bg.png",
        1,  # only the first (full-canvas bg) ref
    )
print("#11 slide-017 (page 11) bg → curve-bg.png")
edit_html("slide-017", fix11)


# ── #12 · slide-050 (page 31): user-curated drone background ────────────
def fix12(html):
    return html.replace(
        "assets/_shared/image-2-1-9202.png",
        "assets/slide-031/drone-bg.png",
        1,
    )
print("#12 slide-050 (page 31) bg → drone-bg.png")
edit_html("slide-050", fix12)


# ── Write back ───────────────────────────────────────────────────────────
DECK.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n==> deck.json updated ({DECK})")
