# RollingAI Deck plugin — CHANGELOG

All changes are committed to the skill source files under `plugin/skills/`.
This file consolidates per-version notes from `build.py`, `extract.applescript`,
and `feishu-deck.js`, plus per-skill architectural changes. Reverse chronological.

## v0.16 — current (multi-run text, doc-name targeting, lazy-video, architecture split)

### Skill structure
- **Plugin split into 4 decoupled skills** (replaces single skill):
  - `feishu-deck-h5` — renderer + design system (forked from feishu-deck-h5)
  - `keynote-to-html` — `.key` → `deck.json` import only (no redesign)
  - `slide-redesign` — apply HTML overrides to any `deck.json`
  - `slide-design` — scaffold for authoring new slides (scripts deferred)
- Common intermediate format: `deck.json` (DeckJSON schema). Each skill consumes or produces this.
- Top-level `plugin/README.md` documents the architecture.

### `keynote-to-html` / `extract.applescript`
- **Document-name targeting**: `--doc-name` argv (3rd). When multiple Keynote
  docs are open, AppleScript was hitting whichever was `front document` —
  not necessarily ours. Now `run.sh` passes the .key basename explicitly.
- **Per-run text extraction** (multi-font/size/color within one text box):
  walks character-by-character, detects style transitions, emits `RUN`
  records after each `ITEM` for `text` / `shape` elements with non-uniform
  styling. Cheap first-vs-last char comparison gates the slow scan.
- **Master suppression fix**: master image only suppressed when slide has
  its OWN full-bleed bg image. Previously oversized master images were
  unconditionally hidden, breaking slides like PDF 5 where the master's
  `up@2x.png` is the intended visible background.

### `keynote-to-html` / `build.py`
- **`.key` zip auto-detect**: Keynote 14.5+ saves single-file zipped `.key`.
  Build.py opens as zip and extracts `Data/` to `<output>/.cache/Data/` on
  first run; reuses cache on subsequent runs. Previous code only handled
  the older directory-bundle format.
- **UTF-8 zip filename fix**: Keynote stores Chinese filenames as UTF-8 but
  doesn't set the language-encoding flag bit, so Python's `zipfile` defaults
  to CP437 and mojibakes the names. Now decodes with `cp437→utf-8` recoding
  when the flag bit is unset. Restored 100+ missing Chinese-named assets.
- **Auto poster frames for videos**: every emitted `<video>` element gets
  a paired first-frame `.poster.jpg` extracted via PyAV. Browsers show
  this when autoplay is blocked.
- **Lazy-video markup**: emit `<video class="lazy-video" data-src="..."
  preload="none">` instead of pre-loaded `src`. Browser no longer decodes
  all 62 videos on page load.
- **Per-run text rendering**: `_render_text_runs()` emits `<span>` per
  `Element.runs` entry with individual font/size/color/weight. Single-run
  text falls through to original block render.
- **Multi-run shape layout**: shape with multi-run text uses
  `display: block` (so `<span>`s flow as inline text with `<br>` line
  breaks). Single-run shape keeps `display: flex` for clean centering.
- **Multi-run skips fit-to-box**: `fit_font_to_box()` only runs for
  single-run text. Multi-run uses each run's authored size verbatim.
- **`--renderer PATH` flag** (replaces `--feishu-skill`): defaults to
  `../feishu-deck-h5/`; decoupled so any compatible renderer works.
- **`--redesigns DIR` deprecated**: redesign now lives in the
  `slide-redesign` skill; kept for backward compatibility.

### `feishu-deck-h5` (forked from feishu-deck-h5)
- **Lazy-video JS** (new top-level IIFE in `feishu-deck.js`): polls
  `.slide-frame.is-current`, attaches `src` only within ±1 slide of
  current, removes `src` when out of range. Frees decoder slots; deck
  with 22 lazy videos is now smooth.
- **Auto-unmute on user engagement**: videos start `muted` (for autoplay
  reliability). Any `keydown` / `click` / `touchstart` flips a flag;
  subsequent slide navigation plays current video unmuted. Falls back
  to muted if browser still rejects play().
- **Fix**: lazy-video IIFE moved out of the mobile-only (`max-width: 900px`)
  IIFE. Previously was inside a guard clause and never ran on desktop.
- **raw layout**: `<div class="wordmark"></div>` removed (was painting a
  飞书 logo via background-image even when content was empty).
- **CSS override in raw slides**: `.slide > * { animation: none !important;
  transform: none !important; opacity: 1; }` so per-element inline opacity
  is honored. Previously feishu's stagger-reveal animation forced
  `opacity: 1`, silently overriding all our inline opacity values.

### `slide-redesign` (new skill)
- Extracted from `keynote-to-html --redesigns DIR`.
- `apply.py` takes a `deck.json` + a `redesigns/` dir and writes a new
  `deck.json` with targeted slides replaced (`.bak` backup).
- Filename conventions: `slide-NN.html` for PDF-page index, OR
  `slide-NNN.html` (zero-padded) for slide-key match.
- `SKILL.md` documents the **mandatory redesign rules**:
  1. Text content VERBATIM from source (no editorial additions).
  2. No invented icons / emojis / arrows.
  3. CSS scoped via exact `data-slide-key="slide-NNN"` selector.
  4. Decorative liberties OK (layout / color / typography).
  5. **PPT-feel** — must fill 1920×1080 canvas. Title ≥ 56-88px;
     content extends ≥ 80% width AND ≥ 70% height.

### Bug fixes
- `--feishu-skill` → `--renderer` rename (path resolution).
- `run.sh`: `EXTRA_ARGS[@]:-` default to survive `set -u` with empty array.
- `run.sh`: poll for Keynote document load before extracting (large `.key`
  files take seconds to open).
- `extract.applescript`: `set rotation` → `set rotDeg` (reserved word).
- Shape rendering: `is_translucent` check uses `css_opacity` for both
  rgba alpha and inline `opacity:` (consistent).
- `opacity: ... !important` so it survives feishu CSS rules with
  `!important` (was overriding our 0.22 → 1.0 silently).

### Verbatim text rule (slide-redesign)
- All text in redesign files MUST come from the original Keynote extract
  (TSV). Earlier slide 24 redesign had editorially-added explanatory
  body copy that wasn't in the original — rule enforces this can't happen
  again.

---

## v0.15

- **Group child positioning fix**: Keynote 14.5 AppleScript returns child
  positions as ABSOLUTE slide coordinates, not relative to group origin.
  Removed the offset addition that was double-shifting children. (Empirically
  verified on slide 60 where group at (119, 542) reported children with
  matching absolute positions.)

## v0.14

- Verified v0.13 fixes propagated. Documentation sync only.

## v0.13

- `fit_font_to_box` is now an identity passthrough (per user direction):
  always honor the authored Keynote font size; never auto-shrink.
- Per-element CSS opacity now has `!important` so it survives feishu's
  `.deck:not([data-nav-armed]) .slide-frame:first-child .slide > *
  { opacity: 1 !important }` rule.
- Slide-bg heuristic now ignores MASTER elements when scanning for "dark
  text". Master placeholder shapes use theme-default black even on dark
  slides; including them caused slide 34 to be flagged as needing a white
  bg (which made our 50%-opacity image appear LIGHTER, not darker).

## v0.12

- "Container shape" handling: shapes with no fill / no text that visually
  CONTAIN other elements (banner/pill/card backgrounds with group children
  inside). Now rendered as default semi-transparent rounded boxes so the
  layout shape is preserved.
- `other:line` elements (Keynote dividers) with h=0 or w=0 render as
  2-pixel hairline divs. Previously they disappeared because raster
  fallback's crop region was invalid for zero-height regions.

## v0.11

- Placeholder text filter: `_PLACEHOLDER_PATTERNS` adds patterns like
  `Presentation Title`, `正文级别 \d+`, `Slide Title`, `Subtitle`,
  `Click to add`, `金句页底图`, etc. AppleScript returns placeholder
  text from masters as if it were content; filter strips it.
- Text alignment: shape with text uses bbox-center heuristic (`_text_align`)
  instead of forcing center. Many Keynote shapes are left-aligned.
- Image rotation extracted and applied via CSS `transform: rotate()`.

## v0.10 — CRITICAL FIX (opacity)

- **Root cause of "videos and bg images render too bright" complaints**:
  feishu-deck-h5's stagger-reveal CSS rule forces `opacity: 1` on every
  direct child of `.slide` via `animation: fs-reveal`. This silently
  overrode all inline opacity values — authored 22% / 30% semi-transparent
  backgrounds were rendering at 100%, making slides look ~3-4x brighter
  than Keynote.
- Fix: override the animation in per-slide inline `<style>` so inline
  opacity is honored.
- `Element.css_opacity` reverted to identity mapping. (Earlier v0.10
  tried gamma 1.8 correction; turned out the real bug was the animation.)

## v0.9

- Master items emitted with `MASTER` record type (vs `ITEM`); build.py
  sets `Element.is_master = True`.
- Master-image suppression: when master image is oversized OR slide has
  own full-bleed image, master is dropped. Matches Keynote's PDF-export
  behavior where master bg placeholder is hidden by slide's own bg.

## v0.8

- Approximate Keynote's "shrink text to fit" via `fit_font_to_box()`
  heuristic. (Later disabled in v0.13 per user direction.)

## v0.7

- Walk master / base-layout items per slide; emit BEFORE slide's own
  items so they render beneath (template backgrounds, footers).

## v0.6

- Opacity extracted from every Keynote item (0–100) and emitted as
  CSS `opacity:` for images / videos / text.
- "No fill" vs "black fill" disambiguated via sentinel (`-1` on fill_r).
- Corner-radius heuristic suppressed for translucent overlays.

## v0.5 — CRITICAL FIX (font-family quoting)

- font-family stack now uses SINGLE quotes around multi-word family
  names. v0.4 used double quotes inside double-quoted style attributes
  — browsers truncated style at the first inner double quote, silently
  discarding `font-weight` / `font-size` / everything past `font-family`.
- AppleScript extract respects `--limit` — stops early instead of
  walking the whole document.

## v0.4

- Font-weight parsing from font name suffix (e.g. `-Bold`, `-Black`,
  `-Light`, `-Medium`, `_SC_Black`) → emits CSS `font-weight:` (100–900).
- Font-style parsing: `-Italic` / `-Oblique` → CSS `font-style: italic`.
- Removed wordmark `<div>` from raw layout (was painting 飞书 logo).

## v0.3

- Detect shape+image pairs at same bbox; render combined as single
  raster crop (recovers Keynote's "stylized image placeholder" visuals
  with gradient fills AppleScript can't access).
- Skip empty shapes overlapping with other elements.
- Slide background heuristic (dark text → white bg).
- `object-fit: cover` for raster images (was `contain`, left letterboxing).

## v0.2

- Render shapes with fill color + best-effort border-radius.
- Per-element rotation via CSS `transform`.
- Per-slide background color from `#SLIDE-META`.
- PNG raster fallback for unhandled elements (when `--rasters-dir`).
- Better image matching: size floor + aspect.
- Skip group container records (children already flattened).

## v0.1 — initial

- AppleScript walks every iWork item, emits TSV.
- build.py composes positioned HTML; calls render-deck.py.
- Image matching by prefix + dimension fallback.
- Pipeline files: `extract.applescript`, `build.py`, `run.sh`.
