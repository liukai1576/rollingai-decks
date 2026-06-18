"""iwa_resolver.py — deterministic per-slide asset map from a .key bundle.

Why this exists
---------------
AppleScript reports image/movie elements with only a `file name` basename
(e.g. "已粘贴的图像.png", or sometimes empty). Multiple Data/ files can
match that stem after suffix stripping, and our prior AssetResolver had to
guess between them by aspect/size. That guessing was wrong on slides where
two images shared the same base name but lived at different bbox positions
(e.g. slide PDF-page 45 was picking 10793.png when the right answer was
已粘贴的图像-9115.png).

The .key bundle itself has the ground truth. Each `Index/Slide-<id>.iwa`
lists its drawables; image/movie drawables reference a numeric data-id;
`Index/Metadata.iwa` maps data-id → on-disk filename. We follow this chain
and key the result by (slide_no_1based, bbox) so the resolver in build.py
can look up the exact filename without guessing.

Usage
-----
    m = IWAAssetMap.from_key(Path("foo.key"))
    fname = m.lookup(slide_no=45, x=-7.6, y=6.5, w=1935, h=1097)
    # → "已粘贴的图像-9115.png" or None

slide_no is 1-based and matches AppleScript's iteration order (which
includes skipped slides — same as `current.keynote_no` in build.py).
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


import re

# AppleScript reports an element's VISIBLE mask region; IWA stores the
# image's natural frame. Same image, different bbox — so we can't bbox-match
# directly. Strategy:
#   1. Filter slide's IWA assets by file_name stem (strip trailing -NNNN data
#      id suffix and ".ext"). Usually narrows to one.
#   2. If still multiple, fall back to a fuzzy bbox proximity ranking.
#   3. If file_name is empty (some inserted movies), use kind + bbox.


def _gradient_to_css(gradient: dict) -> str:
    """Convert an IWA gradient dict into a CSS `linear-gradient(...)` string.

    Keynote angle convention: radians, counter-clockwise from +x axis.
    CSS angle convention: degrees, clockwise from up (`0deg` = bottom-to-top).
    Transform: css_deg = (90 - kn_deg) mod 360
    """
    import math
    stops = gradient.get("stops") or []
    if not stops:
        return ""
    # Angle (linear gradient only — radial not yet handled, fall back to vertical)
    angle_rad = (gradient.get("anglegradient") or {}).get("gradientangle", math.pi / 2)
    try:
        angle_rad = float(angle_rad)
    except (TypeError, ValueError):
        angle_rad = math.pi / 2
    angle_deg_kn = math.degrees(angle_rad)
    angle_deg_css = (90.0 - angle_deg_kn) % 360.0
    css_stops = []
    for s in stops:
        c = s.get("color") or {}
        r = int(round(float(c.get("r") or 0) * 255))
        g = int(round(float(c.get("g") or 0) * 255))
        b = int(round(float(c.get("b") or 0) * 255))
        a = float(c.get("a") if c.get("a") is not None else 1.0)
        frac_pct = float(s.get("fraction") or 0) * 100.0
        css_stops.append(f"rgba({r},{g},{b},{a:.3f}) {frac_pct:.1f}%")
    # Multiply style-level opacity in later — we leave that to the caller
    return f"linear-gradient({angle_deg_css:.1f}deg, {', '.join(css_stops)})"


def _bezier_to_svg_path(bz: dict) -> tuple:
    """Convert a Keynote `bezierPathSource` dict into an SVG path `d` string
    plus the viewBox parameters needed to draw it without clipping.

    Returns (d_string, vb_x, vb_y, vb_w, vb_h). The d_string is in
    Keynote's path-local coordinate space (which is NOT the shape's
    natural size — Keynote stores bezier control points in a normalized
    ~100-unit coordinate frame, with overshoots beyond [0,100] when the
    curve's control polygon expands past the rect, as it does for a
    circle inscribed in a square).

    The caller emits <svg viewBox="vb_x vb_y vb_w vb_h"
    preserveAspectRatio="none"> so the path stretches to the shape's
    actual rendered bbox without clipping its anchor/control overshoots.

    Returns ("", 0, 0, 0, 0) when the path is empty or malformed.
    """
    if not isinstance(bz, dict):
        return ("", 0.0, 0.0, 0.0, 0.0)
    elements = ((bz.get("path") or {}).get("elements")) or []
    # Rectangle-shortcut: a path made of moveTo + N lineTo + closeSubpath
    # (no curveTo / quadCurveTo) is just an axis-aligned rectangle, which
    # we can render as a plain <div> with the shape's CSS fill (gradient
    # CSS works correctly in `background:`, NOT in SVG <path fill="...">).
    # Return empty so the build.py shape branch falls back to the div
    # path. Critical: SVG `fill="linear-gradient(...)"` is INVALID syntax,
    # so without this fast-path our dark-gradient overlays render as
    # transparent paths (image looks bright, text contrast lost).
    has_curve = any(
        isinstance(el, dict) and el.get("type") in ("curveTo", "quadCurveTo")
        for el in elements
    )
    if not has_curve:
        return ("", 0.0, 0.0, 0.0, 0.0)
    parts: list[str] = []
    # Track actual path bounds so we can size the viewBox to fit. Keynote
    # circles have control polygons that extend ~5% beyond the visual
    # bounding rect (e.g. y goes from -4.88 to 104.88 for what's nominally
    # a 0..100 shape) — if we set viewBox to 0,0,100,100 those overshoots
    # get clipped, turning circles into quarter-arcs (this was p5's dots
    # and p80's brain/eye/etc).
    min_x = float("inf");  min_y = float("inf")
    max_x = float("-inf"); max_y = float("-inf")
    def _bump(p):
        nonlocal min_x, min_y, max_x, max_y
        if p is None: return
        if p[0] < min_x: min_x = p[0]
        if p[0] > max_x: max_x = p[0]
        if p[1] < min_y: min_y = p[1]
        if p[1] > max_y: max_y = p[1]
    for el in elements:
        if not isinstance(el, dict): continue
        t = el.get("type") or el.get("elementType") or ""
        pts = el.get("points") or []
        if not isinstance(pts, list): continue
        def xy(i):
            p = pts[i] if i < len(pts) else None
            if not isinstance(p, dict): return None
            try:
                return (float(p.get("x") or 0), float(p.get("y") or 0))
            except (TypeError, ValueError):
                return None
        if t == "moveTo" and pts:
            p = xy(0)
            if p:
                parts.append(f"M{p[0]:.2f} {p[1]:.2f}"); _bump(p)
        elif t == "lineTo" and pts:
            p = xy(0)
            if p:
                parts.append(f"L{p[0]:.2f} {p[1]:.2f}"); _bump(p)
        elif t == "curveTo" and len(pts) >= 3:
            c1, c2, anc = xy(0), xy(1), xy(2)
            if c1 and c2 and anc:
                parts.append(f"C{c1[0]:.2f} {c1[1]:.2f} "
                             f"{c2[0]:.2f} {c2[1]:.2f} "
                             f"{anc[0]:.2f} {anc[1]:.2f}")
                _bump(c1); _bump(c2); _bump(anc)
        elif t == "quadCurveTo" and len(pts) >= 2:
            c, anc = xy(0), xy(1)
            if c and anc:
                parts.append(f"Q{c[0]:.2f} {c[1]:.2f} {anc[0]:.2f} {anc[1]:.2f}")
                _bump(c); _bump(anc)
        elif t in ("closeSubpath", "closePath"):
            parts.append("Z")
    if not parts or min_x == float("inf"):
        return ("", 0.0, 0.0, 0.0, 0.0)
    return (" ".join(parts), min_x, min_y, max_x - min_x, max_y - min_y)


def _strip_data_id_suffix(name: str) -> str:
    """`已粘贴的图像-9115.png` → `已粘贴的图像` ;  `image-2-1.png` → `image-2-1`.

    Only strip a trailing `-NNNN+` that's at least 4 digits (Keynote's data
    id format is always large numbers). A trailing `-1` is part of the real
    name and must NOT be stripped (`image-2-1.png` stem is `image-2-1`).
    """
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return re.sub(r"-\d{4,}$", "", stem)


@dataclass
class _Asset:
    slide_no: int          # 1-based, matches AppleScript order
    kind: str              # "image" or "movie"
    x: float
    y: float
    w: float
    h: float
    filename: str          # actual on-disk name under Data/
    # When True, the underlying TSD.ImageArchive has a `mask` field —
    # Keynote applied a crop/mask to the image. In that case the visible
    # display bbox is SMALLER than this asset's geometry; AppleScript
    # reports the masked visible region (which is what we want to render
    # at). When False, the image renders at its full geometry (no mask)
    # and AppleScript may report a narrower clipped bbox by mistake —
    # use THIS asset's bbox to avoid object-fit:cover side-cropping.
    has_mask: bool = False


@dataclass
class _TextAlign:
    slide_no: int
    x: float
    y: float
    w: float
    h: float
    align: str             # "left" / "center" / "right" / "justify" / "natural"
    # Authored line spacing (Keynote's lineSpacing.amount, e.g. 0.9, 1.0,
    # 1.2). Use directly as CSS `line-height: <amount>`. 0 means default
    # (build.py keeps its 1.35 / 1.4 baseline in that case).
    line_height: float = 0.0


@dataclass
class _ShapeFill:
    """Translucent / colored / gradient shape backdrop derived from IWA
    style chain.

    AppleScript reports many shape fills as `fill=none` — color comes from
    a parent ShapeStyle, not a direct assignment. We surface here:
      · solid color fills (r,g,b,alpha)
      · linear gradient fills (gradient_css carries the full CSS string)
    `gradient_css`, when non-empty, is the source-of-truth — render via
    `background: <gradient_css>;` and ignore the r/g/b fields.
    """
    slide_no: int
    x: float
    y: float
    w: float
    h: float
    r: int                 # 0-255 (solid fill path)
    g: int
    b: int
    alpha: float           # 0..1 (solid fill path: color-alpha × style opacity)
    has_text: bool
    gradient_css: str = ""  # non-empty → use this instead of rgba(r,g,b,a)
    # pathsource.pointPathSource.type — Keynote's named shape type, e.g.
    # "kTSDRightSingleArrow", "kTSDStar", "kTSDOval", "kTSDRoundedRect".
    # When set, build.py can render proper geometry (SVG path) instead of
    # a bbox-only colored rectangle. Empty string for shapes without a
    # named pathsource (typical bezier paths, default rects).
    shape_kind: str = ""
    # Rotation angle in degrees (Keynote's geometry.angle, kept here so
    # build.py can correctly orient SVG geometry without re-querying).
    angle: float = 0.0
    # Bezier path (from super.pathsource.bezierPathSource) — for custom
    # Keynote shapes (the big rings on p5, etc). 3-tuple of:
    #   (svg_d_string, natural_width, natural_height)
    # natural_w/h define the viewBox so the path scales to the shape bbox.
    # Empty d_string when shape has no bezier path.
    bezier_path: tuple = ("", 0.0, 0.0, 0.0, 0.0)
    # Stroke (border) info from the ShapeStyle chain. When stroke_width > 0,
    # the shape was authored with a visible border in Keynote — build.py
    # should emit `border: <w>px <dash> <color>`. Many slides (p5's big
    # ring circles, divider boxes) have NO fill and stroke-only; without
    # this they'd render as invisible empty divs.
    stroke_color: str = ""    # "rgba(r,g,b,a)" or "" when no stroke
    stroke_width: float = 0.0
    stroke_dash: str = ""     # "" / "dashed" / "dotted"


# Map TSWP TextAlignmentType enum (TATvalue0..4) to CSS-friendly strings.
# Keynote / iWork proto convention (verified empirically against centered
# title shapes in test decks):
#   0 = left, 1 = right, 2 = center, 3 = justify, 4 = natural (locale default)
_TAT_TO_ALIGN = {
    "TATvalue0": "left",
    "TATvalue1": "right",
    "TATvalue2": "center",
    "TATvalue3": "justify",
    "TATvalue4": "natural",
}


class IWAAssetMap:
    def __init__(self, assets: list[_Asset], text_aligns: list[_TextAlign] = None,
                 shape_fills: list[_ShapeFill] = None,
                 master_bboxes: dict = None,
                 slide_bgs: dict = None):
        self._assets = assets
        self._by_slide: dict[int, list[_Asset]] = {}
        for a in assets:
            self._by_slide.setdefault(a.slide_no, []).append(a)
        self._aligns_by_slide: dict[int, list[_TextAlign]] = {}
        for ta in (text_aligns or []):
            self._aligns_by_slide.setdefault(ta.slide_no, []).append(ta)
        self._fills_by_slide: dict[int, list[_ShapeFill]] = {}
        for sf in (shape_fills or []):
            self._fills_by_slide.setdefault(sf.slide_no, []).append(sf)
        # (slide_no, filename) → (x, y, w, h) of the image IN THE TEMPLATE.
        # AppleScript reports master images at their CLIPPED bbox (the visible
        # region intersected with the canvas), which mis-positions tall/wide
        # template backgrounds — `up@2x.png` is 2048×6456 but AppleScript said
        # 1958×2076, so object-fit:cover shows the wrong slice. The template
        # IWA has the TRUE placement; we render at that.
        self._master_bbox: dict[tuple[int, str], tuple[float, float, float, float]] = master_bboxes or {}
        # slide_no → CSS string ("#RRGGBB" or "linear-gradient(...)"). Source of
        # truth: KN.SlideStyleArchive.slideProperties.fill resolved from each
        # slide's style identifier. None → no explicit fill, caller falls back.
        self._slide_bg: dict[int, str] = slide_bgs or {}

    def slide_background(self, slide_no: int) -> Optional[str]:
        """Return the CSS background value (color or gradient) for this slide,
        as authored in Keynote's SlideStyleArchive. None if not extractable."""
        return self._slide_bg.get(slide_no)

    def master_bbox(self, slide_no: int, file_name: str) -> Optional[tuple[float, float, float, float]]:
        """Return (x, y, w, h) of a master/template image as positioned IN
        the template, or None if not in our map. Match by file_name stem,
        scoped to slide_no when possible."""
        if not file_name:
            return None
        stem = _strip_data_id_suffix(file_name)
        # First try (slide_no, fn) exact stem match
        for (sn, fn), bbox in self._master_bbox.items():
            if sn == slide_no and _strip_data_id_suffix(fn) == stem:
                return bbox
        # Fall back to ANY slide's template that has this filename stem
        for (sn, fn), bbox in self._master_bbox.items():
            if _strip_data_id_suffix(fn) == stem:
                return bbox
        return None

    def master_filename(self, slide_no: int, file_name: str) -> Optional[str]:
        """Resolve an AppleScript-reported MASTER image stem (e.g. 'image6.jpeg')
        to the EXACT on-disk Data/ filename for THIS slide's template (e.g.
        'image6-9334.jpeg'). Returns None if no master record matches.

        Why: AppleScript reports master images by basename only (stripped of
        the '-<data_id>' suffix). When a Keynote deck has SEVERAL distinct
        'image6.<ext>' files across different templates (one per master), the
        legacy stem-based file-system scan picks the wrong file by aspect
        ratio — so slide 65 ends up rendering slide 60's cityscape. This
        method gives the TRUE filename from the per-slide template index."""
        if not file_name:
            return None
        stem = _strip_data_id_suffix(file_name)
        # Prefer slide-scoped match.
        for (sn, fn), _ in self._master_bbox.items():
            if sn == slide_no and _strip_data_id_suffix(fn) == stem:
                return fn
        # Global fallback — only useful when the template image isn't
        # registered against this specific slide_no but exists somewhere.
        for (sn, fn), _ in self._master_bbox.items():
            if _strip_data_id_suffix(fn) == stem:
                return fn
        return None

    def shape_fills_for_slide(self, slide_no: int) -> list[_ShapeFill]:
        """All ShapeInfo-archive fills on this slide, in IWA archive order."""
        return list(self._fills_by_slide.get(slide_no, []))

    def lookup_with_bbox(self, slide_no: int, x: float, y: float, w: float, h: float,
                         file_name: Optional[str] = None,
                         kind: Optional[str] = None) -> Optional[tuple]:
        """Like `lookup`, but returns (filename, (x, y, w, h), has_mask)."""
        candidates = self._by_slide.get(slide_no, [])
        if kind:
            candidates = [a for a in candidates if a.kind == kind]
        if not candidates:
            return None
        if file_name:
            ap_stem = _strip_data_id_suffix(file_name)
            stem_hits = [a for a in candidates
                         if _strip_data_id_suffix(a.filename) == ap_stem]
            if not stem_hits:
                # Long-prefix fallback. Keynote sometimes truncates very long
                # filenames (e.g. DALL-E descriptions with 200+ chars) at
                # DIFFERENT byte positions between AppleScript and the on-disk
                # name. p77's "Rearrange_the_5_icons..." is truncated to
                # `..._over_retention_le.png` by AppleScript but stored as
                # `..._over_-15325.png` on disk. Stem match fails, but they
                # share a 200-char common prefix — only one IWA candidate
                # plausibly matches. Require ≥ 50 chars of shared prefix
                # AND a unique winner to avoid mis-pairing.
                prefix_hits = []
                MIN_PREFIX = 50
                for a in candidates:
                    cand_stem = _strip_data_id_suffix(a.filename)
                    n = 0
                    for ca, cb in zip(ap_stem, cand_stem):
                        if ca != cb: break
                        n += 1
                    if n >= MIN_PREFIX:
                        prefix_hits.append((n, a))
                if len(prefix_hits) == 1:
                    a = prefix_hits[0][1]
                    return (a.filename, (a.x, a.y, a.w, a.h), a.has_mask)
                return None
            candidates = stem_hits
        if len(candidates) == 1:
            a = candidates[0]
            return (a.filename, (a.x, a.y, a.w, a.h), a.has_mask)
        best = max(candidates, key=lambda a: _bbox_score(a, x, y, w, h))
        return (best.filename, (best.x, best.y, best.w, best.h), best.has_mask)

    def lookup(self, slide_no: int, x: float, y: float, w: float, h: float,
               file_name: Optional[str] = None,
               kind: Optional[str] = None) -> Optional[str]:
        """Return the Data/ filename matching this element, or None.

        Match strategy (in order):
          1. Same kind (image vs movie) — if `kind` is given.
          2. If `file_name` is given, filter by stem match (strip data-id
             suffix and extension). This usually disambiguates uniquely,
             because two elements on the same slide rarely share a stem.
          3. If still > 1 candidate, pick the one whose bbox is closest
             (best size-overlap heuristic — see _bbox_score).
          4. If file_name is empty (some inserted movies have no exposable
             name), fall straight through to bbox-only.
        """
        candidates = self._by_slide.get(slide_no, [])
        if kind:
            candidates = [a for a in candidates if a.kind == kind]
        if not candidates:
            return None

        if file_name:
            ap_stem = _strip_data_id_suffix(file_name)
            stem_hits = [a for a in candidates
                         if _strip_data_id_suffix(a.filename) == ap_stem]
            if not stem_hits:
                # NO stem match. Critical: don't fall back to bbox scoring
                # across unrelated assets — that pairs a master logo to a
                # random phone screenshot just because positions are close.
                # Hand back to the caller so the legacy stem+dim heuristic
                # (which has its own scope) can have a shot.
                return None
            candidates = stem_hits

        if len(candidates) == 1:
            return candidates[0].filename

        # Tiebreaker among stem-matched candidates: bbox proximity. Also
        # covers the empty-file_name case where caller passed kind only
        # (e.g. a movie whose AppleScript file_name is "" — fall through
        # to bbox match within that kind).
        best = max(candidates, key=lambda a: _bbox_score(a, x, y, w, h))
        return best.filename

    def assets_for_slide(self, slide_no: int) -> list[_Asset]:
        return list(self._by_slide.get(slide_no, []))

    def _best_text_record(self, slide_no: int, x: float, y: float,
                          w: float, h: float) -> Optional["_TextAlign"]:
        """Pick the best-matching paragraph record for a bbox. Same scoring
        as text_alignment() but returns the full record so callers can also
        read line_height."""
        candidates = self._aligns_by_slide.get(slide_no, [])
        if not candidates:
            return None
        def score(ta: "_TextAlign") -> float:
            ox = max(0.0, min(ta.x + ta.w, x + w) - max(ta.x, x))
            x_score = ox / max(min(ta.w, w), 1.0)
            dy = abs((ta.y + ta.h / 2) - (y + h / 2)) / 1080.0
            return x_score - dy
        best = max(candidates, key=score)
        if score(best) < 0.5:
            return None
        return best

    def text_alignment(self, slide_no: int, x: float, y: float,
                       w: float, h: float) -> Optional[str]:
        """Return CSS alignment ("left"/"center"/"right"/"justify") for the
        text element at this bbox, or None if not known.

        IWA stores text shapes with the AUTHORED width but often h=0 (text
        auto-fits to content). AppleScript reports the RENDERED bbox with
        a real height. So bbox-area overlap doesn't work — we score by
        horizontal extent overlap + vertical center proximity instead.
        """
        best = self._best_text_record(slide_no, x, y, w, h)
        if best is None or not best.align or best.align == "natural":
            return None
        return best.align

    def text_line_height(self, slide_no: int, x: float, y: float,
                         w: float, h: float) -> float:
        """Return the authored line-height multiplier from the IWA
        ParagraphStyle.lineSpacing.amount, or 0.0 when not specified
        (caller should use its default)."""
        best = self._best_text_record(slide_no, x, y, w, h)
        if best is None:
            return 0.0
        return best.line_height

    @classmethod
    def from_key(cls, key_path: Path) -> "IWAAssetMap":
        """Build the map by parsing a .key bundle. Three on-disk forms, all
        exposing the same `Index/<...>.iwa` entries:
          1. single-file zip                       → read Index/* from the zip
          2. directory bundle with unpacked Index/ → read Index/* from disk
          3. directory bundle with nested Index.zip → read Index/* from that
             zip (Keynote Creator Studio 15+ on iCloud stores the index
             zipped even when the bundle itself is a directory)
        """
        try:
            from keynote_parser.codec import IWAFile
        except ImportError as e:
            raise RuntimeError(
                "keynote-parser package required for IWA resolution. "
                "Install with: pip install keynote-parser"
            ) from e

        # Open as single-file zip OR directory bundle.
        if key_path.is_file() and zipfile.is_zipfile(key_path):
            opener = _ZipOpener(key_path)
        elif key_path.is_dir():
            # Directory bundle: prefer an unpacked Index/ tree; otherwise fall
            # back to a nested Index.zip. The zip's entries already carry the
            # `Index/` prefix, so _ZipOpener serves them under the exact names
            # the rest of from_key reads — no path translation needed.
            index_zip = key_path / "Index.zip"
            if (key_path / "Index").is_dir():
                opener = _DirOpener(key_path)
            elif index_zip.is_file() and zipfile.is_zipfile(index_zip):
                opener = _ZipOpener(index_zip)
            else:
                raise RuntimeError(
                    f"directory bundle has neither Index/ nor Index.zip: {key_path}"
                )
        else:
            raise RuntimeError(f"not a .key file or bundle: {key_path}")

        with opener as o:
            # 1. data_id → on-disk filename (from Metadata.iwa's
            # PackageMetadata.datas list)
            meta_d = IWAFile.from_buffer(o.read("Index/Metadata.iwa")).to_dict()
            data_id_to_filename: dict[str, str] = {}
            for chunk in meta_d.get("chunks", []):
                for ar in chunk.get("archives", []):
                    for obj in ar.get("objects", []):
                        if obj.get("_pbtype") == "TSP.PackageMetadata":
                            for d in obj.get("datas", []):
                                # "fileName" is the on-disk name in Data/;
                                # fall back to preferredFileName if missing.
                                fn = d.get("fileName") or d.get("preferredFileName")
                                if fn:
                                    data_id_to_filename[d["identifier"]] = fn

            # 2. Slide order: KN.ShowArchive.slideTree.slides is the ordered
            # list of SlideNodeArchive ids; each node points to a SlideArchive
            # id which matches `Index/Slide-<id>.iwa`. Order INCLUDES skipped
            # slides, matching AppleScript's iteration.
            doc_d = IWAFile.from_buffer(o.read("Index/Document.iwa")).to_dict()
            node_order: list[str] = []
            node_to_slide_arch: dict[str, str] = {}
            for chunk in doc_d.get("chunks", []):
                for ar in chunk.get("archives", []):
                    for obj in ar.get("objects", []):
                        t = obj.get("_pbtype")
                        if t == "KN.ShowArchive":
                            for ref in obj.get("slideTree", {}).get("slides", []):
                                node_order.append(ref["identifier"])
                        elif t == "KN.SlideNodeArchive":
                            nid = ar["header"]["identifier"]
                            node_to_slide_arch[nid] = obj["slide"]["identifier"]
            slide_arch_order = [node_to_slide_arch[n] for n in node_order
                                if n in node_to_slide_arch]

            # File names for slide IWAs vary: most decks have
            #   Index/Slide-<arch_id>.iwa
            # but Keynote sometimes adds a version suffix:
            #   Index/Slide-<arch_id>-<v>.iwa     (e.g. eCINDI deck uses -2)
            # Also slide 1 historically lives at Index/Slide.iwa with no id.
            # Build a stable lookup table so every code path uses the same one.
            all_names_set = set(o.namelist())
            import re as _re
            slide_iwa_file: dict[str, str] = {}  # arch_id → "Index/Slide-...iwa"
            for a in slide_arch_order:
                # 1) Exact match
                cand = f"Index/Slide-{a}.iwa"
                if cand in all_names_set:
                    slide_iwa_file[a] = cand
                    continue
                # 2) Versioned match: Slide-<id>-<anything>.iwa
                pat = _re.compile(rf"^Index/Slide-{_re.escape(a)}(?:-[^/]*)?\.iwa$")
                for nm in all_names_set:
                    if pat.match(nm):
                        slide_iwa_file[a] = nm
                        break
                else:
                    # 3) The very first slide may be Index/Slide.iwa (no id)
                    if a == slide_arch_order[0] and "Index/Slide.iwa" in all_names_set:
                        slide_iwa_file[a] = "Index/Slide.iwa"

            # 3a. Pre-pass A: index ParagraphStyleArchive entries (source of
            # truth for text alignment). Most styles live in
            # DocumentStylesheet.iwa, but per-slide overrides can live in the
            # slide's own iwa.
            para_align: dict[str, str] = {}  # arch_id → "left"/"center"/etc.
            para_lh: dict[str, float] = {}   # arch_id → line-height multiplier
            # Pre-pass B: index ShapeStyleArchive entries (source of truth for
            # shape fill color + opacity). Walk parent chain to resolve.
            shape_style_raw: dict[str, dict] = {}  # arch_id → {fill, opacity, parent}
            for n in (("Index/DocumentStylesheet.iwa",) +
                      tuple(slide_iwa_file[a] for a in slide_arch_order
                            if a in slide_iwa_file)):
                try:
                    d = IWAFile.from_buffer(o.read(n)).to_dict()
                except Exception:
                    continue
                for chunk in d.get("chunks", []):
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            t = obj.get("_pbtype")
                            arid = ar["header"]["identifier"]
                            if t == "TSWP.ParagraphStyleArchive":
                                pp = obj.get("paraProperties") or {}
                                a = pp.get("alignment")
                                if a in _TAT_TO_ALIGN:
                                    para_align[arid] = _TAT_TO_ALIGN[a]
                                # lineSpacing has two common modes in Keynote:
                                #   · default / kRelativeLineSpacing → amount
                                #     is a unitless multiplier (0.9, 1.18).
                                #     CSS: `line-height: <amount>`.
                                #   · kExactLineSpacing → amount is absolute
                                #     points. CSS: `line-height: <amount>px`.
                                # We encode the mode by sign convention:
                                # positive = multiplier, negative = -points.
                                # build.py decodes and emits the right unit.
                                ls = pp.get("lineSpacing")
                                if isinstance(ls, dict):
                                    amt = ls.get("amount")
                                    mode = ls.get("mode") or ""
                                    if amt is not None:
                                        try:
                                            amt_f = float(amt)
                                            if mode == "kExactLineSpacing":
                                                # Encode points as a negative
                                                # value so the caller knows.
                                                para_lh[arid] = -amt_f
                                            else:
                                                para_lh[arid] = amt_f
                                        except (TypeError, ValueError):
                                            pass
                            elif t == "TSWP.ShapeStyleArchive":
                                # TSWP.ShapeStyleArchive nests:
                                #   super.super.parent.identifier  → parent style
                                #   super.shapeProperties           → overrides (incl. opacity)
                                # And TSP.StylePropertyTable on super.super
                                # carries the bulk properties (fill etc).
                                # We capture raw and resolve later.
                                sup = obj.get("super", {}) or {}
                                ssup = sup.get("super", {}) or {}
                                parent = (ssup.get("parent") or {}).get("identifier")
                                # Properties at this style's level live on
                                # sup.shapeProperties (overrides) AND on
                                # ssup.shapeProperties (the "real" props).
                                own_props = (sup.get("shapeProperties") or {})
                                base_props = (ssup.get("shapeProperties") or {})
                                shape_style_raw[arid] = {
                                    "parent": parent,
                                    "own": own_props,
                                    "base": base_props,
                                }

            # Resolve shape-style chain. Returns dict with keys:
            #   "kind": "color" | "gradient" | None
            #   "color": (r,g,b,a) tuple in 0..1, when kind == "color"
            #   "gradient_css": full CSS linear-gradient(...) string, when kind == "gradient"
            #   "opacity": 0..1, the style-level alpha multiplier
            #   "stroke_color": (r,g,b,a) in 0..1 or None
            #   "stroke_width": float (px) or 0
            #   "stroke_dash":  "" / "dashed" / "dotted"  (CSS border-style)
            # A gradient fill in any level wins over a color fill in parents
            # (gradient is a complete fill spec, not an additive override).
            def _resolve_shape_style(sid: str, seen=None) -> dict:
                if seen is None: seen = set()
                if not sid or sid in seen or sid not in shape_style_raw:
                    return {"kind": None, "color": None, "gradient_css": "",
                            "opacity": 1.0, "stroke_color": None,
                            "stroke_width": 0.0, "stroke_dash": ""}
                seen.add(sid)
                raw = shape_style_raw[sid]
                parent = _resolve_shape_style(raw["parent"], seen)
                kind = parent["kind"]
                color = parent["color"]
                grad = parent["gradient_css"]
                op = parent["opacity"]
                stroke_color = parent["stroke_color"]
                stroke_width = parent["stroke_width"]
                stroke_dash = parent["stroke_dash"]
                # Walk own → base properties (own overrides base overrides parent)
                for src in (raw["base"], raw["own"]):
                    if not isinstance(src, dict): continue
                    if "fill" in src:
                        fill = src.get("fill")
                        # Empty fill dict ({}) in Keynote means the author
                        # explicitly cleared the fill ("No Fill" in UI). This
                        # MUST NOT inherit from a parent style — otherwise the
                        # parent's e.g. white default leaks through. Treat
                        # empty as "explicit transparent / no fill".
                        if not fill:
                            kind, color, grad = None, None, ""
                        elif isinstance(fill, dict):
                            # Gradient (linear)
                            gradient = fill.get("gradient")
                            if isinstance(gradient, dict) and gradient.get("stops"):
                                css = _gradient_to_css(gradient)
                                if css:
                                    kind, color, grad = "gradient", None, css
                            else:
                                c = fill.get("color")
                                if isinstance(c, dict) and "r" in c:
                                    color = (float(c.get("r") or 0),
                                             float(c.get("g") or 0),
                                             float(c.get("b") or 0),
                                             float(c.get("a") if c.get("a") is not None else 1.0))
                                    kind, grad = "color", ""
                                else:
                                    # fill dict present but no recognisable
                                    # color or gradient — treat as cleared.
                                    kind, color, grad = None, None, ""
                    # Stroke (border). Keynote stores it as
                    #   stroke: {color: {r,g,b,a}, width: px, pattern: {...}}
                    # Empty {} clears stroke. Else extract color + width + pattern.
                    if "stroke" in src:
                        st = src.get("stroke")
                        if not st:
                            stroke_color, stroke_width, stroke_dash = None, 0.0, ""
                        elif isinstance(st, dict):
                            sc = st.get("color")
                            if isinstance(sc, dict) and "r" in sc:
                                stroke_color = (
                                    float(sc.get("r") or 0),
                                    float(sc.get("g") or 0),
                                    float(sc.get("b") or 0),
                                    float(sc.get("a") if sc.get("a") is not None else 1.0),
                                )
                            sw = st.get("width")
                            if sw is not None:
                                stroke_width = float(sw)
                            # pattern.type: TSDSolidPattern, or array-based dash.
                            patt = st.get("pattern") or {}
                            ptype = patt.get("type", "")
                            if "Dash" in ptype:
                                stroke_dash = "dashed"
                            elif "Dot" in ptype:
                                stroke_dash = "dotted"
                            else:
                                stroke_dash = ""
                    if "opacity" in src and src["opacity"] is not None:
                        op = float(src["opacity"])
                return {"kind": kind, "color": color, "gradient_css": grad,
                        "opacity": op, "stroke_color": stroke_color,
                        "stroke_width": stroke_width, "stroke_dash": stroke_dash}

            # 3b. Per-slide pass: collect image/movie drawables AND text-shape
            # alignments. For each slide:
            #   · Find TSD.ImageArchive / TSD.MovieArchive → asset map
            #   · Find TSWP.ShapeInfoArchive / KN.PlaceholderArchive → look up
            #     its ownedStorage → first paragraph style → alignment.
            all_names = set(o.namelist())
            assets: list[_Asset] = []
            text_aligns: list[_TextAlign] = []
            shape_fills: list[_ShapeFill] = []
            # (slide_no, on-disk filename) → (x, y, w, h) from the slide's
            # templateSlide chain. Captures the TRUE placement of master/
            # template images (which AppleScript reports clipped to canvas).
            master_bboxes: dict[tuple[int, str], tuple[float, float, float, float]] = {}

            # Pre-pass: build slide_no → templateSlide arch_id mapping via
            # SlideNodeArchive. Then for each template_id, scan its IWA
            # (either Index/TemplateSlide-<id>.iwa, or Index/TemplateSlide.iwa
            # which holds the global default(s)) for image/movie drawables.
            slide_to_template: dict[int, str] = {}
            for slide_no, arch_id in enumerate(slide_arch_order, 1):
                iwa_name = slide_iwa_file.get(arch_id)
                if not iwa_name:
                    continue
                try:
                    sd = IWAFile.from_buffer(o.read(iwa_name)).to_dict()
                except Exception:
                    continue
                for chunk in sd.get("chunks", []):
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            if obj.get("_pbtype") == "KN.SlideArchive":
                                tpl = (obj.get("templateSlide") or {}).get("identifier")
                                if tpl:
                                    slide_to_template[slide_no] = tpl

            # Pre-pass: index template_id → list of image_archives. Templates
            # can live in `Index/TemplateSlide-<id>.iwa` (per-template file)
            # OR in `Index/TemplateSlide.iwa` (one file may hold several
            # default templates). Walk both.
            template_images: dict[str, list[tuple[str, float, float, float, float]]] = {}
            # filename = filename ; tuple = (filename, x, y, w, h)

            def _index_template_iwa(name: str):
                try:
                    td = IWAFile.from_buffer(o.read(name)).to_dict()
                except Exception:
                    return
                # In TemplateSlide.iwa multiple slide archives may coexist;
                # group images by which SlideArchive's ownedDrawables they
                # belong to. ownedDrawables can include GroupArchives that
                # CONTAIN images — we walk those transitively so an image
                # nested inside a group on the template is still attributed
                # to the right slide. Without that walk, p68/p69 lost their
                # 1920×4000 vertical-scroll bg + 960×1080 side panel because
                # both images sat inside Group 2693904, not directly under
                # SlideArchive.ownedDrawables.
                for chunk in td.get("chunks", []):
                    # Collect every archive in this chunk for fast lookup.
                    arch_by_id: dict[str, dict] = {}
                    for ar in chunk.get("archives", []):
                        arch_by_id[ar["header"]["identifier"]] = ar

                    # Walk drawable refs (recursively through Group archives)
                    # starting from each SlideArchive's ownedDrawables, and
                    # collect the set of archive IDs that ARE images / movies
                    # owned by that slide.
                    def _walk_drawables(start_ids: list[str]) -> set[str]:
                        seen: set[str] = set()
                        stack = list(start_ids)
                        while stack:
                            aid = stack.pop()
                            if aid in seen: continue
                            seen.add(aid)
                            ar = arch_by_id.get(aid)
                            if not ar: continue
                            for obj in ar.get("objects", []):
                                if obj.get("_pbtype") == "TSD.GroupArchive":
                                    # Group has children under several
                                    # historical field names. Push all.
                                    for k in ("childInfos", "children", "drawables"):
                                        lst = obj.get(k)
                                        if isinstance(lst, list):
                                            for it in lst:
                                                if isinstance(it, dict) and "identifier" in it:
                                                    stack.append(it["identifier"])
                        return seen

                    # Single-SlideArchive template files: attribute EVERY
                    # image archive in the file to that slide, regardless of
                    # whether it's reachable via ownedDrawables. This is the
                    # backstop for templates that use a non-standard
                    # ownership relation (some Keynote-saved templates).
                    slide_ids = [ar["header"]["identifier"]
                                 for ar in chunk.get("archives", [])
                                 for obj in ar.get("objects", [])
                                 if obj.get("_pbtype") == "KN.SlideArchive"]

                    if len(slide_ids) == 1:
                        sarid = slide_ids[0]
                        for ar in chunk.get("archives", []):
                            for obj in ar.get("objects", []):
                                if obj.get("_pbtype") not in ("TSD.ImageArchive", "TSD.MovieArchive"):
                                    continue
                                t = obj.get("_pbtype")
                                ref = (obj.get("data") if t == "TSD.ImageArchive"
                                       else obj.get("movieData")) or {}
                                data_id = ref.get("identifier")
                                fname = data_id_to_filename.get(data_id) if data_id else None
                                if not fname: continue
                                geo = obj.get("super", {}).get("geometry", {}) or {}
                                pos = geo.get("position", {}) or {}
                                size = geo.get("size", {}) or {}
                                bbox = (
                                    float(pos.get("x", 0) or 0),
                                    float(pos.get("y", 0) or 0),
                                    float(size.get("width", 0) or 0),
                                    float(size.get("height", 0) or 0),
                                )
                                template_images.setdefault(sarid, []).append((fname, *bbox))
                        continue

                    # Multi-SlideArchive case: walk each slide's ownership
                    # transitively (through groups), then attribute images
                    # by membership.
                    slide_archives: dict[str, list[str]] = {}
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            if obj.get("_pbtype") != "KN.SlideArchive": continue
                            sarid = ar["header"]["identifier"]
                            initial = [d["identifier"]
                                       for d in obj.get("ownedDrawables", [])
                                       if isinstance(d, dict) and "identifier" in d]
                            slide_archives[sarid] = list(_walk_drawables(initial))

                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            if obj.get("_pbtype") not in ("TSD.ImageArchive", "TSD.MovieArchive"):
                                continue
                            t = obj.get("_pbtype")
                            ref = (obj.get("data") if t == "TSD.ImageArchive"
                                   else obj.get("movieData")) or {}
                            data_id = ref.get("identifier")
                            fname = data_id_to_filename.get(data_id) if data_id else None
                            if not fname: continue
                            geo = obj.get("super", {}).get("geometry", {}) or {}
                            pos = geo.get("position", {}) or {}
                            size = geo.get("size", {}) or {}
                            bbox = (
                                float(pos.get("x", 0) or 0),
                                float(pos.get("y", 0) or 0),
                                float(size.get("width", 0) or 0),
                                float(size.get("height", 0) or 0),
                            )
                            arid = ar["header"]["identifier"]
                            # Find owning slide via transitive walk membership.
                            for sarid, members in slide_archives.items():
                                if arid in members:
                                    template_images.setdefault(sarid, []).append((fname, *bbox))
                                    break

            for n in all_names:
                if n.startswith("Index/TemplateSlide") and n.endswith(".iwa"):
                    _index_template_iwa(n)

            # For each slide, register: (a) bboxes from its direct
            # templateSlide; (b) ALL template images globally (keyed by a
            # sentinel slide_no=-1). AppleScript's `base layout` resolves
            # via Keynote's internal master inheritance, which doesn't
            # always match the IWA `templateSlide` ref (slide 5's
            # templateSlide is an empty "blank" but AppleScript reports
            # up@2x.png from a parent master). The global fallback handles
            # that case.
            for slide_no, tpl_id in slide_to_template.items():
                for (fname, x, y, w, h) in template_images.get(tpl_id, []):
                    master_bboxes[(slide_no, fname)] = (x, y, w, h)
            for tpl_id, imgs in template_images.items():
                for (fname, x, y, w, h) in imgs:
                    # Don't overwrite a slide-specific entry
                    key = (-1, fname)
                    master_bboxes.setdefault(key, (x, y, w, h))
            for slide_no, arch_id in enumerate(slide_arch_order, 1):
                iwa_name = slide_iwa_file.get(arch_id)
                if not iwa_name:
                    continue
                slide_d = IWAFile.from_buffer(o.read(iwa_name)).to_dict()

                # First pass on this iwa: build a local storage-arch lookup so
                # we can resolve ShapeInfo → Storage → ParaStyle within one
                # slide without rescanning.
                storage_first_para: dict[str, Optional[str]] = {}
                # Also: index TSD.GroupArchive entries so we can compute
                # slide-absolute positions for nested shapes. A shape sitting
                # inside a group reports geometry.position RELATIVE to its
                # parent group; we need to walk the parent chain and sum
                # offsets to match what AppleScript reports (slide-absolute).
                group_pos: dict[str, tuple[float, float]] = {}     # arch_id → (x, y)
                parent_of: dict[str, str] = {}                       # child_id → group_id
                for chunk in slide_d.get("chunks", []):
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            pbt = obj.get("_pbtype")
                            if pbt == "TSWP.StorageArchive":
                                tps = obj.get("tableParaStyle") or {}
                                entries = tps.get("entries") or []
                                first = None
                                if entries:
                                    first = (entries[0].get("object") or {}).get("identifier")
                                storage_first_para[ar["header"]["identifier"]] = first
                            elif pbt == "TSD.GroupArchive":
                                gid = ar["header"]["identifier"]
                                geo = (obj.get("super", {}) or {}).get("geometry") or {}
                                pos = geo.get("position") or {}
                                group_pos[gid] = (
                                    float(pos.get("x", 0) or 0),
                                    float(pos.get("y", 0) or 0),
                                )
                                for key_name in ("childInfos", "children", "drawables"):
                                    lst = obj.get(key_name)
                                    if isinstance(lst, list):
                                        for it in lst:
                                            if isinstance(it, dict) and "identifier" in it:
                                                parent_of[it["identifier"]] = gid

                def _absolute_pos(arch_id: str, lx: float, ly: float) -> tuple[float, float]:
                    """Walk parent-group chain and sum offsets so the returned
                    (x, y) is in slide-absolute coordinates."""
                    ax, ay = lx, ly
                    cur = arch_id
                    guard = 0
                    while cur in parent_of and guard < 16:
                        gid = parent_of[cur]
                        gx, gy = group_pos.get(gid, (0.0, 0.0))
                        ax += gx; ay += gy
                        cur = gid
                        guard += 1
                    return ax, ay

                for chunk in slide_d.get("chunks", []):
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            t = obj.get("_pbtype", "")
                            # Asset extraction
                            if t in ("TSD.ImageArchive", "TSD.MovieArchive"):
                                if t == "TSD.ImageArchive":
                                    ref = obj.get("data") or {}
                                    kind = "image"
                                else:
                                    ref = obj.get("movieData") or {}
                                    kind = "movie"
                                data_id = ref.get("identifier")
                                fname = data_id_to_filename.get(data_id) if data_id else None
                                if fname:
                                    geo = obj.get("super", {}).get("geometry", {}) or {}
                                    pos = geo.get("position", {}) or {}
                                    size = geo.get("size", {}) or {}
                                    # `mask` field signals Keynote applied
                                    # a crop on this image — AppleScript
                                    # bbox is the visible masked region;
                                    # this asset's geometry is the underlying
                                    # natural placement.
                                    has_mask = bool(obj.get("mask"))
                                    lpx = float(pos.get("x", 0) or 0)
                                    lpy = float(pos.get("y", 0) or 0)
                                    ax, ay = _absolute_pos(
                                        ar["header"]["identifier"], lpx, lpy)
                                    assets.append(_Asset(
                                        slide_no=slide_no, kind=kind,
                                        x=ax, y=ay,
                                        w=float(size.get("width", 0) or 0),
                                        h=float(size.get("height", 0) or 0),
                                        filename=fname,
                                        has_mask=has_mask,
                                    ))
                                continue

                            # Shape archives (text-bearing or pure backdrops).
                            # Used for TWO purposes:
                            #   · text alignment (resolved via paragraph style)
                            #   · shape fill backdrop (resolved via shape style)
                            if t in ("TSWP.ShapeInfoArchive", "KN.PlaceholderArchive"):
                                # Geometry path differs between shape and placeholder.
                                geo = (obj.get("super", {}).get("super", {}).get("geometry")
                                       or obj.get("super", {}).get("geometry") or {})
                                pos = geo.get("position", {}) or {}
                                size = geo.get("size", {}) or {}
                                w = float(size.get("width", 0) or 0)
                                h = float(size.get("height", 0) or 0)
                                # Skip true empty placeholders.
                                if w == 0 and h == 0:
                                    continue
                                lpx = float(pos.get("x", 0) or 0)
                                lpy = float(pos.get("y", 0) or 0)
                                # Translate to slide-absolute by accumulating
                                # parent-group offsets. AppleScript reports
                                # slide-absolute, so we must too — otherwise
                                # bbox matching in build.py fails for any
                                # grouped shape.
                                px, py = _absolute_pos(ar["header"]["identifier"], lpx, lpy)

                                storage_ref = (obj.get("ownedStorage")
                                               or obj.get("deprecatedStorage") or {})
                                storage_id = storage_ref.get("identifier")
                                has_text = bool(storage_id)

                                # Alignment + line-height (text-props record).
                                # Emit one record per text-bearing shape as
                                # long as EITHER align or line_height is known.
                                if storage_id:
                                    para_id = storage_first_para.get(storage_id)
                                    align = para_align.get(para_id) if para_id else None
                                    lh = para_lh.get(para_id, 0.0) if para_id else 0.0
                                    if align or lh > 0:
                                        text_aligns.append(_TextAlign(
                                            slide_no=slide_no,
                                            x=px, y=py, w=w, h=h,
                                            align=align or "",
                                            line_height=lh,
                                        ))

                                # Named shape kind ("kTSDRightSingleArrow",
                                # "kTSDOval", etc.) — captured from the
                                # super.pathsource.pointPathSource block.
                                # build.py uses this to switch from a
                                # bbox-colored div to a proper SVG path for
                                # arrows / callouts / stars / etc.
                                shape_kind = ""
                                psrc = ((obj.get("super") or {})
                                        .get("pathsource") or {})
                                pps = psrc.get("pointPathSource") or {}
                                if isinstance(pps, dict):
                                    shape_kind = pps.get("type") or ""
                                # geometry.angle for rotation-aware rendering.
                                shape_angle = float(geo.get("angle", 0) or 0)
                                # Bezier path (custom-drawn shapes). Falls back
                                # to empty if shape uses a named pointPathSource
                                # or has no path. p5's big rings, organic blobs,
                                # callout speech bubbles all land here.
                                bz = psrc.get("bezierPathSource")
                                bezier_tuple = (_bezier_to_svg_path(bz)
                                                if isinstance(bz, dict) else
                                                ("", 0.0, 0.0, 0.0, 0.0))

                                # Shape fill — read via TSWP.ShapeStyleArchive
                                # parent chain. AppleScript can't surface these.
                                style_id = (obj.get("super", {}).get("style") or {}).get("identifier")
                                if style_id:
                                    rs = _resolve_shape_style(style_id)
                                    op = rs.get("opacity", 1.0)
                                    # Prepare stroke CSS string (used in BOTH
                                    # fill and stroke-only paths below).
                                    sc = rs.get("stroke_color")
                                    sw = rs.get("stroke_width", 0.0)
                                    sd = rs.get("stroke_dash", "")
                                    stroke_css = ""
                                    if sc is not None and sw > 0:
                                        sa = sc[3] * op  # stroke alpha × style opacity
                                        # Keynote's inherited theme default
                                        # ("Outline → 1px Black") shows up
                                        # everywhere in the shape style chain
                                        # but isn't actually rendered unless
                                        # the author explicitly turned it on.
                                        # Identify by: 1px width AND black
                                        # color. Treating these as no stroke
                                        # silences the false-positive 1px
                                        # borders that appeared on every shape.
                                        is_theme_default = (
                                            sw <= 1.0
                                            and sc[0] < 0.05 and sc[1] < 0.05 and sc[2] < 0.05
                                        )
                                        if sa > 0.02 and not is_theme_default:
                                            stroke_css = (f"rgba({int(round(sc[0]*255))},"
                                                          f"{int(round(sc[1]*255))},"
                                                          f"{int(round(sc[2]*255))},"
                                                          f"{sa:.3f})")
                                    # 3 paths: gradient fill, color fill, stroke-only.
                                    if rs.get("kind") == "gradient":
                                        css = rs.get("gradient_css") or ""
                                        if css and op > 0.02:
                                            shape_fills.append(_ShapeFill(
                                                slide_no=slide_no,
                                                x=px, y=py, w=w, h=h,
                                                r=0, g=0, b=0,
                                                alpha=op,
                                                has_text=has_text,
                                                gradient_css=css,
                                                shape_kind=shape_kind,
                                                angle=shape_angle,
                                                stroke_color=stroke_css,
                                                stroke_width=sw if stroke_css else 0.0,
                                                stroke_dash=sd if stroke_css else "",
                                                bezier_path=bezier_tuple,
                                            ))
                                    elif rs.get("kind") == "color":
                                        color = rs.get("color")
                                        if color is not None:
                                            r, g, b, a = color
                                            eff_alpha = a * op
                                            if eff_alpha > 0.02:
                                                shape_fills.append(_ShapeFill(
                                                    slide_no=slide_no,
                                                    x=px, y=py, w=w, h=h,
                                                    r=int(round(r * 255)),
                                                    g=int(round(g * 255)),
                                                    b=int(round(b * 255)),
                                                    alpha=eff_alpha,
                                                    has_text=has_text,
                                                    shape_kind=shape_kind,
                                                    angle=shape_angle,
                                                    stroke_color=stroke_css,
                                                    stroke_width=sw if stroke_css else 0.0,
                                                    stroke_dash=sd if stroke_css else "",
                                                    bezier_path=bezier_tuple,
                                                ))
                                    elif stroke_css and w > 1 and h > 1:
                                        # Stroke-only shape — no fill but has a
                                        # visible border. Common for ring
                                        # circles, divider boxes, etc. Emit
                                        # with alpha=0 sentinel: build.py
                                        # will render `background:transparent`
                                        # + `border:...`.
                                        # Skip text-bearing shapes: Keynote's
                                        # default 1px black stroke on text
                                        # frames isn't actually rendered. And
                                        # skip degenerate w=0/h=0 frames
                                        # (auto-fit text boxes).
                                        shape_fills.append(_ShapeFill(
                                            slide_no=slide_no,
                                            x=px, y=py, w=w, h=h,
                                            r=0, g=0, b=0,
                                            alpha=0.0,
                                            has_text=has_text,
                                            shape_kind=shape_kind,
                                            angle=shape_angle,
                                            stroke_color=stroke_css,
                                            stroke_width=sw,
                                            stroke_dash=sd,
                                            bezier_path=bezier_tuple,
                                        ))
            # === Slide backgrounds (KN.SlideStyleArchive → fill) ===
            # Every slide carries a `style: {identifier}` reference. Resolving
            # it yields slideProperties.fill, which is the authored background
            # (color or gradient). Read this FIRST — it's the source of truth.
            # The previous "white text → dark bg" area-weighted heuristic in
            # build.py is now only a fallback for slides whose style chain
            # doesn't yield a fill.
            slide_bgs: dict[int, str] = {}

            # Collect every KN.SlideStyleArchive across all iwa files.
            style_objs: dict[str, dict] = {}
            for name in all_names:
                if not name.endswith(".iwa"):
                    continue
                try:
                    nd = IWAFile.from_buffer(o.read(name)).to_dict()
                except Exception:
                    continue
                for chunk in nd.get("chunks", []):
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            if obj.get("_pbtype") == "KN.SlideStyleArchive":
                                style_objs[ar["header"]["identifier"]] = obj

            def _resolve_slide_fill(sid: str, depth: int = 0):
                """Walk the SlideStyleArchive parent chain until we find a
                slideProperties.fill. Returns the fill dict, or None."""
                if depth > 8 or not sid or sid not in style_objs:
                    return None
                obj = style_objs[sid]
                fill = (obj.get("slideProperties") or {}).get("fill")
                if fill:
                    return fill
                parent = ((obj.get("super", {}) or {})
                          .get("parent", {}) or {}).get("identifier")
                return _resolve_slide_fill(parent, depth + 1)

            def _fill_to_css(fill: dict) -> Optional[str]:
                """Turn an IWA fill dict into a CSS background value.

                Handles: solid color, linear/radial gradient, image fill.
                For image fills we emit `url('assets/_shared/<file>') center/cover`
                — the asset gets staged into _shared/ at build time. Returns
                None when the fill type is unrecognized."""
                if not isinstance(fill, dict):
                    return None
                # Solid color.
                col = fill.get("color")
                if col and isinstance(col, dict):
                    r = int(round(float(col.get("r") or 0) * 255))
                    g = int(round(float(col.get("g") or 0) * 255))
                    b = int(round(float(col.get("b") or 0) * 255))
                    a = float(col.get("a", 1.0) or 1.0)
                    if a >= 0.999:
                        return f"#{r:02X}{g:02X}{b:02X}"
                    return f"rgba({r},{g},{b},{a:.3f})"
                # Gradient (linear / radial). Reuse _gradient_to_css.
                grad = fill.get("gradient")
                if grad and isinstance(grad, dict):
                    try:
                        return _gradient_to_css(grad)
                    except Exception:
                        return None
                # Image fill — Keynote stores it as { image: { data: {identifier},
                # interpretsUntaggedImageDataAsGeneric, ... } }. We resolve the
                # data_id → on-disk filename and emit a CSS background-image
                # url. The asset is referenced via assets/_shared/ so build.py
                # only needs to stage the file once per deck.
                img = fill.get("image")
                if img and isinstance(img, dict):
                    img_ref = img.get("data") or img.get("imageData") or {}
                    data_id = img_ref.get("identifier") if isinstance(img_ref, dict) else None
                    if data_id:
                        fn = data_id_to_filename.get(data_id)
                        if fn:
                            # We mark this with a sentinel prefix so build.py
                            # recognizes it as an image fill (needs staging).
                            # CSS form is `url('...') center/cover no-repeat`.
                            return f"__SLIDE_BG_IMAGE__:{fn}"
                return None

            # For each slide, look up its style.identifier from KN.SlideArchive.
            for slide_no, arch_id in enumerate(slide_arch_order, 1):
                iwa_name = slide_iwa_file.get(arch_id)
                if not iwa_name:
                    continue
                try:
                    sd = IWAFile.from_buffer(o.read(iwa_name)).to_dict()
                except Exception:
                    continue
                style_id = None
                for chunk in sd.get("chunks", []):
                    for ar in chunk.get("archives", []):
                        for obj in ar.get("objects", []):
                            if obj.get("_pbtype") == "KN.SlideArchive":
                                style_id = (obj.get("style") or {}).get("identifier")
                                break
                if not style_id:
                    continue
                fill = _resolve_slide_fill(style_id)
                if not fill:
                    continue
                css = _fill_to_css(fill)
                if css:
                    slide_bgs[slide_no] = css

        return cls(assets, text_aligns, shape_fills,
                   master_bboxes=master_bboxes, slide_bgs=slide_bgs)


def _bbox_score_xywh(ax: float, ay: float, aw: float, ah: float,
                     bx: float, by: float, bw: float, bh: float) -> float:
    """IoU-ish bbox overlap; positive on overlap, negative-distance otherwise."""
    inter_w = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    inter_h = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = inter_w * inter_h
    if inter == 0:
        acx, acy = ax + aw / 2, ay + ah / 2
        bcx, bcy = bx + bw / 2, by + bh / 2
        return -(((acx - bcx) ** 2 + (acy - bcy) ** 2) / 1e6)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _bbox_score(a: _Asset, x: float, y: float, w: float, h: float) -> float:
    return _bbox_score_xywh(a.x, a.y, a.w, a.h, x, y, w, h)


# ----------------------------------------------------------------------------
# Opener abstraction so the .key zip and (legacy) directory bundle share a
# single read-by-name interface.
# ----------------------------------------------------------------------------

class _ZipOpener:
    def __init__(self, p: Path):
        self.p = p

    def __enter__(self):
        self._zf = zipfile.ZipFile(self.p)
        self._names = set(self._zf.namelist())
        return self

    def __exit__(self, *exc):
        self._zf.close()

    def read(self, name: str) -> bytes:
        return self._zf.read(name)

    def namelist(self) -> list[str]:
        return list(self._names)


class _DirOpener:
    def __init__(self, p: Path):
        self.p = p

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def read(self, name: str) -> bytes:
        return (self.p / name).read_bytes()

    def namelist(self) -> list[str]:
        return [str(f.relative_to(self.p)) for f in self.p.rglob("*") if f.is_file()]
