#!/usr/bin/env python3
"""rebuild_slides.py — re-render specific slides in a production deck.

Replaces deck.json[*].data.html + the corresponding slide block in
index.html for ONLY the requested pages. Other slides are left alone.

Usage:
    python3 rebuild_slides.py \
        <output_dir> <extract.tsv> <key_bundle> <page_no> [<page_no> ...]

Example:
    python3 plugin/skills/keynote-to-html/assets/rebuild_slides.py \
        imports/AI案例分享/render-output-full \
        /tmp/chunks/merged.tsv \
        "/path/to/file.key" \
        19 20 22 63

Why this exists:
    `build.py` always rebuilds the WHOLE deck from extract.tsv. When the
    user has done hand-edits in deck.json (titles, removed elements,
    custom styling), running build.py wipes them. This script lets us
    re-render JUST the pages affected by an iwa_resolver / build.py
    code change without touching the rest of the deck.
"""
from __future__ import annotations
import sys, json, re, zipfile, tempfile, atexit, shutil
from pathlib import Path

if len(sys.argv) < 5:
    print(__doc__, file=sys.stderr)
    sys.exit(2)

OUTPUT_DIR = Path(sys.argv[1]).resolve()
TSV_PATH   = Path(sys.argv[2]).resolve()
KEY_PATH   = Path(sys.argv[3]).resolve()
PAGES = [int(x) for x in sys.argv[4:]]
SLIDE_KEYS = {f"slide-{p:03d}" for p in PAGES}

# Import the build pipeline's per-slide functions.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B
from iwa_resolver import IWAAssetMap

print(f"==> rebuilding {len(PAGES)} slides ({sorted(PAGES)}) in {OUTPUT_DIR}")

_, slides, _, _ = B.parse_tsv(TSV_PATH)
iwa = IWAAssetMap.from_key(KEY_PATH)

# Stage Data/ from the .key zip so AssetResolver can find files. Use a
# temp dir; build.py does the same when invoked normally.
# IMPORTANT: Keynote stores UTF-8 filenames in the zip WITHOUT setting the
# UTF-8 flag bit (0x800). Python's zipfile defaults to CP437 decode for
# those, producing mojibake for Chinese names. Recode if needed —
# otherwise `_by_name` will be keyed by mojibake and IWA's clean Chinese
# filenames won't match, and every image with Chinese chars will render
# as a "missing image" placeholder.
import shutil as _shutil
with zipfile.ZipFile(KEY_PATH) as z:
    data_dir = Path(tempfile.mkdtemp(prefix="kn-data-"))
    # Each .key Data/ extract is ~1.2 GB for this deck. If we crash or get
    # killed before cleanup, the temp dir leaks. Register cleanup so repeat
    # rebuilds don't fill /tmp (which we did, more than once).
    atexit.register(lambda: shutil.rmtree(data_dir, ignore_errors=True))
    for info in z.infolist():
        raw_name = info.filename
        if not (info.flag_bits & 0x800):
            try:
                raw_name = raw_name.encode("cp437").decode("utf-8")
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
        if info.is_dir() or not raw_name.startswith("Data/"):
            continue
        name = Path(raw_name).name
        if not name or name.startswith("."):
            continue
        target = data_dir / name
        with z.open(info) as src, open(target, "wb") as dst:
            _shutil.copyfileobj(src, dst)

resolver = B.AssetResolver(data_dir, OUTPUT_DIR / "assets", iwa_map=iwa)
raster   = B.RasterFallback(None, None, [s.keynote_no for s in slides])

deck = json.loads((OUTPUT_DIR/"deck.json").read_text(encoding="utf-8"))
by_key = {s["key"]: s for s in deck["slides"]}

patched: list[str] = []
for sl in slides:
    key = f"slide-{sl.keynote_no:03d}"
    if key not in SLIDE_KEYS:
        continue
    if key not in by_key:
        print(f"  WARN: {key} not in deck.json — skip")
        continue
    slide_assets_subdir = f"assets/{key}"
    slide_assets_dir = OUTPUT_DIR / "assets" / key
    new_html, warns = B.compose_slide_html(
        sl, resolver, raster, slide_assets_subdir, slide_assets_dir
    )
    # Ensure the per-slide CSS keeps `isolation: isolate` so z-index
    # doesn't escape across slides (matches the full build.py output).
    new_html = re.sub(
        r"(\.slide\[data-slide-key='slide-\d+'\] \{ background: [^}]+overflow: hidden;)( \})",
        lambda m: (m.group(1) + " isolation: isolate;" + m.group(2))
                  if "isolation:" not in m.group(0) else m.group(0),
        new_html, count=1,
    )
    by_key[key]["data"]["html"] = new_html
    patched.append(key)
    if warns:
        for w in warns:
            print(f"    {w}")

# Save deck.json.
(OUTPUT_DIR/"deck.json").write_text(
    json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

# Splice into index.html — for each patched slide, replace the content
# of its `<div class="slide" ... data-slide-key="slide-NNN">…</div>`
# block by walking matching div-depth.
html = (OUTPUT_DIR/"index.html").read_text(encoding="utf-8")
opener = re.compile(
    r'(<div\s+class="slide"\s+data-layout="raw"\s*'
    r'data-screen-label="(?P<label>[^"]+)"\s+'
    r'data-slide-key="(?P<key>slide-\d+)">)',
    re.IGNORECASE,
)
o_open  = re.compile(r'<div\b', re.IGNORECASE)
o_close = re.compile(r'</div\s*>', re.IGNORECASE)

def splice(text: str, slide_key: str, new_inner: str) -> str:
    for m in opener.finditer(text):
        if m.group("key") != slide_key:
            continue
        s = m.end(); depth, i = 1, s
        while i < len(text) and depth > 0:
            no, nc = o_open.search(text, i), o_close.search(text, i)
            if no and no.start() < nc.start():
                depth += 1; i = no.end()
            else:
                depth -= 1
                if depth == 0:
                    return text[:s] + "\n" + new_inner + "\n" + text[nc.start():]
                i = nc.end()
    raise KeyError(f"slide {slide_key} not found in index.html")

for key in patched:
    html = splice(html, key, by_key[key]["data"]["html"])

(OUTPUT_DIR/"index.html").write_text(html, encoding="utf-8")
print(f"==> done. {len(patched)} slide(s) rebuilt & spliced into deck.")
