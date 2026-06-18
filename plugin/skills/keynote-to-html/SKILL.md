---
name: keynote-to-html
display_name: Keynote 转 HTML
author: liukai
kind: [创建]
version: "0.22"
input:  Apple .key file (path)
output: deck output dir (deck.json + index.html + assets/ + history.json)
triggers:
  - "把 Keynote 转成 HTML"
  - "import keynote"
  - ".key 转 deck"
  - "用户提供 .key 文件路径"
  - "用户在 Keynote 中打开了一个文档"
invocation: |
  bash plugin/skills/keynote-to-html/assets/run.sh \
    "<path-to-.key>" "<output-dir>" [--limit N]
requires:
  - macOS + Keynote Creator Studio (com.apple.Keynote)
  - "pip: PyMuPDF Pillow keynote-parser"
appends_history: true
description: |
  Convert an Apple Keynote (.key) presentation into a deck.json + HTML deck
  by walking the presentation slide-by-slide and reconstructing each slide as
  positioned HTML — images stay as <img>, text becomes editable HTML text,
  videos become <video>. Triggers: "把 Keynote 转成 HTML", "import keynote",
  ".key 转 deck", or when the user hands over a .key file path / a Keynote
  document opened on their machine.

  Per-slide algorithm:
    1. AppleScript walks every iWork item on the slide → emits (type, position,
       size, file name, text content, font / size / color).
    2. For images, file references are resolved against the .key bundle's
       Data/ directory: exact prefix match first; falls back to dimension /
       aspect-ratio match for ambiguous "pasted-image.pdf" cases.
    3. Each non-text element becomes an <img>/<video> at the original (x, y, w, h).
       Each text becomes a real HTML <h1/h2/div/li> with the original font + size.
    4. The slide is emitted as a `layout: "raw"` entry in deck.json.
    5. feishu-deck-h5's render-deck.py wraps everything in present-mode chrome.

  Lossy / acceptable failures (do NOT block on these):
    · Custom Keynote fonts (HarmonyOS / Alibaba PuHui / 方正兰亭) fall back to
      web-safe Chinese stacks (PingFang SC, Microsoft YaHei).
    · 1-2 ambiguous pasted-image files may match the wrong source — log and continue.
    · Master-slide background inheritance is not yet resolved (best-effort).
    · Animations / build effects are dropped (intentional — HTML doesn't need them).
---

# keynote-to-html

## When to invoke

Trigger when the user has a `.key` file (or a Keynote presentation already
open in Keynote Creator Studio) and wants an HTML version that:

  - Looks ≥ 95% identical to the original Keynote rendering
  - Has editable text (HTML elements, not pixels)
  - Has playable videos (where the original had video; positioning extracted
    via AppleScript movie items)
  - Carries feishu-deck-h5's present-mode chrome (left/right keys, F fullscreen,
    bottom controls, progress bar)

Do NOT use this skill for:
  - PDF input (use a PDF-only fallback; .key has structured data the PDF lost)
  - Producing a "redesigned" deck (use the deck authoring path with manual
    deck.json — this skill is a faithful 1:1 converter)

## Preflight

1. Verify `.key` file exists and is openable. If user gave only a name (not a
   path), Spotlight-search via `mdfind "<name>"`.
2. `pip install PyMuPDF Pillow keynote-parser` — needed for PDF→PNG
   conversion, image dimension probing, and IWA-based deterministic
   asset/alignment resolution. Skip if already installed.
3. Confirm **Keynote Creator Studio** (v15+, bundle id `com.apple.Keynote`)
   is installed. The plain "Keynote" v14 (`com.apple.iWork.Keynote`) is the
   older app — extract.applescript pins to the new bundle for consistent
   behavior. If only the old one is available, edit the bundle id at the
   top of extract.applescript and run.sh.
4. Confirm the feishu-deck-h5 skill is reachable. Default lookup is
   `../feishu-deck-h5/` (sibling skill in `plugin/skills/`); override via
   `--renderer <path>` flag.
5. **Fingerprint probe**. Before launching Keynote (which is slow), run
   a pure-IWA fingerprint pass against the library DB so the user knows
   which slides already exist as verbatim copies / template reuse /
   fuzzy-text matches in other decks:
   ```bash
   python3 library/db/collect_fingerprints.py --probe "<path-to-.key>"
   ```
   No Keynote, no AppleScript — just unzip the `.key` and walk each
   `Slide-*.iwa`. The report flags per-page matches against `slides.db`.
   Show this report to the user before the slow path.

## End-to-end flow (with user-confirmation gate)

The slow steps are (a) AppleScript extract (~30s per slide for big decks)
and (b) per-slide raster fallbacks. Always:

1. **Preflight**: deps + fingerprint probe (above). Surface the probe
   report. Skip this entirely only if the user said so.
2. **Extract**: run AppleScript on the WHOLE deck (cheap relative to the
   rest, and we need extracted titles to label the selection list).
3. **Confirmation gate (REQUIRED)**: After extract.tsv is written, parse
   it (or read the deck.json that build.py would produce in dry-run mode)
   and present a numbered list of slides with their titles + fingerprint
   match status. Ask the user which slides to actually convert. Default
   on no answer = "all of them". Examples of valid replies:
     · `all` — convert everything
     · `1,3,5-8,12` — explicit list
     · `skip 4,7` — convert all except these
   Pass the result through to `build.py --slides 1,3,5-8,12`.
4. **Build + render**: run build.py with `--slides` filter. Only the
   selected slides are composed into HTML + assets.

Do NOT skip step 3 unless the user explicitly says "convert all".

## Invocation

```bash
bash plugin/skills/keynote-to-html/assets/run.sh \
  "<path-to-.key>" \
  "<output-dir>" \
  [--limit N]              # only convert first N non-skipped slides
  [--renderer PATH]    # path to renderer skill (default: ../feishu-deck-h5/)
  [--rasters-dir DIR]      # per-page PNG dir for fallback crops (slide-NN.png)
  [--pdf PATH]             # source PDF for on-demand fallback rasterization
  [--redesigns DIR]        # dir with slide-NN.html HTML overrides (1-based PDF page)
```

### Redesign overlays — `--redesigns DIR`

`--redesigns DIR` is kept for backward compatibility but is **no longer the
canonical way to redesign slides**. The redesign workflow now lives in the
dedicated **`slide-redesign`** skill, which can be applied to ANY deck.json
(not just Keynote imports). The canonical pipeline is:

```bash
# 1. Import Keynote → deck.json
bash run.sh customer.key out/

# 2. Redesign selected slides
bash plugin/skills/slide-redesign/assets/apply.sh \
  out/deck.json  out/redesigns/

# 3. Re-render
python3 plugin/skills/feishu-deck-h5/deck-json/render-deck.py \
  out/deck.json  out/
```

See `plugin/skills/slide-redesign/SKILL.md` for the full rules on writing
`redesigns/slide-NN.html` files (verbatim text content, PPT-feel canvas
filling, data-slide-key scoping, etc.).

### Raster fallback — `--rasters-dir DIR` / `--pdf PATH`

Provide either `--rasters-dir` OR `--pdf` (or neither) to enable raster
fallback. When enabled, any element type we can't structurally reconstruct
(lines, charts, tables, vector masks, shapes with no extractable fill) gets
cropped from the rasterized page PNG and embedded as an `<img>` — so the
visual lands even when the structural extraction can't.

The skill opens the .key in Keynote Creator Studio, drives an AppleScript that emits
per-slide TSV element data to `<output-dir>/extract.tsv`, copies/converts
matched assets into `<output-dir>/assets/slide-NN/`, builds a DeckJSON-format
`deck.json`, and calls the renderer's `render-deck.py` to produce `index.html`.

The .key file stays untouched. The Keynote Creator Studio document opens read-only.

## Pipeline files

| File | Role |
|---|---|
| `assets/extract.applescript` | Drives Keynote Creator Studio; emits TSV with one row per (slide, element) |
| `assets/build.py` | Parses TSV → matches images → composes positioned HTML → writes deck.json → invokes feishu-deck-h5 render |
| `assets/run.sh` | Bash entry point |

## Verifying

After a run, do these by hand:

  - Open `<output-dir>/index.html` in a browser
  - Try ← → arrow keys → page navigation works
  - Try F → fullscreen present mode
  - Pick a text element → DevTools → edit it → the rendered slide updates
  - Compare side-by-side with the original Keynote — flag pages where layout
    drifted noticeably (text overlaps an image, image cropped wrong, font way
    off). Most drift is fixable by tweaking the AppleScript-reported
    position / size, OR by adjusting the image-match heuristic.

## Known limitations (v0.13)

  - Rich text runs: **SUPPORTED since v0.16** (this note used to say runs
    collapse — that's no longer true). `extractTextRuns` in
    extract.applescript walks the text character-by-character and emits a
    `RUN` record whenever font / size / color changes; build.py renders each
    run as its own inline `<span>` (per-run font / size / color / weight). So a
    single box like "1.5亿" (96px "1.5" + 64px "亿") or "节省 90%" keeps each
    run's styling. Residual caveat: the scan is AppleScript-driven (per-char
    `font/size/color of character i`), which is reliable for common fonts but
    can occasionally misread per-char style for unusual custom fonts. The
    deterministic hardening is to read the run structure from the IWA archive
    (TSWP CharacterStyle) the same way iwa_resolver reads images — not yet
    wired, do it if a real deck shows wrong per-run styling. Paragraph
    alignment is already IWA-sourced (iwa_resolver `text_aligns`).
  - Shape corner radius: AppleScript doesn't expose Keynote's corner-radius
    property cleanly. We apply a heuristic (pill if h<200 & 1.5<aspect<6;
    rounded box otherwise) — covers most cases but not bespoke radii.
  - Vector lines & arrows: emitted as raster crops via fallback (or skipped
    if no fallback). Lines have h=0 which makes structural rendering moot;
    crops carry the visual.
  - Charts / tables: not structurally parsed. Use raster fallback to ship the
    visual.
  - Auto-shrink-to-fit text: Keynote may visually shrink text to fit its
    box. AppleScript reports the AUTHORED font size, not the displayed size.
    Text that overflows in HTML may not match the original — fix by editing
    the HTML font-size, or by enabling text-overflow handling in the future.
  - Master slide background images: only the master's background COLOR is
    extracted. Master background images / gradients fall back to the color
    or to #000.

Known issues (v0.13; under active development):
  - Auto-shrink-to-fit text: DISABLED per user direction (2026-05). The
    skill always honors the authored Keynote font size. If displayed text
    overflows its bbox in the browser, it wraps naturally; users edit the
    rendered HTML if they need a different size. (Previously v0.6–v0.12
    tried various char-width heuristics; they were too inaccurate to
    reliably differentiate "intentional auto-shrink" from "just fit".)
  - Image cropping inside Keynote (`crop bounds`) not extracted — Keynote
    14.5 closes off `crop bounds` / `image scale` / `image offset` to
    AppleScript automation. We render the full source image inside the
    bbox via `object-fit: cover`. For images that Keynote was cropping to
    show only a sub-region (e.g. slide 21's circuit-board HUD), this
    causes a visually different (typically brighter) result. Would
    require parsing the .key bundle's IWA archive — out of scope for v0.13.
  - Image rotation extracted; perspective / flip transforms not captured.
  - Shape fill: gradient / advanced-gradient / image-fill shapes don't
    expose their color via AppleScript. shape+image bbox pairing falls
    back to a raster crop when there's an image at the same bbox; the
    shape's visual is otherwise lost.
  - Master background-fill (color or image set via the master's `background
    fill type`) doesn't expose reliably via AppleScript. Master iWork
    items (images, shapes, text) ARE extracted; placeholder text (e.g.
    "幻灯片标题" / "正文级别 1") is filtered out.

Known fixed in v0.13:
  - Opacity not applying on first slide (the renderer's `.deck:not(
    [data-nav-armed]) .slide-frame:first-child .slide > * { opacity: 1
    !important }` rule was overriding our inline opacity) — fixed by
    emitting our opacity with `!important`.
  - Slide bg color mis-detected as white when master placeholder text
    had black color (master `正文级别` shapes) — bg heuristic now skips
    master elements.
  - Rotation `transform: rotate(...)` was killed by our anti-flash
    `transform: none !important` — fixed by emitting rotation with
    `!important` so it survives the override.
  - Master placeholder text ("幻灯片标题" / "正文级别 1\n2…" / "Subtitle")
    being rendered as if real content.

The skill is designed to grow per-page as edge cases surface from real decks.
