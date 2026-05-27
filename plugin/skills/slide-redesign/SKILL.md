---
name: slide-redesign
description: |
  Replace one or more slides in an existing deck.json with hand-authored HTML.
  Use this when an imported or auto-generated slide doesn't render well in
  position-faithful mode and needs a custom layout (heavy tables, dashboards,
  card grids, custom hero pages).

  Inputs:
    · deck.json   — any DeckJSON (from keynote-to-html, slide-design, or hand-authored)
    · redesigns/  — directory of slide-NN.html files (1-based PDF page number,
                    OR slide-key — both supported; see SKILL.md body)
  Output:
    · deck.json (same path or new) with the targeted slides converted to
      `layout: raw` using the user-provided HTML body.

  Common triggers: "redesign slide 24", "替换第 26 页布局", "这页用 HTML 重写",
  or "改造这几页".

  Decoupled from keynote-to-html: the same redesign workflow works for any
  deck.json source. This is the right skill to invoke after a Keynote import
  identifies pages that don't translate well.
---

# slide-redesign

## Role in the architecture

```
   ┌────────────────┐
   │ existing       │
   │ deck.json      │ ─┐
   └────────────────┘  │
                       ├──> slide-redesign ──> updated deck.json
   ┌────────────────┐  │                       (selected slides
   │ redesigns/     │ ─┘                        replaced)
   │  slide-24.html │
   │  slide-40.html │
   │  ...           │
   └────────────────┘
```

The output is still a normal deck.json — pass it to **rolling-deck-h5** to
render to HTML.

## When to invoke

Trigger when:
  - The user has an imported deck (from keynote-to-html or similar) and
    points to specific pages that look wrong / cramped / unrepresentative.
  - The user wants to "re-author" specific slides with a cleaner layout
    while keeping everything else as-is.

Do NOT use this skill for:
  - Building a brand-new deck from scratch (use **slide-design** instead).
  - Fixing extraction bugs systematically across many slides (file an issue
    against **keynote-to-html** or whichever generator produced the deck).

## Redesign HTML rules (MANDATORY — apply equally regardless of source)

These rules govern any HTML file dropped into `redesigns/`. Same rules whether
the slide came from a Keynote import or a hand-authored deck.

1. **TEXT CONTENT MUST BE VERBATIM.** If replacing an imported slide, copy
   every visible text string verbatim from the source data (TSV for Keynote
   imports, original deck.json for hand-authored). NEVER invent body copy,
   captions, descriptions, label text. NEVER paraphrase. Reordering OK;
   rewording is not. If a card has a quote, copy the quote — don't substitute
   a "more explanatory" sentence.

2. **DON'T add visual elements that weren't authored.** No invented icons,
   arrow indicators, decorative emojis, unless the source slide had them.

3. **Match the slide's data-slide-key.** The wrapper is
   `<div class="slide" data-slide-key="slide-NNN" ...>` where NNN is the
   ZERO-PADDED slide key from the input deck.json. Scope all your CSS via
   that exact selector or other slides will pick up your styles.

4. **Decorative liberties OK**: layout (grid vs absolute), color theme,
   spacing, typography choices, card visual style, divider treatments,
   hover effects, animations — all editorial decisions you can make to
   improve presentation. The CONTENT is fixed; the PRESENTATION is yours.

5. **FILL THE 1920×1080 CANVAS — feel like a PPT, not a webpage.** The
   redesigned slide must occupy the full canvas with strong typographic
   presence. Targets:
     - Title font ≥ 56–88px; subtitle ≥ 28–40px; body ≥ 20–28px.
     - Content extends to ≥ 80% of canvas width AND ≥ 70% of canvas height.
     - Padding 56–96px from the canvas edges.
     - Images / cards / dashboards SCALE UP to fill.
   A redesign that occupies only 1/2 or 1/3 of the canvas is WRONG — fix
   the proportions before declaring done.

## File format

Each `redesigns/slide-NN.html` contains:

```html
<!--
  Slide NN · "<title>"
  Source: content verbatim from <provenance>.
-->
<style>
  .slide[data-slide-key='slide-NNN'] { background: ...; ... }
  .slide[data-slide-key='slide-NNN'] .my-class { ... }
</style>

<h1 class="...">VERBATIM TITLE</h1>
... rest of body ...
```

## Invocation

```bash
bash plugin/skills/slide-redesign/assets/apply.sh \
  <input-deck.json> \
  <redesigns-dir> \
  [<output-deck.json>]
```

If `<output-deck.json>` omitted, the input is updated in place (with a
`.bak` backup created next to it).

## Pipeline file

| File | Role |
|---|---|
| `assets/apply.py` | Load deck.json, replace targeted slides with HTML from redesigns dir, write deck.json |
| `assets/apply.sh` | Bash wrapper |

## Verification

After `slide-redesign` runs, follow up with `rolling-deck-h5` to render
HTML and visually verify each redesigned slide.
