#!/usr/bin/env python3
"""
keynote-to-html · build.py  (v0.16)

Reads the TSV emitted by extract.applescript, resolves image references against
the .key bundle's Data/ directory, composes positioned HTML for each slide,
writes a feishu-deck-h5 deck.json, and invokes feishu's render-deck.py.

v0.16 changes:
  · `--redesigns DIR` flag: per-slide HTML overrides. When `DIR/slide-NN.html`
    exists (NN = 1-based PDF page), its contents replace the auto-extracted
    slide body entirely. Use this for layouts that don't map cleanly from
    Keynote — heavy tables, custom card grids, dashboards. Each override is
    partial HTML (a `<style>` block + body elements) embedded inside the
    raw-layout slide. Auto-extraction still runs for non-overridden slides;
    redesigned slides are exempt from element extraction, placeholder
    suppression, raster fallback, etc. Demonstrated on the Kangshifu deck:
    slides 24 (6-card grid), 26 (case + dual phone videos), 27 (2-col
    dashboard), 40 (case + phone screenshots).
  · Render "container shapes" (no fill / no text shape that visually CONTAINS
    other elements — typical pattern: a banner/pill/card background with a
    group of children inside). Previously skipped because AppleScript couldn't
    extract the gradient/theme fill color. Now render as a default semi-
    transparent rounded box so the layout shape is preserved. Affected pages:
    26 (pink "成功案例" banner), and any other deck using gradient-filled
    card backgrounds.
  · Render `other:line` elements (Keynote dividers) with h=0 or w=0 as a
    2-pixel hairline div with semi-transparent white. Previously these
    disappeared entirely because the raster fallback's crop region was
    invalid for zero-height regions. Affected pages: 24 (6 card-title
    underlines), 12, 30, 42.

v0.15 changes (paired with extract.applescript v0.15):
  · FIXED group child positioning. Empirically verified that Keynote 14.5
    AppleScript returns child positions as ABSOLUTE slide coordinates,
    NOT relative to the group's top-left. Our v0.2 group recursion was
    adding the group's position as an offset, double-counting it and
    pushing grouped elements OFF the slide canvas (typically y > 1080).
    Affected slide 40 (5 bullet shapes + 5 icons all rendered at y=1084+
    instead of y=542+). Fix: pass (0, 0) as offset when recursing into
    group children. Re-extract required for this fix to take effect.

v0.14 changes:
  · Image resolver now PREFERS candidates with the same file extension
    as AppleScript reported. Previously, the resolver collected all
    candidates with matching stem regardless of extension, then picked by
    aspect ratio. This caused slide 37's `已粘贴的图像.tiff` to match a
    `.png` file whose aspect ratio coincidentally matched the bbox
    (a landscape robot image) instead of the actual `.tiff` (pink-gradient
    bg). Now we filter to same-extension candidates first.

v0.13 changes:
  · `fit_font_to_box` is now an identity passthrough (per user direction):
    always honor the authored Keynote font size; never auto-shrink.
  · Per-element CSS opacity now has `!important` so it survives feishu's
    `.deck:not([data-nav-armed]) .slide-frame:first-child .slide > * {
    opacity: 1 !important }` rule (which targeted the first slide pre-
    navigation but silently overrode our inline opacity).
  · Slide-bg heuristic now ignores MASTER elements when scanning for
    "dark text". Master placeholder shapes use theme-default black even on
    dark slides; including them caused slide 34 to be flagged as needing a
    white bg (which then made our 50%-opacity image appear LIGHTER, not
    darker, when blended over the wrong bg color).

v0.12 changes:
  · `fit_font_to_box()` char-width heuristic was too conservative:
    CJK was 1.00em (actual PingFang/Noto/Alibaba ≈ 0.95em); ASCII was
    0.55em (actual mixed-case ≈ 0.50em); height threshold was 1.05x.
    This caused spurious 1-line text to be counted as 2-line and shrunk
    aggressively (slide 21's "做是做了AI…" at 55 pt was being shrunk to
    30 pt). Revised to 0.95em/0.50em + 15% container buffer + 1.20x
    height threshold — only shrink on unmistakable overflow.

v0.11 changes:
  · Suppress Keynote master placeholder text/shape elements (matches
    "幻灯片标题" / "正文级别 1\n正文级别 2 …" / "Subtitle" / "Click to add"
    etc. — these are template placeholders Keynote shows in the editor but
    NEVER renders on the slide. AppleScript was returning them as if real
    content, causing junk text on every slide using a templated layout.
  · Element rotation now emits `transform: rotate(Xdeg) !important` so it
    survives our anti-flash `.slide > * { transform: none !important }`
    override. Was killing the 180° rotation on page 28's bg image.
  · Text alignment heuristic: bbox center within ±80 px of slide center
    → `text-align: center`. AppleScript's `alignment` property is not
    accessible from Keynote's automation interface; this position-based
    inference catches the common authoring patterns where users place
    centered text by aligning the bbox horizontally.
  · Master-image suppression threshold relaxed: was `> SLIDE * 0.98`
    (catching exact-canvas-size images); now `> SLIDE * 1.02` so a true
    1920×1080 master backdrop is kept (it's content, not overflow).

v0.10 changes:
  · CRITICAL FIX: feishu-deck-h5's "stagger reveal" CSS animation forces
    `opacity: 1` on every direct child of `.slide` via `animation: fs-reveal`.
    This silently overrode all our inline opacity values — authored 22% / 30%
    semi-transparent backgrounds were rendering at 100%, making slides look
    ~3-4x brighter than Keynote. Override the animation in our per-slide
    inline <style> so inline opacity is honored.
  · `Element.css_opacity` is now an identity mapping (was an unnecessary
    gamma-1.8 correction added when I thought CSS opacity blended too bright;
    the real problem was the animation override).

v0.9 changes:
  · Master items now emitted with "MASTER" record type (vs "ITEM"); build.py
    sets `Element.is_master = True` on them.
  · Master-image suppression: when a master image is oversized (wider/taller
    than the 1920×1080 canvas) OR when the slide itself has a full-bleed
    image (treated as the new background), the master's background-like
    images are dropped. Matches Keynote's PDF-export behavior where the
    master background placeholder is hidden by the slide's own bg. Fixes the
    "page 2 background appears brighter than Keynote" bug where the master's
    green-textured up@2x.png was shining through a 22%-opacity ganyifan.

v0.8 changes:
  · Approximate Keynote's "shrink text to fit" via `fit_font_to_box()`:
    estimates whether authored font size would overflow the element's
    bounding box (CJK chars ≈ 1em, ASCII ≈ 0.55em) and scales down. Was
    needed because AppleScript reports the AUTHORED size, but Keynote
    visually shrinks text when auto-fit is on (slides 8 / 9 in the
    Kangshifu deck had 85–100pt authored but displayed at ~50–70pt).

v0.7 changes:
  · Extract master / base-layout items per slide (template backgrounds,
    branded chrome, footer images). They render BENEATH the slide's own
    items, matching Keynote draw order. Previously only the slide's own
    items were captured, so any background that lived on the master was
    missing — typical losses included the "right-half template panel" on
    bio slides and any subtle texture layer.

v0.6 changes:
  · Opacity extracted from every Keynote item (0–100) and emitted as
    CSS `opacity:` for images / videos / text. Translucent overlay shapes
    (semi-transparent black or white masks) render as `rgba()` backgrounds
    with alpha baked in.
  · "No fill" vs "black fill" disambiguated via a sentinel (-1) on fill_r.
    Previously a true black fill (0,0,0) was indistinguishable from
    "fill not extractable" — they're now distinct.
  · Corner-radius heuristic suppressed for translucent overlays (they're
    usually full-bleed masks, not rounded cards).

v0.5 changes:
  · CRITICAL BUG FIX: font-family stack now uses SINGLE quotes around
    multi-word family names. v0.4 used double quotes inside double-quoted
    style attributes — browsers truncated the style attribute at the first
    inner double quote, silently discarding font-weight / font-size /
    everything past font-family. This is why v0.4's font-weight changes
    "didn't work".
  · AppleScript extract now respects --limit — extracts only first N
    non-skipped slides instead of walking the whole document. Fast.

v0.4 changes:
  · Font-weight parsing from Keynote font name suffix (e.g. -Bold, -Black,
    -Light, -Medium, _SC_Black) → emits CSS `font-weight:` (100–900).
    Big visual impact: previously every font rendered at the web fallback's
    default weight (usually 400), losing bold headings and thin body text.
  · Font-style parsing: -Italic / -Oblique → CSS `font-style: italic`.
  · Removed wordmark <div> from feishu raw.fragment.html — the wordmark CSS
    rule painted a 飞书 logo top-right of every slide via background-image,
    even though we had set the div empty. (Edit lives in feishu-deck-h5
    template, since raw layout is shared.)

v0.3 changes:
  · Detect shape+image pairs occupying the same bbox; render the whole pair
    as a single raster crop (recovers Keynote "stylized image placeholder"
    visuals where the shape's fill is gradient/theme — not extractable via
    AppleScript).
  · Skip empty shapes (no fill, no text) that overlap with other elements —
    these are invisible authoring placeholders. Stops "weird crop" artifacts.
  · Slide background heuristic: when AppleScript can't extract a master's
    bg color (gradient/image fills don't expose), infer white vs dark from
    the dominant text color on the slide.
  · object-fit: cover for raster images (was contain — left letterboxing).

v0.2 changes:
  · Renders shapes with fill color (and best-effort border-radius via heuristic).
  · Applies per-element rotation via CSS transform.
  · Uses per-slide background color from #SLIDE-META.
  · PNG raster fallback for unhandled elements (when --rasters-dir provided).
  · Better image matching: filter candidates by minimum size, then aspect.
  · Skips group container records (children already flattened by AppleScript).

Usage:
  python3 build.py <extract.tsv> <key-bundle-path> <output-dir> \
      [--limit N] [--renderer PATH] [--rasters-dir DIR] [--pdf PATH]

If neither --rasters-dir nor --pdf is given, no raster fallback is applied
(unhandled elements render as labeled placeholders so they're visible).
"""
from __future__ import annotations

import argparse
import base64
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("ERROR: PyMuPDF not installed. Run: pip3 install PyMuPDF")

try:
    from PIL import Image
except ImportError:
    sys.exit("ERROR: Pillow not installed. Run: pip3 install Pillow")

# Local module: IWA-based deterministic asset resolution (see iwa_resolver.py).
# Optional — if keynote-parser isn't installed, we fall back to the heuristic
# AssetResolver alone.
try:
    from iwa_resolver import IWAAssetMap
    _IWA_AVAILABLE = True
except Exception:
    IWAAssetMap = None  # type: ignore
    _IWA_AVAILABLE = False


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------

@dataclass
class Element:
    type: str          # image / text / movie / shape / table / chart / group / other:*
    x: float
    y: float
    w: float
    h: float
    rotation: float = 0
    file_name: str = ""
    font: str = ""
    font_size: float = 0
    r: int = 0
    g: int = 0
    b: int = 0
    fill_r: int = 0
    fill_g: int = 0
    fill_b: int = 0
    corner_radius: float = 0
    opacity: float = 100  # 0–100 (Keynote convention)
    is_master: bool = False  # True if extracted from the slide's base layout (master)
    text: str = ""
    # Per-run styling (only populated when extract emitted RUN records — i.e.
    # text has non-uniform fonts/sizes/colors). Each run is a dict:
    # {"text": str, "font": str, "size": float, "r": int, "g": int, "b": int}
    runs: list = field(default_factory=list)
    # v2 deck.json: the element that pick_title selects gets data_role="title".
    # All text-div emission sites in compose_slide_html honor this and render
    # `data-role="title"` so downstream skills can find / replace the title
    # element. See plugin/_spec/deck-json-v2.md §"raw layout title 同步规则".
    data_role: str = ""
    # For type=="table" only: list of cell dicts in row-major order.
    # Each cell: {"row": int, "col": int, "w": float, "h": float, "text": str}
    cells: list = field(default_factory=list)
    # For type=="chart" only: extracted chart data.
    # {"type": str, "series": [str], "categories": [str],
    #  "points": [[float, ...]]}  -- points[series_idx][category_idx]
    chart: dict = field(default_factory=dict)

    @property
    def text_color_hex(self) -> str:
        return _kn_rgb_to_hex(self.r, self.g, self.b)

    @property
    def fill_color_hex(self) -> str:
        # Treat sentinel (-1) as no fill — emit transparent for safety
        if self.fill_r < 0:
            return "transparent"
        return _kn_rgb_to_hex(self.fill_r, self.fill_g, self.fill_b)

    @property
    def fill_color_rgba(self) -> str:
        """Returns rgba() with alpha from gamma-corrected opacity. transparent if no fill."""
        if self.fill_r < 0:
            return "transparent"
        a = self.css_opacity
        return f"rgba({int(self.fill_r * 255 / 65535)},{int(self.fill_g * 255 / 65535)},{int(self.fill_b * 255 / 65535)},{a:.3f})"

    @property
    def has_fill(self) -> bool:
        return self.fill_r >= 0

    @property
    def is_translucent(self) -> bool:
        return self.opacity < 99.5

    @property
    def css_opacity(self) -> float:
        """Opacity for CSS. Identity mapping (authored opacity / 100) once
        feishu's stagger-reveal animation is disabled (see compose_slide_html
        for the override). Pixel-measured against Keynote PDF export and the
        identity is a close match — no gamma correction needed."""
        if self.opacity >= 99.5:
            return 1.0
        return max(0.0, min(1.0, self.opacity / 100.0))


def _kn_rgb_to_hex(r: int, g: int, b: int) -> str:
    """Keynote color (0–65535 per channel) → #RRGGBB."""
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(r * 255 / 65535))) if r else 0,
        max(0, min(255, int(g * 255 / 65535))) if g else 0,
        max(0, min(255, int(b * 255 / 65535))) if b else 0,
    )


@dataclass
class Slide:
    keynote_no: int
    skipped: bool
    bg_r: int = 0
    bg_g: int = 0
    bg_b: int = 0
    elements: list[Element] = field(default_factory=list)

    @property
    def bg_hex(self) -> str:
        return _kn_rgb_to_hex(self.bg_r, self.bg_g, self.bg_b)

    @property
    def has_bg_color(self) -> bool:
        return (self.bg_r + self.bg_g + self.bg_b) > 0


# ----------------------------------------------------------------------------
# TSV parsing
# ----------------------------------------------------------------------------

def parse_tsv(tsv_path: Path) -> tuple[int, list[Slide], float, float]:
    total = 0
    slides: list[Slide] = []
    current: Optional[Slide] = None
    # Source canvas size from the .key. Defaults to 1920×1080; updated when
    # we see a #DOC-SIZE header. After parsing we scale every element so the
    # renderer (which always lays out a 1920×1080 canvas) sees the deck at
    # the right baseline.
    src_w, src_h = 1920.0, 1080.0

    for line in tsv_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        head = parts[0]

        if head == "#TOTAL":
            total = int(parts[1])
        elif head == "#DOC-SIZE":
            try:
                src_w = float(parts[1])
                src_h = float(parts[2])
            except (IndexError, ValueError):
                pass
        elif head == "#SLIDE":
            current = Slide(keynote_no=int(parts[1]), skipped=(parts[2] == "true"))
            slides.append(current)
        elif head == "#SLIDE-META" and current is not None:
            try:
                current.bg_r = int(float(parts[1] or 0))
                current.bg_g = int(float(parts[2] or 0))
                current.bg_b = int(float(parts[3] or 0))
            except (IndexError, ValueError):
                pass
        elif head == "#END-SLIDE" and current is not None:
            # Dedupe pass. Keynote 15 surfaces some elements multiple times:
            #   (a) master items appear in both `base layout` and the slide's
            #       own `iWork items` (→ MASTER + ITEM records)
            #   (b) the same master item appears twice in `base layout` (→
            #       MASTER + MASTER records, identical bbox + filename)
            # Collapse by (type, file_name, rounded bbox). Keep the FIRST
            # occurrence; prefer MASTER over ITEM when both exist so master-
            # suppression logic still gets a chance to evaluate it.
            seen: set[tuple[str, str, int, int, int, int]] = set()
            # First pass: collect master keys so we can drop ITEM duplicates
            # of them.
            master_keys = {
                (el.type, el.file_name, int(el.x), int(el.y),
                 int(el.w), int(el.h))
                for el in current.elements
                if el.is_master and el.file_name
            }
            deduped = []
            for el in current.elements:
                key = (el.type, el.file_name,
                       int(el.x), int(el.y), int(el.w), int(el.h))
                # Skip an ITEM that duplicates a MASTER record (or vice versa)
                if (not el.is_master) and el.file_name and key in master_keys:
                    continue
                # Skip exact duplicates (same is_master, same key)
                tag = (("M" if el.is_master else "I"),) + key
                if tag in seen:
                    continue
                seen.add(tag)
                deduped.append(el)
            current.elements = deduped
            current = None
        elif head == "#DONE":
            break
        elif head in ("ITEM", "MASTER") and current is not None:
            # ITEM \t type \t x \t y \t w \t h \t rotation \t file_name \t font \t
            # font_size \t r \t g \t b \t fill_r \t fill_g \t fill_b \t corner \t opacity \t text_b64
            try:
                el = Element(
                    type=parts[1],
                    x=float(parts[2]),
                    y=float(parts[3]),
                    w=float(parts[4]),
                    h=float(parts[5]),
                    rotation=float(parts[6] or 0),
                    file_name=parts[7],
                    font=parts[8],
                    font_size=float(parts[9] or 0),
                    r=int(float(parts[10] or 0)),
                    g=int(float(parts[11] or 0)),
                    b=int(float(parts[12] or 0)),
                    fill_r=int(float(parts[13] or 0)),
                    fill_g=int(float(parts[14] or 0)),
                    fill_b=int(float(parts[15] or 0)),
                    corner_radius=float(parts[16] or 0),
                    opacity=float(parts[17] or 100),
                    is_master=(head == "MASTER"),
                    text=base64.b64decode(parts[18]).decode("utf-8") if len(parts) > 18 and parts[18] else "",
                )
                # Skip "group" container records — their children were already flattened.
                if el.type == "group":
                    continue
                current.elements.append(el)
            except (IndexError, ValueError) as e:
                print(f"  warning: bad ITEM line: {e!r} — {line[:120]}", file=sys.stderr)

        elif head == "CELL" and current is not None and current.elements:
            # CELL \t row \t col \t cw \t rh \t font \t size \t r \t g \t b \t
            #      \t fill_r \t fill_g \t fill_b \t text_b64
            # Attaches to the most recently appended element (the table).
            try:
                last = current.elements[-1]
                if last.type != "table":
                    continue
                # Backwards-compat: older extracts had only 6 fields (row,
                # col, cw, rh, text_b64) — handle both.
                # Two TSV formats coexist:
                #   legacy short:  6 fields  (CELL, row, col, cw, rh, text_b64)
                #   current full: 14 fields  (CELL, row, col, cw, rh, font, size,
                #                              r, g, b, fill_r, fill_g, fill_b,
                #                              text_b64)
                # Detect by length and dispatch.
                if len(parts) == 6:
                    cell_text = (base64.b64decode(parts[5]).decode("utf-8")
                                 if parts[5] else "")
                    last.cells.append({
                        "row":  int(parts[1]),
                        "col":  int(parts[2]),
                        "w":    float(parts[3] or 0),
                        "h":    float(parts[4] or 0),
                        "text": cell_text,
                    })
                elif len(parts) >= 14:
                    cell_text = (base64.b64decode(parts[13]).decode("utf-8")
                                 if parts[13] else "")
                    last.cells.append({
                        "row":     int(parts[1]),
                        "col":     int(parts[2]),
                        "w":       float(parts[3] or 0),
                        "h":       float(parts[4] or 0),
                        "font":    parts[5],
                        "size":    float(parts[6] or 0),
                        "r":       int(float(parts[7] or 0)),
                        "g":       int(float(parts[8] or 0)),
                        "b":       int(float(parts[9] or 0)),
                        "fill_r":  int(float(parts[10] or -1)),
                        "fill_g":  int(float(parts[11] or -1)),
                        "fill_b":  int(float(parts[12] or -1)),
                        "text":    cell_text,
                    })
            except (IndexError, ValueError) as e:
                print(f"  warning: bad CELL line: {e!r} — {line[:120]}", file=sys.stderr)

        elif head in ("CHART_META", "SERIES", "CATEGORY", "POINT") and \
                current is not None and current.elements:
            try:
                last = current.elements[-1]
                if last.type != "chart":
                    continue
                ch = last.chart
                if not ch:
                    last.chart = ch = {"type": "", "series": [], "categories": [], "points": []}
                if head == "CHART_META":
                    ch["type"] = parts[1] if len(parts) > 1 else ""
                elif head == "SERIES":
                    name = (base64.b64decode(parts[1]).decode("utf-8")
                            if len(parts) > 1 and parts[1] else "")
                    ch["series"].append(name)
                    ch["points"].append([])
                elif head == "CATEGORY":
                    label = (base64.b64decode(parts[1]).decode("utf-8")
                             if len(parts) > 1 and parts[1] else "")
                    ch["categories"].append(label)
                elif head == "POINT":
                    si = int(parts[1])
                    ci = int(parts[2])
                    v = float(parts[3] or 0)
                    while len(ch["points"]) <= si:
                        ch["points"].append([])
                    while len(ch["points"][si]) <= ci:
                        ch["points"][si].append(0.0)
                    ch["points"][si][ci] = v
            except (IndexError, ValueError) as e:
                print(f"  warning: bad {head} line: {e!r} — {line[:120]}",
                      file=sys.stderr)

        elif head == "RUN" and current is not None and current.elements:
            # RUN \t font \t size \t r \t g \t b \t text_b64
            # Attaches to the most recently appended element.
            try:
                last = current.elements[-1]
                run_text = base64.b64decode(parts[6]).decode("utf-8") if len(parts) > 6 and parts[6] else ""
                last.runs.append({
                    "text": run_text,
                    "font": parts[1],
                    "size": float(parts[2] or 0),
                    "r":    int(float(parts[3] or 0)),
                    "g":    int(float(parts[4] or 0)),
                    "b":    int(float(parts[5] or 0)),
                })
            except (IndexError, ValueError) as e:
                print(f"  warning: bad RUN line: {e!r} — {line[:120]}", file=sys.stderr)

    # Normalise coordinates: the renderer's CSS assumes a 1920×1080 canvas.
    # If the source .key uses a smaller (e.g. 960×540) canvas, every element
    # comes in at coords that only fill the top-left quarter. Scale once
    # right here so all downstream code can stay canvas-agnostic.
    if abs(src_w - 1920.0) > 0.5 or abs(src_h - 1080.0) > 0.5:
        sx = 1920.0 / src_w
        sy = 1080.0 / src_h
        # Uniform scale: the .key's aspect should match 1920×1080. If it
        # doesn't we still go with sx (the renderer's 16:9 frame won't
        # change shape regardless).
        s_font = sx
        print(f"  scaling canvas {src_w:.0f}×{src_h:.0f} → 1920×1080 "
              f"(sx={sx:.3f}, sy={sy:.3f})", file=sys.stderr)
        for sl in slides:
            for el in sl.elements:
                el.x *= sx; el.y *= sy
                el.w *= sx; el.h *= sy
                if el.font_size:
                    el.font_size *= s_font
                for run in getattr(el, "runs", []) or []:
                    if "size" in run and run["size"]:
                        run["size"] = float(run["size"]) * s_font

    return total, slides, src_w, src_h


# ----------------------------------------------------------------------------
# Image matching against .key/Data/
# ----------------------------------------------------------------------------

class AssetResolver:
    """Resolves Element.file_name → actual file under .key/Data/.

    Strategy (v0.2):
      1. Strip "-NNNN" / "-small-NNNN" suffix from Data/ filenames, compare to
         AppleScript-reported stem (which lacks the suffix).
      2. If exactly one non-"small" candidate matches the stem, use it.
      3. Multiple candidates → filter to those whose intrinsic size is at
         least 0.5× the displayed size (rejects tiny thumbnails). Among the
         remaining, score by aspect-ratio match (size as tiebreaker).
    """

    def __init__(self, data_dir: Path, out_assets_dir: Path,
                 iwa_map: "Optional[IWAAssetMap]" = None):
        self.data_dir = data_dir
        self.out_assets_dir = out_assets_dir
        self.cache: dict[tuple[str, int, int], Optional[Path]] = {}
        self.png_cache: dict[Path, Path] = {}
        self._all_files: list[Path] = sorted(p for p in data_dir.iterdir() if p.is_file())
        self._by_name: dict[str, Path] = {p.name: p for p in self._all_files}
        self._dimensions: dict[Path, tuple[float, float]] = {}
        # IWA-derived ground truth: (slide_no, bbox) → exact Data/ filename.
        # When present, we consult this BEFORE the name-stem heuristic — it's
        # deterministic where the heuristic has to guess between collisions.
        self.iwa_map = iwa_map

    def text_align_for_element(self, slide_no: int, x: float, y: float,
                               w: float, h: float) -> Optional[str]:
        """IWA-sourced text alignment ("left"/"center"/"right"/"justify").
        Returns None when no match — caller falls back to "left" (Keynote's
        default for unstyled text)."""
        if self.iwa_map is None:
            return None
        return self.iwa_map.text_alignment(slide_no, x, y, w, h)

    def text_line_height_for_element(self, slide_no: int, x: float, y: float,
                                     w: float, h: float) -> float:
        """IWA-sourced line-height multiplier from lineSpacing.amount.
        Returns 0.0 when not specified (caller uses its default)."""
        if self.iwa_map is None:
            return 0.0
        return self.iwa_map.text_line_height(slide_no, x, y, w, h)

    def resolve_with_bbox(self, slide_no: int, x: float, y: float,
                          w: float, h: float, file_name: str,
                          kind: Optional[str] = None,
                          is_master: bool = False):
        """Like resolve_for_element, but also returns the IWA's TRUE bbox
        AND a `has_mask` flag.

        Returns (Path, (x, y, w, h), has_mask) or (Path, None, False) if
        IWA didn't supply a bbox (legacy heuristic path), or None if
        nothing resolved at all.
        """
        if self.iwa_map is not None:
            # For MASTER elements, query master_filename FIRST. Master images
            # aren't in _by_slide[slide_no] (they live in the template, not
            # in the slide's own iwa), so lookup_with_bbox would either miss
            # them or wrongly match a same-stem ITEM on the same slide (e.g.
            # p86 has 4 images all called "已粘贴的影片.png" — the master
            # bg + 3 UI screenshots — and the legacy path picked a screenshot
            # for the bg because they're in _by_slide).
            if is_master and file_name:
                fname = self.iwa_map.master_filename(slide_no, file_name)
                if fname:
                    p = self._by_name.get(fname)
                    if p is not None:
                        bbox = self.iwa_map.master_bbox(slide_no, file_name)
                        return (p, bbox, False)
            hit = self.iwa_map.lookup_with_bbox(slide_no, x, y, w, h,
                                                file_name=file_name, kind=kind)
            if hit:
                fname, bbox, has_mask = hit
                p = self._by_name.get(fname)
                if p is not None:
                    return (p, bbox, has_mask)
        # Legacy stem+dimension fallback. We INTENTIONALLY skip this for
        # master images: when IWA can't resolve a master file, falling back
        # to a global stem-match by aspect ratio was the source of every
        # cross-slide pollination bug (p64/p65/p70 all picked the wrong
        # master image because they shared a stem with another slide's
        # asset). Rather miss a master image than show the wrong one.
        if file_name and not is_master:
            p = self.resolve(file_name, w, h)
            if p is not None:
                return (p, None, False)
        return None

    def resolve_for_element(self, slide_no: int, x: float, y: float,
                            w: float, h: float, file_name: str,
                            kind: Optional[str] = None) -> Optional[Path]:
        """Resolve an image/movie element to its Data/ file.

        Strategy: IWA bbox lookup first (deterministic), then fall back to the
        old name-stem heuristic. The IWA path works even when AppleScript
        reports `file_name=""` (some inserted movies don't expose a name).
        """
        if self.iwa_map is not None:
            fname = self.iwa_map.lookup(slide_no, x, y, w, h,
                                       file_name=file_name, kind=kind)
            if fname:
                hit = self._by_name.get(fname)
                if hit is not None:
                    return hit
        # Fallback: legacy stem + dimension heuristic. Keeps things working
        # if (a) keynote-parser isn't installed, or (b) the bbox match fails
        # for some edge case (rotated groups, etc.).
        if file_name:
            return self.resolve(file_name, w, h)
        return None

    def _intrinsic_size(self, p: Path) -> Optional[tuple[float, float]]:
        if p in self._dimensions:
            return self._dimensions[p]
        try:
            if p.suffix.lower() == ".pdf":
                doc = fitz.open(p)
                rect = doc[0].rect
                doc.close()
                size = (rect.width, rect.height)
            elif p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".tiff", ".bmp"):
                img = Image.open(p)
                size = img.size
                img.close()
            elif p.suffix.lower() == ".svg":
                # Parse viewBox or width/height from the SVG header.
                import xml.etree.ElementTree as ET
                try:
                    root = ET.parse(p).getroot()
                    vb = root.get("viewBox")
                    if vb:
                        nums = vb.split()
                        if len(nums) == 4:
                            size = (float(nums[2]), float(nums[3]))
                        else:
                            return None
                    else:
                        w = root.get("width", "").rstrip("px")
                        h = root.get("height", "").rstrip("px")
                        size = (float(w), float(h))
                except Exception:
                    return None
            else:
                return None
            self._dimensions[p] = size
            return size
        except Exception:
            return None

    @staticmethod
    def _strip_id_suffix(fname: str) -> str:
        if "." in fname:
            stem, _ = fname.rsplit(".", 1)
        else:
            stem = fname
        return re.sub(r"-small-\d+$|-\d+$", "", stem)

    def resolve(self, file_name: str, want_w: float, want_h: float) -> Optional[Path]:
        if not file_name:
            return None
        key = (file_name, int(want_w), int(want_h))
        if key in self.cache:
            return self.cache[key]

        reported_stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        reported_ext = file_name.rsplit(".", 1)[1].lower() if "." in file_name else ""

        candidates: list[Path] = []
        for p in self._all_files:
            if "small" in p.stem:
                continue
            if self._strip_id_suffix(p.name) == reported_stem:
                candidates.append(p)

        if not candidates:
            self.cache[key] = None
            return None

        if len(candidates) == 1:
            self.cache[key] = candidates[0]
            return candidates[0]

        # FILTER BY EXTENSION FIRST: when AppleScript reports a specific file
        # extension (e.g. `.tiff`), prefer candidates with the same extension
        # before falling back to dimension matching. This fixes the bug where
        # slide 37's `已粘贴的图像.tiff` was matched to a .png (robot image)
        # instead of the .tiff (pink-gradient bg) because aspect-ratio-only
        # matching favored the .png whose bbox aspect happened to match.
        if reported_ext:
            same_ext = [c for c in candidates if c.suffix.lower().lstrip(".") == reported_ext]
            if same_ext:
                candidates = same_ext

        # Multi-candidate: filter by minimum size (source >= 0.5 × displayed area)
        target_area = max(1.0, want_w * want_h)
        big_enough: list[Path] = []
        for c in candidates:
            sz = self._intrinsic_size(c)
            if sz is None:
                continue
            if sz[0] * sz[1] >= 0.5 * target_area:
                big_enough.append(c)

        pool = big_enough if big_enough else candidates

        # Score by aspect ratio match; size as gentle tiebreaker
        target_ratio = want_w / want_h if want_h else 1
        scored: list[tuple[float, Path]] = []
        for c in pool:
            sz = self._intrinsic_size(c)
            if sz is None:
                continue
            cw, ch = sz
            cratio = cw / ch if ch else 1
            ratio_diff = abs(cratio - target_ratio) / max(cratio, target_ratio)
            # log-ish size proximity, capped
            size_ratio = min(cw * ch, target_area) / max(cw * ch, target_area)
            size_diff = 1 - size_ratio
            score = ratio_diff + size_diff * 0.05  # ratio dominates but penalize huge mismatches
            scored.append((score, c))
        scored.sort()
        best = scored[0][1] if scored else None
        self.cache[key] = best
        return best

    def to_png(self, src: Path, slide_assets_dir: Path) -> Path:
        slide_assets_dir.mkdir(parents=True, exist_ok=True)
        if src in self.png_cache:
            cached = self.png_cache[src]
            dst = slide_assets_dir / cached.name
            if not dst.exists():
                shutil.copy(cached, dst)
            return dst

        suffix = src.suffix.lower()
        if suffix == ".pdf":
            doc = fitz.open(src)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=True)
            dst = slide_assets_dir / (src.stem + ".png")
            pix.save(dst)
            doc.close()
        elif suffix in (".tiff", ".tif", ".bmp"):
            # Browsers don't reliably render TIFF/BMP — convert via Pillow.
            img = Image.open(src)
            dst = slide_assets_dir / (src.stem + ".png")
            img.convert("RGBA").save(dst)
            img.close()
        else:
            # .png / .jpg / .jpeg / .gif / .svg — browsers can render directly.
            dst = slide_assets_dir / src.name
            shutil.copy(src, dst)

        self.png_cache[src] = dst
        return dst


# ----------------------------------------------------------------------------
# Raster fallback — crop unhandled element regions from page PNG
# ----------------------------------------------------------------------------

class RasterFallback:
    """Crop bbox regions from rasterized page PNGs as fallback for elements we
    can't reconstruct structurally (lines, charts, tables, shapes with no
    extractable fill, etc.)."""

    def __init__(self, rasters_dir: Optional[Path], pdf_path: Optional[Path],
                 slides_with_kn_no: list[int]):
        """slides_with_kn_no: ordered Keynote slide numbers of non-skipped slides;
        index in this list is the PDF page number - 1."""
        self.rasters_dir = rasters_dir
        self.pdf_path = pdf_path
        # Map keynote_slide_no → PDF page number (1-based)
        self.kn_to_pdf_page: dict[int, int] = {
            kn: idx + 1 for idx, kn in enumerate(slides_with_kn_no)
        }
        self._page_cache: dict[int, Image.Image] = {}
        self._raster_pdf_doc: Optional[fitz.Document] = None
        if not self.rasters_dir and self.pdf_path:
            try:
                self._raster_pdf_doc = fitz.open(self.pdf_path)
            except Exception as e:
                print(f"  warning: could not open --pdf for fallback: {e}", file=sys.stderr)

    def available(self) -> bool:
        return self.rasters_dir is not None or self._raster_pdf_doc is not None

    def _page_image(self, keynote_no: int) -> Optional[Image.Image]:
        pdf_page = self.kn_to_pdf_page.get(keynote_no)
        if pdf_page is None:
            return None
        if pdf_page in self._page_cache:
            return self._page_cache[pdf_page]

        img: Optional[Image.Image] = None
        if self.rasters_dir:
            # try common naming patterns
            for pattern in (f"slide-{pdf_page:02d}.png", f"slide-{pdf_page:03d}.png",
                            f"p-{pdf_page:03d}.jpg", f"page-{pdf_page:03d}.png"):
                cand = self.rasters_dir / pattern
                if cand.is_file():
                    img = Image.open(cand).convert("RGBA")
                    break
        if img is None and self._raster_pdf_doc is not None:
            try:
                page = self._raster_pdf_doc[pdf_page - 1]
                pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGBA")
            except Exception as e:
                print(f"  warning: PDF page {pdf_page} render failed: {e}", file=sys.stderr)
                img = None

        if img is not None:
            self._page_cache[pdf_page] = img
        return img

    def crop(self, keynote_no: int, x: float, y: float, w: float, h: float,
             out_path: Path) -> Optional[Path]:
        page_img = self._page_image(keynote_no)
        if page_img is None:
            return None
        # clamp
        pw, ph = page_img.size
        # The PDF/raster page is 1920x1080. Element coords are in same canvas units.
        # If raster is different size, scale.
        sx = pw / 1920.0
        sy = ph / 1080.0
        left   = max(0, int(x * sx))
        top    = max(0, int(y * sy))
        right  = min(pw, int((x + w) * sx))
        bottom = min(ph, int((y + h) * sy))
        if right <= left or bottom <= top:
            return None
        crop = page_img.crop((left, top, right, bottom))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_path)
        return out_path


# ----------------------------------------------------------------------------
# HTML composition per slide
# ----------------------------------------------------------------------------

_FONT_WEIGHT_KEYWORDS = [
    # Order matters: longer / more specific keywords first
    ("extralight", 200), ("ultralight", 200),
    ("extrabold", 800), ("ultrabold", 800),
    ("semibold", 600), ("demibold", 600),
    ("heavy", 900), ("black", 900),
    ("bold", 700),
    ("medium", 500),
    ("light", 300),
    ("thin", 100),
    ("regular", 400), ("normal", 400), ("book", 400),
]


def _render_text_runs(el, default_color: str, default_font: str, default_size: float) -> str:
    """Render the text content of a text/shape element.

    When `el.runs` contains 2+ entries, emit `<span>` per run with per-run
    font/size/color/weight applied as inline styles. When empty (or 1 run),
    fall back to the container's default styling (just escape + br).

    Newlines become <br> regardless.
    """
    text_fallback = html_lib.escape(el.text).replace("\n", "<br>")
    if len(el.runs) < 2:
        return text_fallback
    out_parts: list[str] = []
    for run in el.runs:
        rt = run.get("text", "")
        if not rt:
            continue
        rfont = run.get("font") or default_font
        rsize = run.get("size") or default_size
        rcolor = _kn_rgb_to_hex(run.get("r", 0), run.get("g", 0), run.get("b", 0)) or default_color
        rweight, rstyle = parse_font_weight_style(rfont)
        rstack = text_font_stack(rfont)
        rt_html = html_lib.escape(rt).replace("\n", "<br>")
        out_parts.append(
            f'<span style="font-family:{rstack};font-size:{rsize:.1f}px;'
            f'font-weight:{rweight};font-style:{rstyle};color:{rcolor};">'
            f'{rt_html}</span>'
        )
    return "".join(out_parts) if out_parts else text_fallback


def parse_font_weight_style(font_name: str) -> tuple[int, str]:
    """Parse a Keynote font name like 'Helvetica-Bold' or
    'HarmonyOS_Sans_SC_Black' into (font-weight, font-style).

    Returns (400, 'normal') for plain / unparseable names.
    """
    if not font_name:
        return 400, "normal"
    fn = font_name.lower()
    # font-style
    style = "italic" if "italic" in fn or "oblique" in fn else "normal"
    # font-weight — first matching keyword wins (sorted by specificity)
    weight = 400
    for kw, w in _FONT_WEIGHT_KEYWORDS:
        if kw in fn:
            weight = w
            break
    return weight, style


def fit_font_to_box(text: str, container_w: float, container_h: float,
                    original_size: float, line_height: float = 1.35,
                    min_size: float = 12.0) -> float:
    """Identity passthrough (v0.13).

    Previous versions tried to approximate Keynote's "shrink text to fit"
    behavior via char-width heuristics, but the estimation was inherently
    inexact (web fallback fonts vary in width vs the authored
    AlibabaPuHuiTi / HarmonyOS_Sans / FZLTTHK fonts) and produced
    spurious shrinks (slide 21 had 3 same-sized quote lines shrunk to
    3 different sizes). Per user direction (2026-05): always honor the
    AUTHORED font size. If the user wants text resized, they can edit the
    Keynote source or the rendered HTML directly. Browser will wrap text
    natively when it overflows the container width.
    """
    return original_size


def text_font_stack(font_name: str) -> str:
    """Returns a CSS font-family stack using SINGLE quotes for multi-word names —
    so it can be embedded inside an HTML `style="..."` attribute without
    breaking the attribute delimiter. (Critical bug fix v0.5: previously used
    double quotes inside double-quoted style attributes, causing browsers to
    discard everything past `font-family:`.)
    """
    fn = (font_name or "").lower()
    cjk = "'PingFang SC','Microsoft YaHei','Source Han Sans SC','Noto Sans SC',sans-serif"
    latin = "'Helvetica Neue','Helvetica','Arial',sans-serif"
    if "harmony" in fn or "alibaba" in fn or "puhui" in fn or "fangzheng" in fn or "lanting" in fn:
        return cjk
    if "helvetica" in fn or "arial" in fn:
        return f"'{font_name}',{latin}"
    if "songti" in fn or "宋" in fn:
        return f"'{font_name}',{cjk}"
    return f"'{font_name}',{cjk}" if font_name else cjk


def _transform(rotation: float) -> str:
    """CSS transform with !important so it survives feishu's per-slide override
    (`.slide > * { transform: none !important }` from our anti-flash CSS)."""
    if abs(rotation) < 0.01:
        return ""
    return f" transform: rotate({rotation}deg) !important;"


def _text_align(el_x: float, el_w: float, slide_w: float = 1920) -> str:
    """Infer CSS text-align from bbox position.

    AppleScript doesn't reliably expose Keynote's text alignment property
    (`alignment of paragraph 1` throws on certain text items). Use a bbox
    heuristic: when the bbox horizontal center is within ±80 px of the slide
    center, treat the text as center-aligned. Bboxes near the left/right
    margins are treated as left/right-aligned.
    """
    bbox_center = el_x + el_w / 2
    slide_center = slide_w / 2  # 960
    if abs(bbox_center - slide_center) <= 80:
        return "center"
    # bbox sits near right edge → right-align
    if el_x + el_w > slide_w - 40 and el_x > slide_w * 0.5:
        return "right"
    return "left"


# Patterns for Keynote master/layout placeholder text that should NOT render
# on the actual slide. AppleScript returns the placeholder text (visible only
# in editor) as if it were content. Filter known placeholder patterns.
_PLACEHOLDER_PATTERNS = [
    re.compile(r"^\s*$"),                                  # empty / whitespace
    re.compile(r"^\s*正文级别\s*\d+\s*$", re.MULTILINE),    # 正文级别 1 / 2 / 3
    re.compile(r"^(\s*正文级别\s*\d+\s*\n?)+$"),            # multi-line stack
    re.compile(r"^\s*幻灯片标题\s*$"),                      # Slide Title (zh)
    re.compile(r"^\s*副标题\s*$"),                          # Subtitle (zh)
    re.compile(r"^\s*Slide\s+(title|headline)\s*$", re.IGNORECASE),
    re.compile(r"^\s*Subtitle\s*$", re.IGNORECASE),
    re.compile(r"^\s*Presentation\s+Title\s*$", re.IGNORECASE),  # Apple template
    re.compile(r"^\s*Click\s+or\s+tap\s+to", re.IGNORECASE),
    re.compile(r"^\s*(Click|Tap)\s+to\s+(add|edit)", re.IGNORECASE),
    re.compile(r"^\s*Body\s+(text|level)\s*\d*\s*$", re.IGNORECASE),
    re.compile(r"^\s*Lorem\s+ipsum", re.IGNORECASE),
    re.compile(r"^\s*金句页底图\s*$"),                       # decor placeholder
    re.compile(r"^\s*Section\s+Title\s*$", re.IGNORECASE),
    re.compile(r"^\s*Chapter\s+Title\s*$", re.IGNORECASE),
]


def _role_attr(el: "Element") -> str:
    """Emit ` data-role="..."` (leading space) when an element has a role,
    empty string otherwise. See plugin/_spec/deck-json-v2.md §"raw layout
    title 同步规则" — downstream skills find / replace the title element
    via this attribute."""
    return f' data-role="{el.data_role}"' if el.data_role else ""


def pick_title(slide: "Slide") -> str:
    """Choose a title string for a Keynote-imported slide and mark the
    chosen element with `data_role="title"` so compose_slide_html emits
    the `data-role="title"` attribute at the right spot.

    Heuristic: largest font_size among non-master text-bearing elements,
    breaking ties by document order. Strips trailing whitespace and
    collapses to the first line if multi-line. Returns "" when there is
    no usable text on the slide (pure image / video slide) — in that
    case no element is marked.
    """
    best_el = None
    best_size = -1.0
    for el in slide.elements:
        if el.is_master:
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        if is_placeholder_text(text):
            continue
        if el.font_size > best_size:
            best_size = el.font_size
            best_el = el
    if best_el is None:
        return ""
    # Mark the source element so the renderer emits data-role="title".
    best_el.data_role = "title"
    # Title is one line — take the first non-empty line.
    for line in (best_el.text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def is_placeholder_text(text: str) -> bool:
    """True if text looks like a Keynote master/layout placeholder, not real content."""
    if not text:
        return True
    return any(p.match(text) for p in _PLACEHOLDER_PATTERNS)


def _bbox_close(a: Element, b: Element, tol: float = 8.0) -> bool:
    """True if two elements occupy substantially the same bbox (≤ tol px on each side)."""
    return (abs(a.x - b.x) <= tol and abs(a.y - b.y) <= tol
            and abs(a.w - b.w) <= tol and abs(a.h - b.h) <= tol)


def _localize_redesign_assets(
    html: str, redesigns_dir: Path,
    slide_assets_dir: Path, slide_assets_subdir: str,
) -> tuple[str, list[str]]:
    """Take a redesign HTML snippet (which can reference its sibling files
    via `../foo/bar.mp4` style paths) and rewrite it to be self-contained
    inside `<output>/assets/slide-NNN/`.

    For every `src=`, `poster=`, `href=` attribute:
      · Skip absolute URLs (http://, https://, data:, blob:), fragments,
        and refs that already live under `assets/slide-NNN/` or `_renderer/`.
      · Resolve the path against redesigns_dir.
      · If the resolved file exists, copy it into slide_assets_dir/
        (preserving basename) and rewrite the attribute to
        `<slide_assets_subdir>/<basename>`.
      · If the file doesn't exist, leave the ref alone and warn.

    Returns (rewritten_html, warnings).

    This is what makes a deck genuinely zip-and-ship: redesigns that
    pointed OUTSIDE the render-output dir get pulled in.
    """
    import shutil
    warnings: list[str] = []
    if not redesigns_dir or not redesigns_dir.is_dir():
        return html, warnings

    # Match src="..."  src='...'  href="..."  poster="..." etc.
    attr_re = re.compile(
        r'((?:src|href|poster|data-src)\s*=\s*)(["\'])([^"\']+)\2'
    )

    def _rewrite(m):
        prefix, quote, url = m.group(1), m.group(2), m.group(3)
        # Skip stuff we shouldn't touch.
        if url.startswith((
            "http://", "https://", "data:", "blob:", "javascript:",
            "mailto:", "#",
        )):
            return m.group(0)
        # Strip ?query / #frag for filesystem resolution, preserve them
        # for the rewritten URL.
        clean = url.split("?", 1)[0].split("#", 1)[0]
        tail = url[len(clean):]
        if not clean:
            return m.group(0)
        # If already pointing inside the output dir's slide_assets_subdir
        # or under _renderer/, leave alone.
        if clean.startswith(slide_assets_subdir + "/") or clean.startswith("_renderer/"):
            return m.group(0)
        # Resolve relative to redesigns_dir (the HTML's own location).
        src = (redesigns_dir / clean).resolve()
        if not src.is_file():
            warnings.append(
                f"redesign ref not found: {url!r} (resolved {src})"
            )
            return m.group(0)
        # Copy in (basename only; redesigns don't tend to need subfolders).
        slide_assets_dir.mkdir(parents=True, exist_ok=True)
        dst = slide_assets_dir / src.name
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        new_url = f"{slide_assets_subdir}/{src.name}{tail}"
        return f"{prefix}{quote}{new_url}{quote}"

    return attr_re.sub(_rewrite, html), warnings


_REF_ATTR_RE = re.compile(
    r'(?:src|href|poster|data-src)\s*=\s*["\']([^"\']+)["\']'
)


def _collect_refs(html: str) -> set[str]:
    """Return the set of local (non-URL, non-data:) paths referenced by the
    HTML's src/href/poster/data-src attributes, normalised so they can be
    compared against on-disk relative paths."""
    refs: set[str] = set()
    for m in _REF_ATTR_RE.finditer(html):
        url = m.group(1).strip().split("?", 1)[0].split("#", 1)[0]
        if not url:
            continue
        if url.startswith((
            "http://", "https://", "data:", "blob:",
            "javascript:", "mailto:",
        )):
            continue
        refs.add(os.path.normpath(url))
    return refs


def _sweep_orphans(output_dir: Path, deck: dict) -> None:
    """Slim the rendered deck dir down to what's actually needed for serving.

    Removes:
      · `.cache/` — per-build .key extraction cache (recreated on next run).
      · `extract.tsv` / `deck.json.bak` — build intermediates.
      · Files under `assets/` that no slide HTML (or `index.html`) references.

    Doesn't touch `_renderer/`, `serve.sh`, `history.json`, `warnings.txt`,
    or `deck.json` — those are part of the shippable deck.
    """
    # 1. Easy wins: drop build artifacts wholesale.
    for trash in (".cache", "extract.tsv", "deck.json.bak"):
        p = output_dir / trash
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            print(f"    swept {p.name}/")
        elif p.is_file():
            p.unlink()
            print(f"    swept {p.name}")

    # 2. Build the set of paths referenced by ANY slide body or by
    # index.html itself. deck.json is the source of truth for slide HTML,
    # but the renderer also wraps it in chrome that may reference _renderer
    # paths — those live outside assets/, so scanning index.html catches
    # them too.
    referenced: set[str] = set()
    for slide in deck.get("slides", []):
        referenced |= _collect_refs(
            (slide.get("data") or {}).get("html", "")
        )
    idx = output_dir / "index.html"
    if idx.is_file():
        referenced |= _collect_refs(idx.read_text(encoding="utf-8", errors="ignore"))

    # 3. Anything under assets/ that isn't referenced → orphan.
    assets_root = output_dir / "assets"
    if not assets_root.is_dir():
        return
    deleted_files = 0
    bytes_freed = 0
    for p in assets_root.rglob("*"):
        if not p.is_file():
            continue
        rel = os.path.normpath(str(p.relative_to(output_dir)))
        if rel in referenced:
            continue
        try:
            sz = p.stat().st_size
            p.unlink()
            deleted_files += 1
            bytes_freed += sz
        except OSError:
            pass
    if deleted_files:
        print(f"    swept {deleted_files} orphan asset(s), "
              f"freed {bytes_freed / 1024 / 1024:.1f} MB")

    # 4. Cross-slide dedup. Many slides reuse the SAME source asset (e.g.
    # the Rolling AI brand video, master backdrops, repeated UI mockups) —
    # AssetResolver copies a fresh per-slide copy each time. Hash every
    # remaining file; for any group of byte-identical files across two or
    # more slides, keep one in `assets/_shared/<basename>` and rewrite all
    # slide-HTML refs (in deck.json + index.html) to point there.
    import hashlib
    by_hash: dict[str, list[Path]] = {}
    for p in assets_root.rglob("*"):
        if not p.is_file() or p.parent == assets_root:
            continue  # skip top-level (e.g. anything in _shared/ from a prior run)
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        by_hash.setdefault(h.hexdigest(), []).append(p)

    rewrites: dict[str, str] = {}        # old rel path → new rel path
    shared_dir = assets_root / "_shared"
    shared_saved = 0
    shared_files = 0
    for digest, paths in by_hash.items():
        if len(paths) < 2:
            continue
        # Pick a stable shared name. Use basename. On collision (same name,
        # different content) prefix with a short hash slice — but in practice
        # collisions within a dedup group can't happen (same hash → same bytes).
        canonical_name = paths[0].name
        shared_dir.mkdir(parents=True, exist_ok=True)
        shared_target = shared_dir / canonical_name
        if shared_target.exists() and shared_target.stat().st_size != paths[0].stat().st_size:
            # Different file already squatting on this name. Disambiguate.
            shared_target = shared_dir / f"{paths[0].stem}-{digest[:8]}{paths[0].suffix}"
        # Move the first copy in (rename, not copy — saves bytes immediately).
        if not shared_target.exists():
            paths[0].rename(shared_target)
        else:
            paths[0].unlink()
        rewrites[os.path.normpath(str(paths[0].relative_to(output_dir)))] = (
            os.path.normpath(str(shared_target.relative_to(output_dir)))
        )
        shared_files += 1
        # Delete the rest, queue rewrite.
        for dup in paths[1:]:
            sz = dup.stat().st_size
            rewrites[os.path.normpath(str(dup.relative_to(output_dir)))] = (
                os.path.normpath(str(shared_target.relative_to(output_dir)))
            )
            dup.unlink()
            shared_saved += sz
            shared_files += 1
    if rewrites:
        print(f"    deduped {shared_files} files → {len(by_hash) - sum(1 for v in by_hash.values() if len(v)<2)} shared, "
              f"freed {shared_saved / 1024 / 1024:.1f} MB")

        # Apply rewrites to deck.json + index.html. The HTML stores paths
        # like `assets/slide-NNN/foo.mp4`; replace with the shared path.
        def _apply(text: str) -> str:
            for old, new in rewrites.items():
                text = text.replace(old, new)
            return text

        deck_path = output_dir / "deck.json"
        if deck_path.is_file():
            deck_path.write_text(
                _apply(deck_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
        if idx.is_file():
            idx.write_text(
                _apply(idx.read_text(encoding="utf-8")),
                encoding="utf-8",
            )

    # 5. Sweep empty slide dirs.
    for d in sorted(assets_root.iterdir(), reverse=True):
        if d.is_dir() and d.name != "_shared":
            try:
                if not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass


def _localize_renderer_refs(html_path: Path, renderer_local: Path,
                            renderer_skill_root: Path) -> None:
    """Copy renderer CSS/JS files into <output>/_renderer/ and rewrite
    index.html refs to use that local path.

    Scans for any `href="..."` or `src="..."` URL containing
    `feishu-deck-h5/` (with any number of `../` prefixes). For each:
      1. Resolves the path relative to renderer_skill_root.
      2. Copies the file into renderer_local/, preserving subfolders
         after `feishu-deck-h5/`.
      3. Rewrites the HTML ref to the local path.

    Idempotent: safe to re-run.
    """
    if not html_path.is_file():
        return
    html = html_path.read_text(encoding="utf-8")

    # Match references like `href="..."` or `src="..."` whose value
    # contains `plugin/skills/feishu-deck-h5/`. Previous regex matched a
    # pure `../`-stack prefix only — fine when output_dir is inside the
    # repo (relpath produces clean `../../../plugin/...`), but breaks
    # when output_dir is outside the repo, e.g. /tmp/build. There the
    # relpath has to climb to the filesystem root and descend into
    # `/Users/liukai/dev/RollingAI DeckBuilder/plugin/...`. The literal
    # space in "RollingAI DeckBuilder" further trips the simpler form of
    # this regex. We now scope the match between the attribute's quote
    # characters and allow ANY characters (including spaces) for the
    # prefix; the substitution drops the prefix and writes a local
    # `_renderer/...` path.
    pat = re.compile(
        r'((?:href|src)\s*=\s*)(["\'])'   # 1=attr=  2=open-quote
        r'([^"\']*?)'                     # 3=prefix junk
        r'plugin/skills/feishu-deck-h5/'
        r'([^"\'?#]+)'                    # 4=relative path inside skill
        r'(\2)',                          # 5=closing-quote (same as opener)
        re.IGNORECASE,
    )
    renderer_local.mkdir(parents=True, exist_ok=True)
    copied = 0
    seen: set[str] = set()

    def _sub(m):
        nonlocal copied
        # Groups: 1=attr= (href= / src=), 2=open-quote, 3=prefix junk,
        #         4=rel path inside skill, 5=close-quote.
        attr  = m.group(1)
        quote = m.group(2)
        rest  = m.group(4)
        src = renderer_skill_root / rest
        if not src.is_file():
            # Unknown ref — leave it alone so the broken state is visible
            # rather than silently mangled.
            return m.group(0)
        dst = renderer_local / rest
        if rest not in seen:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, dst)
                copied += 1
            seen.add(rest)
        return f"{attr}{quote}_renderer/{rest}{quote}"

    new_html = pat.sub(_sub, html)
    if new_html != html:
        html_path.write_text(new_html, encoding="utf-8")
    print(f"    localized renderer: {len(seen)} refs · {copied} files copied to _renderer/")


def _object_fit_for(natural_w: float, natural_h: float,
                    render_w: float, render_h: float) -> str:
    """Pick `object-fit: cover` vs `contain` based on aspect comparison.

    The default in HTML for our renderer is `cover` (fill the box, crop
    overflow). That's fine when the image's natural aspect roughly matches
    the render box — OR when the image is TALLER than the box (e.g. phone
    screenshots in a portrait slot, where cover crops top/bottom which is
    the intentional Keynote display).

    But when the image is significantly WIDER than the box (e.g. 邮政储蓄
    银行 logo natural 624×53 in a 206×42 slot, or FOTILE natural 517×232
    in a 193×31 slot), cover crops the LEFT/RIGHT and we lose the start /
    end of the logo. Authors expect the full logo to remain readable; use
    `contain` instead — image fits fully, with vertical letterbox.

    Threshold: 25% aspect drift. Below that, natural≈container and cover
    is fine. Above that, only switch to contain when natural is the WIDER
    one (we don't want to letterbox tall phone shots).
    """
    if natural_w <= 0 or natural_h <= 0 or render_w <= 0 or render_h <= 0:
        return "cover"
    nat_ratio = natural_w / natural_h
    ren_ratio = render_w / render_h
    drift = abs(nat_ratio - ren_ratio) / max(ren_ratio, nat_ratio)
    if drift < 0.25:
        return "cover"
    # Natural wider than container → cover would crop sides → use contain.
    if nat_ratio > ren_ratio:
        return "contain"
    # Natural taller than container → cover crops top/bottom, usually the
    # intentional Keynote display for portrait images (phones, hero shots).
    return "cover"


# Keynote named shape paths in a 100×100 viewBox. Add new entries to handle
# additional shape kinds without changing the renderer logic.
#
# Coordinate system: SVG y-axis points DOWN (top=0, bottom=100). Each path is
# pre-oriented so it visually looks right when drawn with NO rotation applied.
# Rotation comes from the IWA geometry.angle (or AppleScript's el.rotation),
# applied as `transform: rotate(angle deg)` around the bbox center.
_NAMED_SHAPE_PATHS = {
    # Single arrows. Shape is drawn pointing RIGHT; Keynote left/up/down
    # variants are typically just the same shape with a 90/180/270° angle.
    "kTSDRightSingleArrow": "M0 32 L60 32 L60 8 L100 50 L60 92 L60 68 L0 68 Z",
    "kTSDLeftSingleArrow":  "M100 32 L40 32 L40 8 L0 50 L40 92 L40 68 L100 68 Z",
    "kTSDUpSingleArrow":    "M32 100 L32 40 L8 40 L50 0 L92 40 L68 40 L68 100 Z",
    "kTSDDownSingleArrow":  "M32 0 L32 60 L8 60 L50 100 L92 60 L68 60 L68 0 Z",
    # Bidirectional arrow. Two arrowheads, stem in middle.
    "kTSDDoubleArrow":      "M0 50 L20 25 L20 40 L80 40 L80 25 L100 50 "
                            "L80 75 L80 60 L20 60 L20 75 Z",
    # Up-down bidirectional.
    "kTSDDoubleArrowVertical": "M50 0 L25 20 L40 20 L40 80 L25 80 L50 100 "
                               "L75 80 L60 80 L60 20 L75 20 Z",
    # Five-pointed star, geometric center at (50, 53). Outer radius 47,
    # inner radius 18.5 — standard proportions.
    "kTSDStar": "M50 5 L61 39 L95 39 L68 60 L79 95 L50 73 "
                "L21 95 L32 60 L5 39 L39 39 Z",
    # Triangle variants. SVG path is the OUTLINE filled solid.
    "kTSDIsoscelesTriangle": "M50 0 L100 100 L0 100 Z",
    "kTSDTriangle":          "M50 0 L100 100 L0 100 Z",
    "kTSDRightTriangle":     "M0 0 L100 100 L0 100 Z",
}

def _render_named_shape_svg(kind: str, x: float, y: float, w: float, h: float,
                            fill_css: str, angle: float, opacity: float = 1.0,
                            extra_style: str = "") -> str:
    """Emit an SVG positioned at (x,y) with size (w,h), drawing the named
    Keynote shape with the given fill. Rotation is applied around the bbox
    center via SVG's transform. Returns "" if `kind` is unknown."""
    path = _NAMED_SHAPE_PATHS.get(kind)
    if not path:
        return ""
    # SVG's transform-origin defaults to (0,0). Use a centered rotation by
    # applying transform on the inner <g>: translate to center, rotate, then
    # translate back. Simpler: rotate via CSS transform on the wrapper.
    op_css = f"opacity:{opacity:.3f};" if opacity < 0.999 else ""
    # Keynote geometry.angle is counter-clockwise-positive; CSS rotate() is
    # clockwise-positive — so negate. And emit `!important`: without it the
    # anti-flash rule `.slide > * { transform: none !important }` kills the
    # rotation and the shape renders in its base orientation (this is why
    # p17's up-arrows — kTSDRightSingleArrow at angle=90 — showed pointing
    # RIGHT). The image-rotation path already had this fix; shapes were missed.
    rot_css = (f"transform:rotate({(360.0 - angle) % 360.0:.3f}deg) !important;"
               if abs(angle) > 0.01 else "")
    return (
        f'<svg class="el" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 100 100" preserveAspectRatio="none" '
        f'style="position:absolute;left:{x}px;top:{y}px;'
        f'width:{w}px;height:{h}px;{rot_css}{op_css}{extra_style}">'
        f'<path d="{path}" fill="{fill_css}"/></svg>'
    )


def _css_gradient_to_svg_defs(css: str, grad_id: str) -> str:
    """Turn `linear-gradient(<angle>deg, <stop1>, <stop2>, ...)` into an SVG
    <defs><linearGradient id=...>…</linearGradient></defs> block.

    Each stop is `rgba(r,g,b,a) <pct>%` or `<color> <pct>%`. We split on
    top-level commas (not commas inside `rgba(...)`).

    Returns the <defs> markup, or "" if parsing fails. Caller falls back to
    a plain fill in that case.
    """
    m = re.match(r"linear-gradient\(\s*([-\d.]+)deg\s*,\s*(.+)\)\s*$", css.strip())
    if not m:
        return ""
    try:
        angle_deg = float(m.group(1))
    except ValueError:
        return ""
    body = m.group(2)
    # Split on commas at depth 0 (parens for rgba/rgb track depth).
    stops_raw: list[str] = []
    depth, start = 0, 0
    for i, ch in enumerate(body):
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        elif ch == "," and depth == 0:
            stops_raw.append(body[start:i].strip()); start = i + 1
    stops_raw.append(body[start:].strip())

    stops: list[tuple[float, str, float]] = []
    for s in stops_raw:
        sm = re.match(r"(.+?)\s+([\d.]+)%\s*$", s)
        if not sm: return ""
        color = sm.group(1).strip()
        try:
            pct = float(sm.group(2))
        except ValueError:
            return ""
        rgb = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)", color)
        if rgb:
            r, g, b = rgb.group(1), rgb.group(2), rgb.group(3)
            a = float(rgb.group(4)) if rgb.group(4) else 1.0
            stops.append((pct, f"rgb({r},{g},{b})", a))
        else:
            # Hex or named — pass through; SVG will accept it.
            stops.append((pct, color, 1.0))

    # CSS gradient angle convention: 0deg = up (gradient flows from bottom
    # to top). SVG x1/y1/x2/y2 is in objectBoundingBox 0..1, with y=0 at
    # top. To map: CSS 0deg → SVG (0.5, 1) → (0.5, 0). General:
    #   rad = (angle - 90) * π / 180   (CSS deg to SVG axis angle)
    #   delta = 0.5
    #   x1 = 0.5 - cos(rad) * 0.5; y1 = 0.5 + sin(rad) * 0.5  (start)
    #   x2 = 0.5 + cos(rad) * 0.5; y2 = 0.5 - sin(rad) * 0.5  (end)
    import math
    rad = math.radians(angle_deg - 90.0)
    x1 = 0.5 - math.cos(rad) * 0.5
    y1 = 0.5 + math.sin(rad) * 0.5
    x2 = 0.5 + math.cos(rad) * 0.5
    y2 = 0.5 - math.sin(rad) * 0.5

    stop_xml = "".join(
        f'<stop offset="{pct:.2f}%" stop-color="{c}" stop-opacity="{a:.3f}"/>'
        for pct, c, a in stops
    )
    return (
        f'<defs><linearGradient id="{grad_id}" '
        f'x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}">'
        f'{stop_xml}</linearGradient></defs>'
    )


def _emit_iwa_fill_div(sf, in_place: bool, under_image: bool = False) -> str:
    """Render an IWA `_ShapeFill` as a positioned `<div>`.

    in_place=True   → emitted at source position (no z-index; document order
                      is the source of truth — shape comes before video
                      gets stacked under it).
    in_place=False  → emitted at end (z-index:5; sits above images/videos
                      but below text at z-index:10).
    under_image=True overrides to z-index:-1 — used when an IWA fill's
                      bbox heavily overlaps a content image (dark vignettes,
                      backdrop tints on photo slides). Without this, p19/20/
                      22/63's near-opaque gradient overlays hid their
                      content images entirely.
    """
    if sf.gradient_css:
        bg = f"background:{sf.gradient_css};"
        op_part = f"opacity:{sf.alpha:.3f};" if sf.alpha < 0.999 else ""
    else:
        bg = f"background:rgba({sf.r},{sf.g},{sf.b},{sf.alpha:.3f});"
        op_part = ""
    if under_image:
        z = "z-index:-1;"
    elif in_place:
        z = ""
    else:
        z = "z-index:5;"
    return (
        f'<div class="el iwa-fill" style="left:{sf.x:.0f}px;top:{sf.y:.0f}px;'
        f'width:{sf.w:.0f}px;height:{sf.h:.0f}px;'
        f'{bg}{op_part}{z}pointer-events:none;"></div>'
    )


def compose_slide_html(slide: Slide, resolver: AssetResolver,
                       raster: RasterFallback,
                       slide_assets_subdir: str,
                       slide_assets_dir: Path) -> tuple[str, list[str]]:
    parts: list[str] = []
    warnings: list[str] = []
    key = f"slide-{slide.keynote_no:03d}"

    # Background heuristic: AppleScript's #SLIDE-META gives us the master's fill
    # color only when it's a plain color fill — many Keynote masters use image/
    # gradient fills that don't expose. Fall back to inferring from master name
    # via the layout name (we don't currently pass that through; instead, when
    # bg_r/g/b are all zero AND we're in a "white master" context, the user
    # can override). For now: keep extracted bg; if (0,0,0) and the slide has
    # ANY element with text color #000, assume the master is white.
    # Priority: IWA SlideStyleArchive (authored bg, color or gradient) →
    # AppleScript #SLIDE-META (color fills only — gradient/image fall through)
    # → text-color heuristic. Heuristic is the last resort, NOT first.
    bg = (resolver.iwa_map.slide_background(slide.keynote_no)
          if resolver.iwa_map is not None else None)
    # Slide-bg image fill sentinel: resolver emits "__SLIDE_BG_IMAGE__:<file>"
    # when the slide style's fill is an image. Stage the file into _shared/
    # and turn into a real CSS url(). Falls back to a transparent bg if the
    # file can't be located in Data/.
    if isinstance(bg, str) and bg.startswith("__SLIDE_BG_IMAGE__:"):
        img_fn = bg[len("__SLIDE_BG_IMAGE__:"):]
        src = resolver._by_name.get(img_fn) if hasattr(resolver, "_by_name") else None
        if src and src.is_file():
            shared_dir = resolver.out_assets_dir / "_shared"
            shared_dir.mkdir(parents=True, exist_ok=True)
            dst = shared_dir / src.name
            if not dst.exists():
                import shutil as _sh
                _sh.copy2(src, dst)
            bg = f"url('assets/_shared/{src.name}') center/cover no-repeat"
        else:
            bg = None  # image not findable → fall through
    if bg is None and slide.has_bg_color:
        bg = slide.bg_hex
    if bg is None:
        # Heuristic: if any SLIDE-LEVEL (not master, not placeholder) text
        # element uses near-black color, the slide background is probably
        # white. Master text uses theme-default black even on dark slides —
        # and slide-level shapes with placeholder content (e.g. "金句页底图"
        # which is a decor placeholder named with black theme text) would
        # also pollute the check. Filter both out.
        # Area-weighted: compare TOTAL bbox area of dark-text vs near-white
        # text elements. Whichever wins decides the slide bg. Old heuristic
        # ("any black text → white bg") was tripped by a single small icon
        # glyph and flipped dark-bg slides to white (eCINDI 6/7/9).
        dark_area = 0.0
        white_area = 0.0
        # Build the set of "colored panels" on this slide — any shape with
        # AppleScript fill, plus all IWA fills. A text element sitting inside
        # one of these panels tells us about the PANEL bg, not the slide bg.
        # Without this filter, p74's white title text ("通过WOW健康+...")
        # sitting inside a green bar drowned out the dark body text and
        # resolved the slide to #000 (it should be #FFF).
        iwa_fills_here = (resolver.iwa_map.shape_fills_for_slide(slide.keynote_no)
                          if resolver.iwa_map else [])
        panels = []  # list of (x, y, w, h) bboxes of filled regions
        for el in slide.elements:
            if el.type == "shape" and el.has_fill and not el.is_master:
                panels.append((el.x, el.y, el.w, el.h))
        for sf in iwa_fills_here:
            panels.append((sf.x, sf.y, sf.w, sf.h))
        def _inside_panel(el) -> bool:
            # Element is "on a panel" if its center sits inside any filled
            # bbox AND it's not dramatically larger than the panel (which
            # would suggest the panel is a small decoration over a larger
            # text, not the other way around).
            cx, cy = el.x + el.w / 2, el.y + el.h / 2
            for px, py, pw, ph in panels:
                if px <= cx <= px + pw and py <= cy <= py + ph:
                    if el.w <= pw * 1.4 and el.h <= ph * 1.4:
                        return True
            return False

        for el in slide.elements:
            if el.is_master: continue
            # Only PLAIN TEXT elements count for slide-bg inference. Shapes
            # always have some form of background (fill, theme color, banner
            # bg) that's not always visible to AppleScript/IWA — counting
            # them by text color led to p74 wrongly resolving to #000
            # because the green title-bar shape's white text outweighed
            # all the plain dark body text.
            if el.type != "text": continue
            if not el.text.strip(): continue
            if is_placeholder_text(el.text): continue
            # Skip text that sits on top of a colored panel — its
            # background is the panel, not the slide.
            if _inside_panel(el):
                continue
            s = el.r + el.g + el.b
            a = max(0.0, el.w) * max(0.0, el.h)
            if s < 20000:    dark_area += a
            elif s > 180000: white_area += a
        bg = "#000" if white_area > dark_area else "#FFFFFF"

    parts.append(f"<style>")
    # `isolation: isolate` creates a stacking context on the slide so
    # children rendered at z-index:-1 (backdrop iwa-fills paired with
    # content images) stay INSIDE the slide instead of escaping up to
    # the page root where they'd be hidden by the slide's own background.
    parts.append(f".slide[data-slide-key='{key}'] {{ background: {bg}; overflow: hidden; isolation: isolate; }}")
    parts.append(f".slide[data-slide-key='{key}'] .el {{ position: absolute; transform-origin: center center; }}")
    parts.append(f".slide[data-slide-key='{key}'] .shape {{ box-sizing: border-box; }}")
    # CRITICAL: feishu-deck-h5's "stagger reveal" rule sets
    #   .slide-frame.is-current .slide > * { opacity: 0; transform: ...; animation: fs-reveal ... }
    # The animation transitions opacity 0 → 1 over 0.28s. We disable the
    # animation so authored opacity (e.g. 22% for a translucent bg) is honored
    # — but the base rule's `opacity: 0` would then make elements WITHOUT
    # inline opacity permanently invisible (black slide on navigate). So we
    # also set `opacity: 1` as the default; inline opacity (smaller values)
    # naturally wins via higher specificity.
    parts.append(
        f".slide[data-slide-key='{key}'].slide > * {{ "
        f"animation: none !important; "
        f"transform: none !important; "
        f"opacity: 1; "
        f"}}"
    )
    # z-index discipline so IWA-sourced shape backdrops (translucent black
    # masks, card-fill overlays) layer correctly:
    #   img / video : 0   (slide backgrounds)
    #   .iwa-fill   : 5   (the backdrops we synthesize from style chain)
    #   text/shape  : 10  (all <div class="el ..."> except .iwa-fill)
    # No z-index categories. Source draw order (= DOM order) is the truth
    # from Keynote: bg image → card backdrops → content images → text. The
    # earlier discipline (img:0 / iwa-fill:5 / text:10) flattened all images
    # to one layer and broke decks where a content image lives ABOVE a card
    # backdrop (eCINDI slide 6: white card + dashboard image inside it).
    # Equal stacking, later DOM = on top.
    parts.append(f"</style>")

    SLIDE_W, SLIDE_H = 1920, 1080
    # Master-element suppression: ONLY for template placeholder text/shape
    # ("幻灯片标题", "正文级别 1", etc.) — Keynote literally doesn't render
    # those strings, they're authoring hints in the editor. Everything else
    # from the master (background image, footer chrome, page-number marker)
    # is preserved; z-order + opacity handle whether it actually shows.
    suppressed_master: set[int] = set()
    for i, el in enumerate(slide.elements):
        if not el.is_master:
            continue
        if el.type in ("text", "shape") and is_placeholder_text(el.text):
            suppressed_master.add(i)

    # Match IWA shape-fills to AppleScript shape elements by bbox. When the
    # AppleScript shape has no fill / no text (the typical "empty shape used
    # as a colored rectangle" case), we replace its emission with the IWA
    # backdrop — placed at the SAME position in the parts list so source
    # draw-order is preserved (e.g. slide 18 has the shape BEFORE the video,
    # so its black backdrop must render UNDER the video, not over it).
    iwa_fills = (resolver.iwa_map.shape_fills_for_slide(slide.keynote_no)
                 if resolver.iwa_map is not None else [])
    iwa_fill_for_idx: dict[int, object] = {}  # AppleScript elem idx → _ShapeFill
    iwa_consumed: set[int] = set()  # indices into iwa_fills that paired off
    for fi, sf in enumerate(iwa_fills):
        # Find AppleScript element with best bbox overlap (must be a shape,
        # and the bboxes must be close — we don't want to attach an opaque
        # full-canvas backdrop to a tiny placeholder by accident).
        best_idx, best_score = None, 0.0
        for j, ej in enumerate(slide.elements):
            if ej.type != "shape":
                continue
            # IoU-ish score, rough
            ix0, iy0 = max(sf.x, ej.x), max(sf.y, ej.y)
            ix1, iy1 = min(sf.x + sf.w, ej.x + ej.w), min(sf.y + sf.h, ej.y + ej.h)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            inter = (ix1 - ix0) * (iy1 - iy0)
            union = sf.w * sf.h + ej.w * ej.h - inter
            score = inter / union if union > 0 else 0
            if score > best_score:
                best_score, best_idx = score, j
        if best_idx is not None and best_score >= 0.5:
            iwa_fill_for_idx[best_idx] = sf
            iwa_consumed.add(fi)
            continue
        # IoU fallback: rotated shapes report DIFFERENT bbox in AppleScript
        # (rotated bbox = larger, top-left offset) vs IWA (un-rotated geometry).
        # A 100×100 square at 45° has rotated bbox 141×141 shifted ~20px, so
        # IoU drops to ~0.47 — below the strict 0.5 cutoff. For these, fall
        # back to center-distance matching with a tolerance scaled to the
        # shape size. Only triggers when there's actually a named shape kind
        # to render (otherwise we'd be matching random small decoration to
        # random small shapes).
        if not sf.shape_kind:
            continue
        sf_cx, sf_cy = sf.x + sf.w / 2, sf.y + sf.h / 2
        tol = max(30.0, max(sf.w, sf.h) * 0.30)
        best2, best_d = None, tol
        for j, ej in enumerate(slide.elements):
            if ej.type != "shape" or j in iwa_fill_for_idx:
                continue
            cx, cy = ej.x + ej.w / 2, ej.y + ej.h / 2
            d = ((cx - sf_cx) ** 2 + (cy - sf_cy) ** 2) ** 0.5
            if d < best_d:
                best_d, best2 = d, j
        if best2 is not None:
            iwa_fill_for_idx[best2] = sf
            iwa_consumed.add(fi)

    # Suppress any iwa-fill that covers (essentially) the entire canvas IF
    # a same-size image sits at the same position. Such an iwa-fill is the
    # slide's master backdrop in Keynote — completely hidden by the photo
    # on top — but we were emitting it as a foreground div, which (due to
    # CSS z-index discipline) ends up covering the photo. Drop it here.
    SLIDE_W_CHECK, SLIDE_H_CHECK = 1920, 1080
    has_full_canvas_image = any(
        e.type == "image" and abs(e.x) < 20 and abs(e.y) < 20
        and e.w >= SLIDE_W_CHECK * 0.97 and e.h >= SLIDE_H_CHECK * 0.97
        for e in slide.elements
    )
    canvas_backdrop_idxs: set[int] = set()
    if has_full_canvas_image:
        for idx in list(iwa_fill_for_idx.keys()):
            sf2 = iwa_fill_for_idx[idx]
            if (sf2.w >= SLIDE_W_CHECK * 0.97 and sf2.h >= SLIDE_H_CHECK * 0.97
                    and abs(sf2.x) < 20 and abs(sf2.y) < 20):
                del iwa_fill_for_idx[idx]
                canvas_backdrop_idxs.add(idx)

    # Pre-pass: detect shape+image pairs occupying the same bbox.
    # In Keynote these are "stylized image placeholders" — a shape with a fill
    # (often gradient/theme) acting as a frame, with an image inside it.
    # AppleScript can't extract the shape's fill in many cases, so we render
    # the entire pair as a single raster crop. Mark both elements as skipped.
    skip_idx: set[int] = set()
    skip_idx.update(canvas_backdrop_idxs)
    used_via_raster_pair: set[int] = set()
    bbox_pair_crops: dict[int, str] = {}  # element idx → cropped png rel path

    if raster.available():
        for i, ei in enumerate(slide.elements):
            if ei.type != "shape" or ei.text.strip() or ei.has_fill:
                continue  # only consider EMPTY shapes
            for j, ej in enumerate(slide.elements):
                if j == i or j in skip_idx:
                    continue
                if ej.type != "image":
                    continue
                if _bbox_close(ei, ej):
                    fb = raster.crop(
                        slide.keynote_no, ei.x, ei.y, ei.w, ei.h,
                        slide_assets_dir / f"_pair-{i}.png",
                    )
                    if fb:
                        bbox_pair_crops[j] = f"{slide_assets_subdir}/{fb.name}"
                        skip_idx.add(i)
                        used_via_raster_pair.add(j)
                    break

    # Detect empty shapes for skip decision:
    #   · If the shape CONTAINS multiple other elements inside its bbox →
    #     it's a CONTAINER (banner/card background). Keep it for the
    #     shape-rendering branch's container heuristic to handle.
    #   · If the shape OVERLAPS with content but does NOT contain it (e.g.
    #     a tiny placeholder rectangle dropped on top of text) → skip; it's
    #     an invisible authoring placeholder.
    #   · If the shape has NO overlap with anything → also skip.
    def bbox_contains(a, b, min_overlap_ratio=0.70):
        """True iff at least `min_overlap_ratio` (default 70%) of b's bbox
        area falls inside a's bbox. Strict bbox-containment is too brittle:
        Keynote authors often have body text extending a few px past a
        banner shape's bottom; pure containment misses that case.
        """
        b_area = b.w * b.h
        if b_area <= 0:
            return False
        # intersection
        ix0, iy0 = max(a.x, b.x), max(a.y, b.y)
        ix1, iy1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
        if ix1 <= ix0 or iy1 <= iy0:
            return False
        inter_area = (ix1 - ix0) * (iy1 - iy0)
        return (inter_area / b_area) >= min_overlap_ratio

    def overlaps_without_containing(idx: int) -> bool:
        a = slide.elements[idx]
        contained = 0
        overlapping = 0
        for k, b in enumerate(slide.elements):
            if k == idx or b.type == "group":
                continue
            # check center-distance overlap
            if (abs((a.x + a.w/2) - (b.x + b.w/2)) < (a.w + b.w) / 2 - 4 and
                abs((a.y + a.h/2) - (b.y + b.h/2)) < (a.h + b.h) / 2 - 4):
                overlapping += 1
                if bbox_contains(a, b):
                    contained += 1
        # Overlaps with content but doesn't contain any of it → placeholder
        return overlapping > 0 and contained == 0

    for i, ei in enumerate(slide.elements):
        if i in skip_idx:
            continue
        if ei.type == "shape" and not ei.text.strip() and not ei.has_fill:
            # If the IWA archive paired a fill for this shape — especially a
            # named-path shape (arrows, callouts, ovals) — KEEP it; the
            # AppleScript "no fill" report is just incomplete, not a signal
            # to skip. Without this exception the p74 arrows were dropped
            # because they don't "contain" anything overlapping them.
            # If IWA paired ANY fill / gradient / stroke / named-shape to
            # this AppleScript shape, KEEP it. The "overlaps without
            # containing" filter was originally for invisible authoring
            # decorations — but those don't get IWA fills. Stripping it
            # caused p5's 11 small dots (which overlap the two big rings
            # without containing them) to be silently dropped.
            sf_pair = iwa_fill_for_idx.get(i)
            if sf_pair is not None:
                continue
            if overlaps_without_containing(i):
                skip_idx.add(i)

    for idx, el in enumerate(slide.elements):
        if idx in skip_idx or idx in suppressed_master:
            continue
        rot = _transform(el.rotation)
        op_css = f"opacity:{el.css_opacity:.3f} !important;" if el.is_translucent else ""

        # Shape+image pair already cropped from raster — emit that crop
        if idx in used_via_raster_pair:
            rel = bbox_pair_crops[idx]
            parts.append(
                f'<img class="el" src="{html_lib.escape(rel)}" '
                f'style="left:{el.x}px;top:{el.y}px;width:{el.w}px;height:{el.h}px;'
                f'object-fit:cover;{op_css}{rot}">'
            )
            continue

        if el.type == "image":
            # IWA-deterministic resolution, returning both file AND the
            # IWA's true bbox (when available). For non-master images,
            # AppleScript sometimes reports a CLIPPED bbox (the visible
            # region) which mis-renders the image via object-fit:cover —
            # e.g. slide 12's 邮政储蓄银行 logo (AppleScript 206×42,
            # natural image 624×53, IWA truth 380×32 fits perfectly).
            # If IWA gives us a wider/taller bbox, prefer it.
            iwa_bbox = None
            iwa_has_mask = False
            rb = resolver.resolve_with_bbox(
                slide.keynote_no, el.x, el.y, el.w, el.h, el.file_name, kind="image",
                is_master=el.is_master,
            )
            if rb is None:
                src = None
            else:
                src, iwa_bbox, iwa_has_mask = rb
            if src is None and not el.file_name:
                warnings.append(f"slide {slide.keynote_no} item {idx}: image with no file_name")
                continue
            if src is None:
                warnings.append(
                    f"slide {slide.keynote_no} item {idx}: could not resolve '{el.file_name}' "
                    f"({int(el.w)}×{int(el.h)})"
                )
                # try raster fallback
                if raster.available():
                    fb_path = raster.crop(
                        slide.keynote_no, el.x, el.y, el.w, el.h,
                        slide_assets_dir / f"_fallback-img-{idx}.png",
                    )
                    if fb_path:
                        rel = f"{slide_assets_subdir}/{fb_path.name}"
                        parts.append(
                            f'<img class="el" src="{html_lib.escape(rel)}" '
                            f'style="left:{el.x}px;top:{el.y}px;width:{el.w}px;'
                            f'height:{el.h}px;object-fit:cover;{rot}">'
                        )
                        continue
                parts.append(
                    f'<div class="el" style="left:{el.x}px;top:{el.y}px;width:{el.w}px;'
                    f'height:{el.h}px;outline:1px dashed #f08;color:#f08;font:14px monospace;'
                    f'padding:4px;background:rgba(255,0,128,.08);{rot}">'
                    f'missing image: {html_lib.escape(el.file_name)}</div>'
                )
                continue
            png_path = resolver.to_png(src, slide_assets_dir)
            rel = f"{slide_assets_subdir}/{png_path.name}"
            # Choose render bbox. AppleScript reports the actual display
            # bbox after any mask/crop Keynote has applied — for images
            # entirely within the canvas, that IS the correct bbox.
            # The only case AppleScript LIES is when the image overflows
            # the canvas: Keynote's PDF-export pipeline clips the bbox at
            # the canvas edge before reporting, and now `object-fit:cover`
            # at that smaller-than-real bbox shows the wrong pixel slice
            # (e.g. slide 5 master `up@2x.png` is a 2048×6456 tall texture
            # placed at y=-1081 in the template; AppleScript clips to
            # (-19,-53) 1958×2076 → object-fit shows the middle band of
            # the image, not the top band Keynote actually displays).
            # Detection: AppleScript bbox extends well beyond canvas. In
            # that case use IWA's true placement. .slide overflow:hidden
            # clips it correctly.
            # Bbox decision — kept simple to avoid the rabbit hole:
            #
            #   · Slide-level images: ALWAYS use AppleScript bbox. The IWA
            #     archive carries a `mask` field on virtually every image
            #     drawable (Keynote authors images with implicit unity
            #     masks, so mask presence doesn't reliably signal "the
            #     image is meaningfully cropped"). Trying to override
            #     based on aspect-mismatch with the natural file flips
            #     phone screenshots wrong-way-around. Leaving these on
            #     AppleScript matches what users see in Keynote present
            #     mode at the cost of minor side-cropping on a few wide
            #     logos (e.g. 邮政储蓄银行: object-fit:cover may shave a
            #     few px off each end — acceptable cosmetic drift).
            #
            #   · MASTER images: use IWA bbox ONLY when AppleScript bbox
            #     extends substantially off-canvas. That's the canonical
            #     "Keynote clipped its reported bbox at the canvas edge"
            #     signal — and the only case where IWA's true placement
            #     is observably necessary (e.g. slide 5 up@2x.png 2048×6456
            #     reported as 1958×2076 by AppleScript).
            SLIDE_W, SLIDE_H = 1920, 1080
            CANVAS_OVERFLOW_EPS = 8
            x_use, y_use, w_use, h_use = el.x, el.y, el.w, el.h
            if el.is_master and resolver.iwa_map is not None:
                overflows = (
                    el.x < -CANVAS_OVERFLOW_EPS or el.y < -CANVAS_OVERFLOW_EPS
                    or (el.x + el.w) > SLIDE_W + CANVAS_OVERFLOW_EPS
                    or (el.y + el.h) > SLIDE_H + CANVAS_OVERFLOW_EPS
                )
                if overflows:
                    tbb = resolver.iwa_map.master_bbox(slide.keynote_no, el.file_name)
                    if tbb is not None:
                        x_use, y_use, w_use, h_use = tbb
            # Slide-level images: when AppleScript reports a DEGENERATE bbox
            # (0×0 or essentially zero), fall back to IWA's true bbox if we
            # have one. This is the canonical signal that AppleScript failed
            # to introspect the geometry — typically because the image is
            # nested inside a Group archive and AppleScript reports child
            # geometry as 0×0 (the group's own bbox is correct, but its
            # children aren't traversed for absolute coords). This fix
            # restores p77's bedroom JPEG (full-bleed bg inside a group):
            # AppleScript said 0×0, IWA says (-19,-87,1950×1299).
            if (not el.is_master) and (el.w <= 1 or el.h <= 1) and iwa_bbox is not None:
                ix, iy, iw, ih = iwa_bbox
                if iw > 1 and ih > 1:
                    x_use, y_use, w_use, h_use = ix, iy, iw, ih
            # Pick object-fit based on natural-vs-render aspect comparison
            # (see _object_fit_for). cover for typical / portrait-cropped
            # images; contain when natural is much wider than container so
            # we don't side-crop wide logos.
            natural = resolver._intrinsic_size(src)
            if natural is not None:
                fit = _object_fit_for(natural[0], natural[1], w_use, h_use)
            else:
                fit = "cover"
            parts.append(
                f'<img class="el" src="{html_lib.escape(rel)}" '
                f'style="left:{x_use}px;top:{y_use}px;width:{w_use}px;height:{h_use}px;'
                f'object-fit:{fit};{op_css}{rot}">'
            )

        elif el.type == "movie":
            # IWA-first resolution — critical for movies, which AppleScript
            # sometimes reports with empty file_name (the legacy resolver
            # had no chance there).
            src = resolver.resolve_for_element(
                slide.keynote_no, el.x, el.y, el.w, el.h, el.file_name, kind="movie"
            )
            if src is None:
                # Movie has no resolvable file (AppleScript sometimes returns
                # empty `file name` for inserted movies). Fall back to raster
                # crop of the slide region so user at least sees the visual.
                if raster.available():
                    fb = raster.crop(
                        slide.keynote_no, el.x, el.y, el.w, el.h,
                        slide_assets_dir / f"_fallback-movie-{idx}.png",
                    )
                    if fb:
                        rel = f"{slide_assets_subdir}/{fb.name}"
                        warnings.append(
                            f"slide {slide.keynote_no} item {idx}: movie '{el.file_name}' "
                            f"unresolved, using raster crop"
                        )
                        parts.append(
                            f'<img class="el" src="{html_lib.escape(rel)}" '
                            f'style="left:{el.x}px;top:{el.y}px;width:{el.w}px;'
                            f'height:{el.h}px;object-fit:cover;{op_css}{rot}">'
                        )
                        continue
                warnings.append(
                    f"slide {slide.keynote_no} item {idx}: movie '{el.file_name}' unresolved"
                )
                continue
            slide_assets_dir.mkdir(parents=True, exist_ok=True)
            dst = slide_assets_dir / src.name
            if not dst.exists():
                shutil.copy(src, dst)
            rel = f"{slide_assets_subdir}/{src.name}"

            # Auto-generate a poster frame (first video frame) so the video
            # has something to show before autoplay starts — or when autoplay
            # is blocked (file:// URLs, some browser policies).
            poster_attr = ""
            try:
                import av  # PyAV — optional, but recommended for videos
                poster_path = slide_assets_dir / (src.stem + ".poster.jpg")
                if not poster_path.exists():
                    container = av.open(str(src))
                    for frame in container.decode(video=0):
                        frame.to_image().save(str(poster_path), quality=80)
                        break
                    container.close()
                poster_attr = f' poster="{html_lib.escape(slide_assets_subdir)}/{poster_path.name}"'
            except ImportError:
                pass  # av not installed — silently omit poster
            except Exception as e:
                warnings.append(
                    f"slide {slide.keynote_no} item {idx}: poster gen failed for {src.name}: {e}"
                )

            # IMPORTANT: do NOT set the `src` attribute up-front, and use
            # `preload="none"` — otherwise the browser greedily downloads /
            # decodes every <video> element across all 62 slides on page load,
            # which murders performance and makes navigation laggy. We use
            # `data-src` and rely on feishu-deck.js (see the inline patch
            # below) to swap in `src` only when the slide becomes current,
            # and pause + nuke `src` when it leaves view.
            parts.append(
                f'<video class="el lazy-video" data-src="{html_lib.escape(rel)}"{poster_attr} '
                f'style="left:{el.x}px;top:{el.y}px;width:{el.w}px;height:{el.h}px;'
                f'object-fit:cover;{op_css}{rot}" muted loop playsinline preload="none"></video>'
            )

        elif el.type == "shape":
            # A shape may have text, fill, both, or neither.
            has_text = bool(el.text.strip())
            has_fill_color = el.has_fill
            # text_inner gets either escaped text OR per-run <span>s when
            # the element has multi-run styling (see _render_text_runs).
            # default_color/size/font filled in below once we know them.
            text_inner = ""

            # Look up IWA fill paired with this shape's bbox. Many Keynote
            # shapes (pills with theme colors, decorative ovals, callout
            # backdrops) have their fill in a parent ShapeStyle that
            # AppleScript can't see — has_fill_color is False but the IWA
            # archive carries the real color/gradient. Use it as the
            # background AND signal "this shape is filled" for radius.
            iwa_sf = iwa_fill_for_idx.get(idx)

            # IMAGE FILL on a shape — a picture painted as a shape's fill
            # (not a standalone TSD.ImageArchive). p32's WriteSonic/Frase/
            # Jasper product screenshots are stored this way; without this
            # branch they're dropped (the shape has no color/gradient, so it
            # rendered as nothing). Resolve the fill's Data/ file, copy it,
            # and emit an <img> at the shape's bbox.
            if iwa_sf is not None and getattr(iwa_sf, "image_fill_filename", ""):
                fill_src = resolver.resolve(iwa_sf.image_fill_filename, el.w, el.h)
                if fill_src is not None:
                    png_path = resolver.to_png(fill_src, slide_assets_dir)
                    rel = f"{slide_assets_subdir}/{png_path.name}"
                    r_css = ""
                    if iwa_sf.corner_radius_frac and iwa_sf.corner_radius_frac > 0:
                        rr = min(iwa_sf.corner_radius_frac * el.h,
                                 min(el.w, el.h) / 2.0)
                        r_css = f"border-radius:{rr:.1f}px;"
                    parts.append(
                        f'<img class="el" src="{html_lib.escape(rel)}" '
                        f'style="left:{el.x}px;top:{el.y}px;width:{el.w}px;'
                        f'height:{el.h}px;object-fit:cover;{r_css}">'
                    )
                    continue

            # Bezier-path SVG render: when IWA gave us an explicit path
            # (custom Keynote shapes — not named pointPath types), emit
            # the path verbatim. Catches organic blobs, callouts, hand-
            # drawn shapes. Only applies when there's no text (text-bearing
            # bezier shapes still go through the div path so layout works).
            if (iwa_sf is not None and iwa_sf.bezier_path
                    and iwa_sf.bezier_path[0]
                    and not has_text):
                d_str, vb_x, vb_y, vb_w, vb_h = iwa_sf.bezier_path
                if vb_w <= 0 or vb_h <= 0:
                    # Degenerate path — skip the SVG branch, let the fallback
                    # rect path render the bbox.
                    pass
                else:
                    # Build fill — SVG-flavored, not CSS-flavored.
                    # SVG's `fill` attribute does NOT understand
                    # `linear-gradient(...)`. For curved shapes that need
                    # a gradient we emit a real <linearGradient> in <defs>
                    # and reference it via fill="url(#...)".
                    svg_defs = ""
                    if iwa_sf.gradient_css:
                        grad_id = f"g{abs(hash(iwa_sf.gradient_css)) & 0xffffff:x}_{idx}"
                        svg_defs = _css_gradient_to_svg_defs(iwa_sf.gradient_css, grad_id)
                        fill_css = f"url(#{grad_id})" if svg_defs else "rgba(0,0,0,0)"
                    elif iwa_sf.alpha < 0.001:
                        fill_css = "none"  # stroke-only
                    else:
                        fill_css = (f"rgba({iwa_sf.r},{iwa_sf.g},{iwa_sf.b},"
                                    f"{iwa_sf.alpha:.3f})")
                    stroke_attr = ""
                    if iwa_sf.stroke_color and iwa_sf.stroke_width > 0:
                        # Stroke is authored in Keynote pixels. The path is
                        # in normalized units (~100×100). Map by the path's
                        # viewBox-width vs the shape's display width.
                        scale = vb_w / max(el.w, 1)
                        sw = iwa_sf.stroke_width * scale
                        stroke_attr = (f' stroke="{iwa_sf.stroke_color}" '
                                       f'stroke-width="{sw:.2f}" '
                                       f'fill-rule="evenodd"')
                    angle = el.rotation if el.rotation else (iwa_sf.angle or 0)
                    rot_css = (f"transform:rotate({angle:.3f}deg);"
                               if abs(angle) > 0.01 else "")
                    # NOTE: a previous version put dark-gradient overlays at
                    # z-index:-1 (under their image) thinking the image was
                    # being hidden. That was wrong — Keynote authored these
                    # gradients DELIBERATELY on top, at ~86% alpha, to darken
                    # the photo so light text reads. With z:-1 the image
                    # showed bright and the text became invisible. We trust
                    # IWA's authored alpha and let document order govern Z.
                    parts.append(
                        f'<svg class="el" xmlns="http://www.w3.org/2000/svg" '
                        f'viewBox="{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}" '
                        f'preserveAspectRatio="none" '
                        f'style="position:absolute;left:{el.x}px;top:{el.y}px;'
                        f'width:{el.w}px;height:{el.h}px;{rot_css}">'
                        f'{svg_defs}<path d="{d_str}" fill="{fill_css}"{stroke_attr}/></svg>'
                    )
                    continue

            # Named-shape SVG render: if the IWA pathsource identifies this
            # shape as an arrow / star / callout / etc, draw the actual
            # geometry. Beats the previous behavior of a colored rect bbox
            # that made arrows look like squares (p74 Venn-diagram arrows).
            # Only takes effect when there's no text — text-bearing shapes
            # still need the div path so the text can flow naturally.
            if (iwa_sf is not None and iwa_sf.shape_kind
                    and iwa_sf.shape_kind in _NAMED_SHAPE_PATHS
                    and not has_text):
                if iwa_sf.gradient_css:
                    fill_css = iwa_sf.gradient_css
                else:
                    fill_css = (f"rgba({iwa_sf.r},{iwa_sf.g},{iwa_sf.b},"
                                f"{iwa_sf.alpha:.3f})")
                # Prefer AppleScript's rotation (authoritative for the
                # element we paired this fill to); fall back to IWA angle.
                angle = el.rotation if el.rotation else (iwa_sf.angle or 0)
                svg = _render_named_shape_svg(
                    iwa_sf.shape_kind, el.x, el.y, el.w, el.h,
                    fill_css, angle,
                )
                if svg:
                    parts.append(svg)
                    continue

            if has_fill_color or has_text or iwa_sf is not None:
                if has_fill_color:
                    bg_rgba = el.fill_color_rgba
                elif iwa_sf is not None:
                    if iwa_sf.gradient_css:
                        bg_rgba = iwa_sf.gradient_css
                    elif iwa_sf.alpha < 0.001:
                        # Stroke-only (sentinel alpha=0) → transparent center.
                        bg_rgba = "transparent"
                    else:
                        bg_rgba = (f"rgba({iwa_sf.r},{iwa_sf.g},{iwa_sf.b},"
                                   f"{iwa_sf.alpha:.3f})")
                else:
                    bg_rgba = "transparent"

                # Stroke (border) from IWA ShapeStyle. Common for ring
                # circles (p5's big rings) and outlined boxes — these have
                # no fill but a thick colored border.
                border_css = ""
                if (iwa_sf is not None and iwa_sf.stroke_color
                        and iwa_sf.stroke_width > 0):
                    style = iwa_sf.stroke_dash or "solid"
                    border_css = (f"border:{iwa_sf.stroke_width:.1f}px "
                                  f"{style} {iwa_sf.stroke_color}")

                # Corner radius heuristic. Applied whenever there's a real
                # fill (AppleScript OR IWA). Skip for translucent overlays
                # (full-bleed masks shouldn't get rounded edges).
                radius_css = ""
                has_any_fill = has_fill_color or iwa_sf is not None
                # Skip radius for full-bleed translucent OVERLAYS only (large
                # masking rectangles). Small translucent shapes — p5's blue
                # ring dots at 68% opacity — still need their corner radius.
                is_overlay_mask = (el.is_translucent
                                   and (el.w > 1500 or el.h > 800))
                if has_any_fill and not is_overlay_mask:
                    sk = ((iwa_sf.shape_kind or "") if iwa_sf is not None else "")
                    frac = (iwa_sf.corner_radius_frac if iwa_sf is not None else 0.0)
                    if frac and frac > 0:
                        # REAL rounded-rect radius from IWA (Keynote's
                        # scalarPathSource.scalar, stored as a fraction of the
                        # shape's natural height). Scale to the rendered height,
                        # clamp to a true pill at most. This replaces the old
                        # "pill if short, else 16/24px box" guess that gave the
                        # same table different corner radii per cell.
                        r = min(frac * el.h, min(el.w, el.h) / 2.0)
                        radius_css = f"border-radius:{r:.1f}px"
                    elif "Oval" in sk:
                        # Keynote oval/ellipse → real circle/ellipse.
                        radius_css = "border-radius:50%"
                    elif iwa_sf is None:
                        # AppleScript-only fill (no IWA shape data to read a
                        # real radius from). Keep ONLY the square→circle guess;
                        # the old pill/card/16px guesses are dropped — they were
                        # the source of the inconsistent corner radii.
                        ratio = el.w / el.h if el.h else 1
                        if 0.95 < ratio < 1.05 and el.h > 30:
                            radius_css = "border-radius:50%"
                    # else: IWA-known shape that is neither rounded-rect nor oval
                    # → sharp corners (faithful to Keynote plain rectangles).

                style_parts = [
                    f"left:{el.x}px", f"top:{el.y}px",
                    f"width:{el.w}px", f"min-height:{el.h}px",
                    f"background:{bg_rgba}",
                    radius_css if radius_css else None,
                    border_css if border_css else None,
                ]
                if has_text:
                    weight, fstyle = parse_font_weight_style(el.font)
                    text_color = el.text_color_hex
                    fs_authored = el.font_size or 24
                    is_multirun = len(el.runs) >= 2
                    # Multi-run text uses authored per-run sizes; don't try to
                    # shrink-to-fit using the first run's size (would miscalculate
                    # for mixed-size content).
                    fs = fs_authored if is_multirun else fit_font_to_box(
                        el.text, el.w, el.h, fs_authored)
                    font_stack = text_font_stack(el.font)
                    text_inner = _render_text_runs(el, default_color=text_color,
                                                    default_font=el.font, default_size=fs)
                    # Alignment: source-of-truth is the IWA paragraph style
                    # (TSWP.ParagraphStyleArchive.paraProperties.alignment).
                    # Fall back to bbox-center heuristic if the lookup misses
                    # (rare — typically when the text shape is purely on the
                    # master/template, which we don't index).
                    # IWA paragraph style → text-align (no more bbox-centre
                    # guess). Keynote's default for unstyled text is left.
                    ta = (resolver.text_align_for_element(
                              slide.keynote_no, el.x, el.y, el.w, el.h)
                          or "left")
                    # Authored line spacing. iwa_resolver encodes:
                    #   > 0  → multiplier (default kRelativeLineSpacing)
                    #   < 0  → -points (kExactLineSpacing → absolute pt)
                    #   = 0  → not set; use 1.35 default
                    raw_lh = resolver.text_line_height_for_element(
                        slide.keynote_no, el.x, el.y, el.w, el.h)
                    if raw_lh < 0:
                        lh_css = f"line-height:{-raw_lh:.1f}px"
                    else:
                        lh_css = f"line-height:{(raw_lh or 1.35):.2f}"
                    base_style = [
                        f"color:{text_color}",
                        f"font-family:{font_stack}",
                        f"font-size:{fs:.1f}px",
                        f"font-weight:{weight}",
                        f"font-style:{fstyle}",
                        lh_css,
                        "padding:8px 16px",
                        f"text-align:{ta}",
                    ]
                    if is_multirun:
                        # Block layout — let <span>s flow as inline text so
                        # \n→<br> creates lines and multi-style segments stay
                        # on the same line. Vertical centering via padding
                        # rather than flex (flex breaks <span> inline flow).
                        style_parts += base_style + [
                            "display:block",
                            # Approximate vertical centering by adjusting top
                            # padding when shape box is taller than text.
                            # (Flex would re-flow spans as items.)
                        ]
                    else:
                        # Single-run text — flex is fine and gives clean
                        # vertical centering of a single line.
                        align_items_v = "center"
                        # Map Keynote text-align to flex justify-content. Keynote
                        # also exports "justify" (full-justify) which has no flex
                        # equivalent — degrade to flex-start (left). The text-align
                        # CSS property is set separately so the actual visual
                        # justify still applies to the text run.
                        justify = {"left":"flex-start", "center":"center",
                                   "right":"flex-end",
                                   "justify":"flex-start"}.get(ta, "flex-start")
                        style_parts += base_style + [
                            "display:flex",
                            f"align-items:{align_items_v}",
                            f"justify-content:{justify}",
                        ]
                # Element-level opacity is only needed when the shape has TEXT and is
                # translucent (because rgba bg already handles fill alpha; but text
                # color would stay opaque). For fill-only translucent overlays, rgba
                # alone is sufficient and we leave `opacity:1` so text inside other
                # overlapping divs isn't affected.
                if el.is_translucent and has_text:
                    style_parts.append(f"opacity:{el.css_opacity:.3f} !important")

                style = ";".join(p for p in style_parts if p) + ";" + rot.strip()
                parts.append(
                    f'<div class="el shape"{_role_attr(el)} style="{style}">{text_inner}</div>'
                )
            else:
                # No fill, no text from AppleScript. If IWA reports a fill
                # for this shape's bbox, emit it RIGHT HERE so source draw
                # order is preserved (the shape may sit BELOW a video — see
                # slide 18 where the black backdrop sits under a 42%-opaque
                # video). Otherwise it's a truly invisible authoring node.
                sf = iwa_fill_for_idx.get(idx)
                if sf is not None:
                    parts.append(_emit_iwa_fill_div(sf, in_place=True))
                else:
                    warnings.append(f"slide {slide.keynote_no} item {idx}: shape no fill/text — skipped")

        elif el.type == "text":
            if not el.text.strip():
                continue
            # IWA paragraph style → text-align. No bbox-centre guess.
            ta = (resolver.text_align_for_element(
                      slide.keynote_no, el.x, el.y, el.w, el.h)
                  or "left")
            # Authored line spacing — encoded by iwa_resolver:
            #   > 0 = multiplier, < 0 = -px (exact), 0 = unset.
            raw_lh = resolver.text_line_height_for_element(
                slide.keynote_no, el.x, el.y, el.w, el.h)
            if raw_lh < 0:
                lh_css = f"line-height:{-raw_lh:.1f}px"
                lh = 1.4  # for fit_font_to_box (multiplier expected)
            else:
                lh = raw_lh or 1.4
                lh_css = f"line-height:{lh:.2f}"
            # Container styling uses the FIRST run's font/size as the default.
            # When el.runs has multiple entries, individual <span>s override.
            font_stack = text_font_stack(el.font)
            text_color = el.text_color_hex
            size_authored = el.font_size or 24
            size = fit_font_to_box(el.text, el.w, el.h, size_authored, line_height=lh)
            weight, fstyle = parse_font_weight_style(el.font)
            inner = _render_text_runs(el, default_color=text_color,
                                       default_font=el.font, default_size=size)
            parts.append(
                f'<div class="el"{_role_attr(el)} style="left:{el.x}px;top:{el.y}px;width:{el.w}px;'
                f'min-height:{el.h}px;color:{text_color};'
                f'font-family:{font_stack};font-size:{size:.1f}px;'
                f'font-weight:{weight};font-style:{fstyle};{lh_css};'
                f'text-align:{ta};{op_css}{rot}">'
                f'{inner}</div>'
            )

        else:
            # Horizontal / vertical LINES (other:line) — Keynote authors them as
            # zero-height (h=0) or zero-width separators. They can't be raster-
            # cropped (invalid crop region) but they're visually a 1-2px hairline.
            # Render as a thin div with a semi-transparent border. Catches the
            # divider lines used under card titles on slide 24, the section
            # underlines on slide 12 / 30 / 42, etc.
            if el.type == "other:line" and (el.h < 2 or el.w < 2):
                # horizontal hairline (h=0) or vertical hairline (w=0)
                line_color = "rgba(255,255,255,0.35)"
                if el.h < 2:
                    parts.append(
                        f'<div class="el" style="left:{el.x}px;top:{el.y - 1}px;'
                        f'width:{el.w}px;height:2px;background:{line_color};{rot}"></div>'
                    )
                else:
                    parts.append(
                        f'<div class="el" style="left:{el.x - 1}px;top:{el.y}px;'
                        f'width:2px;height:{el.h}px;background:{line_color};{rot}"></div>'
                    )
                continue

            # TABLE: reconstruct HTML <table> from CELL records emitted by
            # extract.applescript. Per-cell widths/heights + per-cell font,
            # color, and background are honored.
            if el.type == "table" and el.cells:
                max_row = max(c["row"] for c in el.cells)
                max_col = max(c["col"] for c in el.cells)
                grid: dict[tuple[int,int], dict] = {}
                col_w: dict[int, float] = {}
                row_h: dict[int, float] = {}
                for c in el.cells:
                    grid[(c["row"], c["col"])] = c
                    col_w[c["col"]] = c["w"]
                    row_h[c["row"]] = c["h"]

                def _cell_style(c: dict, cw: float, rh: float) -> str:
                    """Per-cell inline style. Reads font/size/text-color and
                    optional fill from the CELL record (Keynote AppleScript
                    surfaces these when present)."""
                    bits = [
                        f"width:{cw:.1f}px",
                        f"height:{rh:.1f}px",
                        "padding:6px 10px",
                        # Default light gray border; Keynote AS doesn't
                        # surface per-cell borders, but a 1px gray is closer
                        # to typical table chrome than no border.
                        "border:1px solid rgba(0,0,0,0.22)",
                        "vertical-align:middle",
                    ]
                    if c.get("font"):
                        bits.append(f"font-family:{text_font_stack(c['font'])}")
                    if c.get("size"):
                        bits.append(f"font-size:{float(c['size']):.1f}px")
                    # Text color (always emit when r,g,b are present — even
                    # for pure black we want to be explicit since the
                    # surrounding font/bg might inherit something else).
                    if any(c.get(k, 0) for k in ("r", "g", "b")) or c.get("r") == 0:
                        if "r" in c:
                            bits.append(f"color:{_kn_rgb_to_hex(c['r'], c['g'], c['b'])}")
                    # Fill: -1 means AppleScript didn't surface it.
                    if c.get("fill_r", -1) >= 0:
                        bits.append("background:" + _kn_rgb_to_hex(
                            c["fill_r"], c["fill_g"], c["fill_b"]))
                    return ";".join(bits)

                rows_html: list[str] = []
                for r in range(1, max_row + 1):
                    cells_html: list[str] = []
                    rh = row_h.get(r, 0) or 0
                    for cc in range(1, max_col + 1):
                        c = grid.get((r, cc))
                        text = html_lib.escape(c["text"]) if c else ""
                        cw = col_w.get(cc, 0) or 0
                        if c:
                            cells_html.append(
                                f'<td style="{_cell_style(c, cw, rh)}">{text}</td>'
                            )
                        else:
                            cells_html.append(
                                f'<td style="width:{cw:.1f}px;height:{rh:.1f}px;'
                                f'border:1px solid rgba(0,0,0,0.22);"></td>'
                            )
                    rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
                tbl = (
                    f'<table style="border-collapse:collapse;'
                    f"font-family:'PingFang SC','Microsoft YaHei',"
                    f"'Helvetica Neue','Arial',sans-serif;"
                    f'font-size:{(el.font_size or 16):.1f}px;'
                    f'color:{el.text_color_hex};">'
                    f'{"".join(rows_html)}</table>'
                )
                parts.append(
                    f'<div class="el" style="left:{el.x}px;top:{el.y}px;'
                    f'width:{el.w}px;height:{el.h}px;{rot}">{tbl}</div>'
                )
                continue

            # CHART: render as SVG bar chart from extracted series data.
            # Best-effort — AppleScript's chart introspection is limited,
            # so points may be partial. Better than a blank.
            if el.type == "chart" and el.chart and el.chart.get("series"):
                ch = el.chart
                series = ch.get("series", [])
                cats = ch.get("categories", [])
                points = ch.get("points", [])
                if cats and points and any(p for p in points):
                    # SVG bars. Each category = a group; series stacked horizontally.
                    pad = 30
                    chart_w = max(100.0, el.w - 2 * pad)
                    chart_h = max(60.0, el.h - 2 * pad - 24)  # leave 24 for axis labels
                    n_cats = len(cats)
                    n_series = len(series)
                    # Normalize values
                    all_vals = [v for sp in points for v in sp if isinstance(v, (int, float))]
                    if not all_vals:
                        all_vals = [0]
                    vmax = max(all_vals) or 1.0
                    palette = ["#3C7FFF", "#33D6C0", "#9F6FF1", "#FF8A4C",
                               "#22B573", "#E75A7C"]
                    group_w = chart_w / max(n_cats, 1)
                    bar_w = group_w / max(n_series, 1) * 0.8
                    bars: list[str] = []
                    for si, sp in enumerate(points):
                        col = palette[si % len(palette)]
                        for ci, v in enumerate(sp):
                            if not isinstance(v, (int, float)): continue
                            bh = (v / vmax) * chart_h if vmax > 0 else 0
                            bx = pad + ci * group_w + si * bar_w + (group_w - n_series * bar_w) / 2
                            by = pad + chart_h - bh
                            bars.append(
                                f'<rect x="{bx:.1f}" y="{by:.1f}" '
                                f'width="{bar_w:.1f}" height="{bh:.1f}" '
                                f'fill="{col}" rx="2"/>'
                            )
                    # X-axis labels
                    labels = []
                    for ci, cat in enumerate(cats):
                        lx = pad + ci * group_w + group_w / 2
                        ly = pad + chart_h + 16
                        labels.append(
                            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12" '
                            f'fill="#444" text-anchor="middle" '
                            f'font-family="PingFang SC,sans-serif">'
                            f'{html_lib.escape(str(cat))}</text>'
                        )
                    # Y-axis baseline
                    axis = (f'<line x1="{pad}" y1="{pad}" x2="{pad}" '
                            f'y2="{pad+chart_h}" stroke="#bbb"/>'
                            f'<line x1="{pad}" y1="{pad+chart_h}" '
                            f'x2="{pad+chart_w}" y2="{pad+chart_h}" stroke="#bbb"/>')
                    parts.append(
                        f'<svg class="el" xmlns="http://www.w3.org/2000/svg" '
                        f'viewBox="0 0 {el.w:.0f} {el.h:.0f}" '
                        f'style="position:absolute;left:{el.x}px;top:{el.y}px;'
                        f'width:{el.w}px;height:{el.h}px;{rot}">'
                        f'{axis}{"".join(bars)}{"".join(labels)}</svg>'
                    )
                    continue

            # Other unsupported types (chart / table / other:*): raster fallback
            if raster.available():
                fb_path = raster.crop(
                    slide.keynote_no, el.x, el.y, el.w, el.h,
                    slide_assets_dir / f"_fallback-{el.type.replace(':','-')}-{idx}.png",
                )
                if fb_path:
                    rel = f"{slide_assets_subdir}/{fb_path.name}"
                    parts.append(
                        f'<img class="el" src="{html_lib.escape(rel)}" '
                        f'style="left:{el.x}px;top:{el.y}px;width:{el.w}px;'
                        f'height:{el.h}px;object-fit:cover;{rot}">'
                    )
                    continue
            warnings.append(
                f"slide {slide.keynote_no} item {idx}: unsupported type '{el.type}' "
                f"({int(el.w)}×{int(el.h)})"
            )

    # IWA-sourced shape backdrops. AppleScript reports `fill=none` for shapes
    # whose color comes from a parent ShapeStyle (translucent black masks,
    # card backdrops, banner pills — all driven by style inheritance). We
    # pull these from the IWA archive and render them here. z-index: 5 puts
    # them ABOVE images/videos (default z-auto) but BELOW text/text-shapes
    # (which we bump to z-index: 10 below).
    # End-of-slide pass: any IWA fills that DIDN'T match an AppleScript
    # shape (typically slides where AppleScript reported the body shape as
    # a tiny placeholder text stub — slides 20-23's 60% black mask is the
    # canonical case). Render with z-index:5 so they layer above raw
    # images/videos but below text. Matched fills were already emitted
    # in source-order position.
    for fi, sf in enumerate(iwa_fills):
        if fi in iwa_consumed:
            continue
        parts.append(_emit_iwa_fill_div(sf, in_place=False))

    return "\n".join(parts), warnings


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", type=Path)
    ap.add_argument("key_bundle", type=Path,
                    help="Path to the .key bundle (directory containing Data/, Index.zip)")
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--limit", type=int, default=0,
                    help="Build only the first N non-skipped slides.")
    ap.add_argument("--slides", type=str, default="",
                    help="Comma-separated 1-based slide numbers / ranges to "
                         "build (e.g. '1,3,5-8,12'). Numbers refer to the "
                         "keynote_no field (= position in the source deck, "
                         "skipped slides excluded). When set, --limit is "
                         "ignored. Use this after the user reviews the "
                         "extract-time slide list and picks what to convert.")
    # Renderer skill — points to the feishu-deck-h5 skill (or a compatible
    # fork). Used to produce the final HTML from deck.json. Kept as a flag
    # so this skill stays decoupled from any specific renderer.
    ap.add_argument("--renderer", type=Path,
                    default=Path(__file__).resolve().parents[2] / "feishu-deck-h5",
                    help="Path to renderer skill root (default: ../feishu-deck-h5/). "
                         "Decoupled so this skill can render against any compatible renderer.")
    ap.add_argument("--redesigns", type=Path, default=None,
                    help="Directory with per-slide HTML overrides "
                         "(slide-NN.html where NN is 1-based PDF page number). "
                         "When present, the file's HTML replaces auto-extracted "
                         "elements for that slide. Use for layouts that don't "
                         "map cleanly from Keynote (heavy tables, custom grids).")
    ap.add_argument("--rasters-dir", type=Path, default=None,
                    help="Directory with per-page PNGs (slide-NN.png) for fallback crops")
    ap.add_argument("--pdf", type=Path, default=None,
                    help="Source PDF for fallback rasterization (alternative to --rasters-dir)")
    args = ap.parse_args()

    if not args.tsv.is_file():
        print(f"ERROR: TSV not found: {args.tsv}", file=sys.stderr)
        return 1

    # Keynote 14.5+ can save `.key` as either a directory bundle (older default)
    # OR as a single zip file (newer default). Handle both. For zip form, extract
    # Data/ entries to <output>/.cache/Data/ once and reuse on subsequent runs.
    data_dir = args.key_bundle / "Data"
    if not data_dir.is_dir():
        import zipfile, shutil as _shutil
        if args.key_bundle.is_file() and zipfile.is_zipfile(args.key_bundle):
            cache_data = args.output_dir / ".cache" / "Data"
            if not cache_data.is_dir() or not any(cache_data.iterdir()):
                cache_data.mkdir(parents=True, exist_ok=True)
                print(f"==> extracting Data/ from zipped .key to {cache_data}/...")
                with zipfile.ZipFile(args.key_bundle) as zf:
                    for info in zf.infolist():
                        # FIX: Keynote stores UTF-8 filenames without setting the
                        # UTF-8 flag bit (0x800), so zipfile defaults to CP437
                        # decode → mojibake for Chinese names. Recode if needed.
                        raw_name = info.filename
                        if not (info.flag_bits & 0x800):
                            try:
                                raw_name = raw_name.encode("cp437").decode("utf-8")
                            except (UnicodeDecodeError, UnicodeEncodeError):
                                pass  # not recodable; keep as-is
                        if info.is_dir() or not raw_name.startswith("Data/"):
                            continue
                        name = Path(raw_name).name
                        if not name or name.startswith("."):
                            continue
                        target = cache_data / name
                        with zf.open(info) as src, open(target, "wb") as dst:
                            _shutil.copyfileobj(src, dst)
                print(f"    extracted {len(list(cache_data.iterdir()))} files")
            data_dir = cache_data
        else:
            print(f"ERROR: not a .key bundle (no Data/) and not a .key zip: {args.key_bundle}", file=sys.stderr)
            return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"==> parsing TSV: {args.tsv}")
    total, slides, src_w, src_h = parse_tsv(args.tsv)
    non_skipped = [s for s in slides if not s.skipped]
    print(f"    total slides: {total}  ·  non-skipped: {len(non_skipped)}")

    if args.slides:
        # Parse "1,3,5-8,12" → {1,3,5,6,7,8,12}
        wanted: set[int] = set()
        for part in args.slides.split(","):
            part = part.strip()
            if not part: continue
            if "-" in part:
                a, b = part.split("-", 1)
                wanted.update(range(int(a), int(b) + 1))
            else:
                wanted.add(int(part))
        non_skipped = [s for s in non_skipped if s.keynote_no in wanted]
        missing = sorted(wanted - {s.keynote_no for s in non_skipped})
        if missing:
            print(f"    warning: --slides asked for {missing} but those "
                  f"don't exist (or are marked skipped)", file=sys.stderr)
        print(f"    --slides filter: building {len(non_skipped)} slides "
              f"(keynote_no in {sorted(s.keynote_no for s in non_skipped)})")
    elif args.limit:
        non_skipped = non_skipped[: args.limit]
        print(f"    limit: building first {len(non_skipped)} slides")

    # Build IWA-derived per-slide asset map from the .key bundle. This is
    # the deterministic ground truth for image/movie resolution — used by
    # resolver.resolve_for_element. Heuristic fallback still kicks in if a
    # bbox match misses or keynote-parser isn't installed.
    iwa_map = None
    if _IWA_AVAILABLE:
        try:
            iwa_map = IWAAssetMap.from_key(args.key_bundle)
            n_assets = sum(len(iwa_map.assets_for_slide(s)) for s in range(1, 200))
            print(f"    IWA asset map: {n_assets} image/movie refs across slides")
            # IWA bboxes come in source-canvas coords (e.g. 0–960 for a
            # 960×540 .key). Element coords from parse_tsv have already
            # been scaled to 1920×1080. Bring the IWA fixtures into the
            # same coordinate space so bbox matching works.
            if abs(src_w - 1920.0) > 0.5 or abs(src_h - 1080.0) > 0.5:
                sx = 1920.0 / src_w
                sy = 1080.0 / src_h
                for a in iwa_map._assets:
                    a.x *= sx; a.y *= sy; a.w *= sx; a.h *= sy
                for fills in iwa_map._fills_by_slide.values():
                    for sf in fills:
                        sf.x *= sx; sf.y *= sy; sf.w *= sx; sf.h *= sy
                for ta_list in iwa_map._aligns_by_slide.values():
                    for ta in ta_list:
                        ta.x *= sx; ta.y *= sy; ta.w *= sx; ta.h *= sy
                # master_bboxes: dict[(slide_no, fn)] → (x, y, w, h)
                iwa_map._master_bbox = {
                    k: (v[0]*sx, v[1]*sy, v[2]*sx, v[3]*sy)
                    for k, v in iwa_map._master_bbox.items()
                }
        except Exception as e:
            print(f"    IWA asset map: build failed ({e}); falling back to heuristic only")
    else:
        print(f"    IWA asset map: keynote-parser not installed; heuristic-only resolution")

    resolver = AssetResolver(data_dir, args.output_dir / "assets", iwa_map=iwa_map)
    raster = RasterFallback(
        rasters_dir=args.rasters_dir,
        pdf_path=args.pdf,
        slides_with_kn_no=[s.keynote_no for s in non_skipped],
    )
    if raster.available():
        src_kind = "rasters-dir" if args.rasters_dir else "pdf"
        print(f"    raster fallback: {src_kind} available")
    else:
        print(f"    raster fallback: none (unhandled elements will show placeholders)")

    deck_slides = []
    all_warnings: list[str] = []

    # Optional per-slide HTML overrides — for layouts that don't map cleanly
    # from Keynote (heavy tables, custom grids, side-by-side phones). Each file
    # in --redesigns is `slide-NN.html` (NN = 1-based PDF page number); its
    # contents replace the auto-extracted slide body entirely.
    redesigns_dir = args.redesigns
    if redesigns_dir and redesigns_dir.is_dir():
        n_redesigns = sum(1 for f in redesigns_dir.glob("slide-*.html"))
        print(f"    redesigns: {n_redesigns} override(s) available in {redesigns_dir}")
    elif redesigns_dir:
        print(f"    redesigns: dir not found, ignoring: {redesigns_dir}")

    for i, slide in enumerate(non_skipped, start=1):
        sub = f"assets/slide-{slide.keynote_no:03d}"
        slide_assets_dir = args.output_dir / sub

        # Redesign override? Two filename conventions are accepted:
        #   · `slide-NN.html`  (2-digit) — matches by PDF page index (1..62)
        #   · `slide-NNN.html` (3-digit, zero-padded) — matches by the
        #     underlying Keynote slide number (slide.keynote_no, includes
        #     skipped slides; matches the deck.json `key`). Useful when
        #     re-ordering / hiding slides shouldn't break a redesign.
        # PDF-index form wins if both exist (more specific to current render).
        override_html = None
        override_label = ""
        if redesigns_dir:
            for cand_name in (f"slide-{i:02d}.html",
                              f"slide-{slide.keynote_no:03d}.html"):
                cand = redesigns_dir / cand_name
                if cand.is_file():
                    override_html = cand.read_text(encoding="utf-8")
                    override_label = cand_name
                    break

        # IMPORTANT: pick_title mutates the chosen element's data_role
        # field — it MUST run before compose_slide_html so the renderer
        # emits the `data-role="title"` attribute. See plugin/_spec/
        # deck-json-v2.md.
        slide_title = pick_title(slide)

        if override_html is not None:
            html_body, redesign_warns = _localize_redesign_assets(
                override_html, redesigns_dir, slide_assets_dir, sub
            )
            all_warnings.extend(redesign_warns)
            warns_count = len(redesign_warns)
            label = f"REDESIGN {override_label}"
        else:
            html_body, warns = compose_slide_html(slide, resolver, raster, sub, slide_assets_dir)
            all_warnings.extend(warns)
            warns_count = len(warns)
            label = f"keynote-slide {slide.keynote_no:2d}  ·  {len(slide.elements)} elements"

        deck_slides.append({
            "key": f"slide-{slide.keynote_no:03d}",
            "title": slide_title,             # v2: first-class title field
            "notes": "",
            "layout": "raw",
            "screen_label": f"{i:02d}",
            "data": {"html": html_body},
        })
        print(f"  · pdf-page {i:2d}  ←  {label}"
              + (f"  ⚠ {warns_count}" if warns_count else ""))

    # Title preference order (most → least authoritative):
    #   1. The .key file's basename (without extension) — matches the deck
    #      the user actually picked, no matter where they're building to.
    #   2. output_dir.parent.name — works for the canonical
    #      imports/<deck-name>/render-output-full/ layout.
    #   3. output_dir.name — last resort.
    # Previous behavior used (2) only, which produced silly titles like
    # "tmp" when building to /tmp/something for a verification pass.
    if args.key_bundle and args.key_bundle.name:
        deck_title = args.key_bundle.stem
    elif args.output_dir.parent.name and args.output_dir.parent.name not in (
        "tmp", "private", "var"
    ):
        deck_title = args.output_dir.parent.name
    else:
        deck_title = args.output_dir.name
    deck = {
        "version": "2",                      # see plugin/_spec/deck-json-v2.md
        "deck": {
            "title": deck_title,
            "language": "zh-only",
            "mode": "rewrite",
            "layout_pack": "feishu-deck-h5",
        },
        "slides": deck_slides,
    }
    deck_path = args.output_dir / "deck.json"
    deck_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2))
    print(f"\n==> wrote deck.json with {len(deck_slides)} slides")

    if all_warnings:
        warnings_path = args.output_dir / "warnings.txt"
        warnings_path.write_text("\n".join(all_warnings))
        print(f"    ⚠ {len(all_warnings)} warnings → {warnings_path.name}")

    # Render via the player dispatcher (plugin/_player/render.py). It reads
    # `deck.layout_pack` from deck.json and invokes the appropriate pack's
    # render entry. This decouples the importer from any specific pack —
    # changing layout_pack in deck.json + re-running the player switches
    # the look without touching this skill.
    player_script = Path(__file__).resolve().parents[3] / "_player" / "render.py"
    if player_script.is_file():
        render_script = player_script
        print(f"\n==> rendering via plugin/_player/render.py")
    else:
        # Back-compat: fall through to the pack's render entry directly.
        render_script = args.renderer / "deck-json/render-deck.py"
        if not render_script.is_file():
            print(f"ERROR: render-deck.py not at {render_script}", file=sys.stderr)
            return 1
        print(f"\n==> rendering via {args.renderer.name}/render-deck.py "
              f"(player dispatcher not found)")
    cmd = [
        sys.executable, str(render_script),
        str(deck_path), str(args.output_dir),
        "--skip-validate-html", "--skip-texts", "--skip-copy-assets",
        # build.py already composed the final, correct title text INTO the raw
        # HTML. Letting render-deck.py re-sync slides[].title back over the
        # data-role="title" element is at best a no-op and at worst destructive:
        # pick_title can mark a multi-paragraph block as the title and truncate
        # slides[].title to its first line, so the sync would replace the whole
        # block's body with that one line (nuked 10/73 slides on the 海正 deck).
        "--skip-raw-title-sync",
        # We re-localize the HTML's renderer refs ourselves below — the
        # renderer's own copy-assets.py is feishu-deck-h5-specific (hardcoded
        # `skills/feishu-deck-h5/` regex + requires `runs/<ts>/output/`
        # layout) so it does nothing for our `feishu-deck-h5` fork OR for
        # our `imports/.../render-output-full/` layout. Our localizer is
        # smaller and just-works.
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("RENDER FAILED:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return 1

    for line in (result.stdout.strip().splitlines() or [""])[-5:]:
        print(f"    {line}")

    # Localize the renderer's CSS/JS refs. After render-deck.py finishes,
    # index.html contains <link>/<script> URLs like
    #   ../../../plugin/skills/feishu-deck-h5/assets/feishu-deck.css
    # which only resolve when serving from above the skill root — they break
    # the moment you serve from the output dir (paths escape the server
    # root → 404 → all slides stack unstyled, JS doesn't run, no nav).
    # Copy each referenced renderer file into <output>/_renderer/ and
    # rewrite the HTML to use that local path. Result: output dir is
    # self-contained and `bash serve.sh` Just Works.
    _localize_renderer_refs(args.output_dir / "index.html",
                             args.output_dir / "_renderer",
                             args.renderer)

    # Drop a one-line `serve.sh` next to index.html. Browsers (esp. Chrome)
    # impose extra restrictions on file:// — CORS, certain SVG references,
    # cache aggressiveness — that don't show under http://. The serve script
    # gives a deterministic "double-click to view" path.
    serve_path = args.output_dir / "serve.sh"
    serve_path.write_text(
        '#!/usr/bin/env bash\n'
        '# Serve this deck on localhost:8765 so the browser uses http:// not file://.\n'
        '# (file:// has CORS/SVG/cache quirks that don\'t show under http://.)\n'
        'set -e\n'
        'cd "$(dirname "$0")"\n'
        'PORT="${1:-8765}"\n'
        'echo "==> serving on http://localhost:$PORT/index.html"\n'
        'python3 -m http.server "$PORT"\n'
    )
    serve_path.chmod(0o755)

    # Sweep orphan assets + the unzipped .key cache. Both are byproducts
    # of the build pipeline that don't need to ship: the deck must be
    # self-contained under <output>/ but every byte should be referenced.
    _sweep_orphans(args.output_dir, deck)

    # Append a history record so anyone looking at this output dir can see
    # which skill / version produced it. See plugin/_lib/history.py.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from _lib import history  # type: ignore
        history.append(
            args.output_dir,
            skill="keynote-to-html",
            version="0.17",
            input=str(args.key_bundle),
            slide_count=len(deck_slides),
            warnings=len(all_warnings),
        )
    except Exception as e:
        print(f"  (could not append history.json: {e})", file=sys.stderr)

    print(f"\n==> DONE  →  {args.output_dir / 'index.html'}")
    print(f"          or  bash {serve_path}  (recommended — avoids file:// quirks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
