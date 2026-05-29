# RollingAI Deck — plugin

Four decoupled skills for building 1920×1080 HTML decks. The common
intermediate format is `deck.json` (DeckJSON schema, see `feishu-deck-h5/
deck-json/deck-schema.json`). Each skill either produces or consumes this
format, so they compose freely.

```
                   ┌───────────────────────────┐
                   │  feishu-deck-h5          │  ← renderer + design system
                   │  deck.json → index.html   │     (forked from feishu-deck-h5)
                   └────────────▲──────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │ deck.json             │ deck.json             │ deck.json
        │                       │                       │
   ┌────┴─────────┐    ┌────────┴────────┐    ┌─────────┴────────┐
   │ keynote-to-  │    │  slide-design   │    │ slide-redesign   │
   │ html         │    │  (scaffold)     │    │                  │
   ├──────────────┤    ├─────────────────┤    ├──────────────────┤
   │ .key → deck. │    │ user prompt →   │    │ deck.json +      │
   │ json (1:1    │    │ new slide entry │    │ redesigns/*.html │
   │ extraction)  │    │ appended to     │    │ → deck.json with │
   │              │    │ deck.json       │    │ slides replaced  │
   └──────────────┘    └─────────────────┘    └──────────────────┘
```

## Skills

### `feishu-deck-h5/` — renderer foundation

Takes a `deck.json` and produces a self-contained HTML deck with
present-mode chrome (← → arrow nav, F fullscreen, progress bar, scroll
mode for mobile).

- Defines the DeckJSON schema (`deck-json/deck-schema.json`).
- Ships layouts (cover / agenda / section / content / stats / quote /
  image-text / table / flow / logo-wall / arch-stack / end / replica / raw).
- Ships present-mode JS (`assets/feishu-deck.js`) and design tokens CSS
  (`assets/feishu-deck.css` — to be rebranded).
- Forked from feishu-deck-h5; rebrand to RollingAI design tokens / logos
  in progress.

```bash
python3 plugin/skills/feishu-deck-h5/deck-json/render-deck.py \
  <input-deck.json> <output-dir>/
```

### `keynote-to-html/` — Keynote import

Imports an Apple Keynote `.key` file via AppleScript + binary asset
extraction, and produces a `deck.json` with one `layout: "raw"` slide per
non-skipped Keynote slide.

```bash
bash plugin/skills/keynote-to-html/assets/run.sh \
  <path-to-.key> <output-dir> \
  [--limit N] [--rasters-dir DIR] [--pdf PATH]
```

After this, the output dir contains `deck.json` (+ `index.html` from
auto-invoked renderer). You can stop here or feed the deck.json into
`slide-redesign` / `slide-design` for further work.

### `slide-redesign/` — selective slide override

Replaces specific slides in an existing `deck.json` with hand-authored
HTML, for layouts that don't translate cleanly from Keynote (dashboards,
custom card grids, hero pages with custom typography).

```bash
bash plugin/skills/slide-redesign/assets/apply.sh \
  <input-deck.json> <redesigns-dir> [<output-deck.json>]
```

Each `redesigns/slide-NN.html` (NN = 1-based PDF page number, OR
zero-padded slide-key) replaces the matching slide in the deck.

### `slide-design/` — new slide authoring (scaffold)

Authors brand-new slides from scratch and appends them to a `deck.json`,
or starts a fresh deck. Pipeline scripts not yet implemented; the skill is
declared so its role is reserved in the architecture.

## Typical workflow

```bash
# 1. Import existing Keynote
bash plugin/skills/keynote-to-html/assets/run.sh \
  customer-pitch.key out/

# 2. Identify pages that need redesign; author them in out/redesigns/
$EDITOR out/redesigns/slide-24.html
$EDITOR out/redesigns/slide-40.html
$EDITOR out/redesigns/slide-55.html

# 3. Apply redesigns (modifies out/deck.json in place, with .bak backup)
bash plugin/skills/slide-redesign/assets/apply.sh \
  out/deck.json out/redesigns/

# 4. (Future) Append a new slide that wasn't in the original Keynote
bash plugin/skills/slide-design/...

# 5. Re-render to HTML
python3 plugin/skills/feishu-deck-h5/deck-json/render-deck.py \
  out/deck.json out/

# 6. Open
open out/index.html
```

## Decoupling design principles

- **Single source of truth: `deck.json`.** Every skill reads or writes it;
  the renderer is the only consumer of the final form.
- **No skill depends on another at runtime** — each ships its own assets
  and scripts. They communicate via the `deck.json` file on disk.
- **Renderer is a flag, not a hard-coded dependency** —
  `keynote-to-html --renderer <path>` defaults to `feishu-deck-h5` but
  any compatible renderer works.
- **Redesigns are content + presentation overrides**, not patches to the
  extractor. If a Keynote import looks bad, you fix it by writing
  `slide-NN.html` (curation work) — not by patching `keynote-to-html`
  (engineering work). This separation keeps the import skill simple and
  the design judgments where they belong (in HTML, not Python).
