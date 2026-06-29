# 生成照片墙模板线框 SVG(精确几何)
PAD=6; GAP=3            # 帧内边距 / 格间距
FW=212; FH=119         # 单个 16:9 缩略帧尺寸(画布缩小版)

def cell(x,y,w,h,hero=False):
    fill="var(--accent-9,#3b82f6)" if hero else "var(--bg-tile,#d4d9e0)"
    op="0.85" if hero else "1"
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="{fill}" fill-opacity="{op}"/>'

def grid(ox,oy,cols,rows):
    """均匀 cols×rows 平铺,返回格子 rect 列表"""
    iw=FW-2*PAD; ih=FH-2*PAD
    cw=(iw-(cols-1)*GAP)/cols; ch=(ih-(rows-1)*GAP)/rows
    out=[]
    for r in range(rows):
        for c in range(cols):
            x=ox+PAD+c*(cw+GAP); y=oy+PAD+r*(ch+GAP)
            out.append(cell(x,y,cw,ch))
    return out

def hero_right(ox,oy,n_small):
    """左 hero 大图(占左 62%)+ 右侧竖排 n_small 张"""
    iw=FW-2*PAD; ih=FH-2*PAD
    hero_w=iw*0.62; right_w=iw-hero_w-GAP
    out=[cell(ox+PAD,oy+PAD,hero_w,ih,hero=True)]
    ch=(ih-(n_small-1)*GAP)/n_small
    for i in range(n_small):
        y=oy+PAD+i*(ch+GAP)
        out.append(cell(ox+PAD+hero_w+GAP,y,right_w,ch))
    return out

def hero_corner(ox,oy):
    """6张:左上 hero 2x2 + 右列2 + 底行3 (基于 3x3)"""
    iw=FW-2*PAD; ih=FH-2*PAD
    cw=(iw-2*GAP)/3; ch=(ih-2*GAP)/3
    def gx(c): return ox+PAD+c*(cw+GAP)
    def gy(r): return oy+PAD+r*(ch+GAP)
    out=[cell(gx(0),gy(0),cw*2+GAP,ch*2+GAP,hero=True)]   # hero 2x2
    out+=[cell(gx(2),gy(0),cw,ch), cell(gx(2),gy(1),cw,ch)]   # 右列2
    out+=[cell(gx(0),gy(2),cw,ch), cell(gx(1),gy(2),cw,ch), cell(gx(2),gy(2),cw,ch)]  # 底行3
    return out

# 模板定义:(标题, 副标题, 生成函数)
TPLS=[
 ("4 张 · 田字", "2×2 均等", lambda ox,oy: grid(ox,oy,2,2)),
 ("4 张 · hero+3", "1 大 + 3 竖排", lambda ox,oy: hero_right(ox,oy,3)),
 ("6 张 · 平铺", "3×2 均等", lambda ox,oy: grid(ox,oy,3,2)),
 ("6 张 · hero", "1 大 + 5 围", lambda ox,oy: hero_corner(ox,oy)),
 ("8 张 · 平铺", "4×2 均等", lambda ox,oy: grid(ox,oy,4,2)),
 ("9 张 · 平铺", "3×3 均等", lambda ox,oy: grid(ox,oy,3,3)),
 ("12 张 · 平铺", "4×3 均等", lambda ox,oy: grid(ox,oy,4,3)),
]

# 布局:每行 4 个卡片
CW=250; CH=180; COLS=4; MX=20; MY=20
rows=(len(TPLS)+COLS-1)//COLS
W=MX*2+COLS*CW; H=MY+rows*CH+20
svg=[f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,system-ui,sans-serif" role="img">']
svg.append('<title>照片墙模板候选</title>')
for i,(title,sub,fn) in enumerate(TPLS):
    r=i//COLS; c=i%COLS
    ox=MX+c*CW; oy=MY+r*CH
    fx=ox+(CW-FW)/2; fy=oy+24
    # 帧外框
    svg.append(f'<rect x="{fx:.1f}" y="{fy:.1f}" width="{FW}" height="{FH}" rx="6" fill="var(--bg-frame,#11151c)"/>')
    svg+=fn(fx,fy)
    svg.append(f'<text x="{ox+CW/2:.1f}" y="{oy+16:.1f}" text-anchor="middle" font-size="15" font-weight="600" fill="var(--text-1,#1a1a1a)">{title}</text>')
    svg.append(f'<text x="{ox+CW/2:.1f}" y="{fy+FH+18:.1f}" text-anchor="middle" font-size="12" fill="var(--text-2,#6b7280)">{sub}</text>')
svg.append('</svg>')
print("\n".join(svg))
