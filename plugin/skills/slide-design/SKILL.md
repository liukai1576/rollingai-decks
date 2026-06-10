---
name: slide-design
display_name: 幻灯片设计
author: liukai
kind: [创建, 构思]
version: "0.7"
input:  existing deck.json (optional) + author intent
output: deck.json with new slides appended (or fresh deck.json)
triggers:
  - "我想新加一页"
  - "在 deck 里加一张 slide"
  - "重新设计一张 slide"
  - "从零写一个 deck"
invocation: |
  # Conversational. Claude reads intent, picks layout, fills data, writes slide entry.
  # See body for the two modes (structured layout vs raw HTML).
description: |
  Author NEW slides from scratch and append them to a deck.json (or start a
  new deck). Use this when the user wants a fresh slide that doesn't exist
  in any imported source — e.g. an extra Q4 strategy page added to a
  Kangshifu pitch that came from Keynote import.

  Two authoring modes:
    A. Structured: use a feishu-deck-h5 layout (cover / agenda / section /
       content (3up/2col/blocks/story-case) / stats / quote / image-text /
       table / flow / end). Fill the layout's data fields; renderer applies
       the design system automatically. Best for slides that fit a known
       pattern.
    B. Raw HTML: hand-author the slide body as partial HTML (same format
       slide-redesign accepts). Best for custom layouts.

  Output is one or more new slide entries appended to a deck.json, OR a
  fresh deck.json if starting from scratch. Then renderable via
  feishu-deck-h5.

  Common triggers: "做一张新 slide", "在这个 deck 里加一页讲...",
  "新建一份关于 X 的 deck".
---

# slide-design

> **🚧 Scaffold only.** Pipeline scripts not yet implemented. The skill is
> declared here so its role is reserved in the architecture; the assets/
> dir will hold the authoring tools once the design language for RollingAI
> Deck stabilizes.

## 🛑 STEP 0 — ALWAYS PICK A LAYOUT PACK FIRST (explicit, never inferred)

Before authoring ANY new deck, you MUST ask the user which layout pack to
use and bake the choice into `deck.json.deck.layout_pack`. Two packs are
registered (registry strict-mode enforces this — see `plugin/_player/`):

| pack id           | When to pick it                                                                                                                              |
|---                |---                                                                                                                                            |
| `feishu-deck-h5`  | Default for Keynote/PDF imports + structured business decks. Renderer: `plugin/skills/feishu-deck-h5/deck-json/render-deck.py`. Data-driven via `deck.json` layouts (cover / agenda / section / content / stats / quote / etc.) Each slide is one of the 10 documented layouts. |
| `rolling-deck`    | High-quality single-file client pitch. Particle-earth cover + frosted-glass design tokens + built-in edit/present modes + PDF export. Renderer copies `template.html` and you swap content. Component vocabulary in `plugin/skills/rolling-deck/reference.md` (cards-3 / route-card / goals-grid / approach-grid / tl-weeks / calendar-wrap / synth-band etc.) |

**Rule:** the choice is the user's. Use `AskUserQuestion` with a 2-option
selector (`feishu-deck-h5` vs `rolling-deck`). Do NOT default — past
mistake: silently picked feishu-deck-h5 + hand-rolled CSS + fake logo
for a client pitch that should have used rolling-deck. The user had to
catch it and ask for a redo.

Quick decision tree if uncertain:

- Source is a Keynote / PDF import? → `feishu-deck-h5` (matches
  `keynote-to-html` output).
- New deck from scratch, single-file deliverable to client, pitch-style? →
  `rolling-deck`.
- Adding pages to an existing deck? → use the pack already in
  `deck.json.deck.layout_pack`. Never mix packs inside one deck.

Once picked, the **per-pack authoring rules** below apply.

## 🛑 RULE — Template is NOT a storyline

This is the single most common mistake when authoring with a layout pack
that ships an example deck (e.g. `rolling-deck/assets/template.html` =
"10× Transformation" example with 16 specific slides). Internalize this
before you write a single section:

**What a layout pack provides:**

| ✅ Provides                          | ❌ Does NOT provide |
|---                                  |---                  |
| Visual system (colors, type, glass) | Your content architecture |
| Component vocabulary (cards-3, goals-grid, route-card, approach-grid, tl-weeks, calendar-wrap, synth-band …) | Which components to use, in what order, how many |
| Interaction/animation (cover anim, nav, edit mode, PDF export) | Your page count / chapter order / closing rhythm |
| **Standard pages**: cover, section-head, end | All content pages |

**The correct authoring loop:**

1. Read the user's source material first (brief, SOW, outline, PDF). Map
   out **the source's own storyline** — how many distinct sections, how
   many points per section, what kind of information each point is
   (parallel items? cause/effect? data? timeline? two-sided contrast?).
2. **For each page in the source's storyline,** ask: "what's the
   information shape on this page?" Then pick the component whose shape
   matches:
   - parallel items, 3-5 items → `cards-3` or `goals-grid`
   - 2-way contrast → `approach-grid`
   - timeline/phases → `tl-weeks`
   - data table → `calendar-wrap` + table
   - single big number / headline stats → `hero-stats`
   - chapter break → `section-head`
   - closing punchline → `synth-band`
3. Standard pages get reused verbatim (cover-hero, end).
4. **NEVER** the other way around: don't pick a component first and then
   bend the source content to fill it.

**Anti-patterns to refuse:**

- ❌ "The template's example used `goals-grid` with `lead-card + 4 cards`
  for its goals page, so I'll also use `lead-card + 4 cards` for my goals
  page" — when the source only has 3 goals, do NOT invent goals 4 and 5
  to fit the layout. Use a 3-card `cards-3` instead, or even just a tight
  `section-head` + text.
- ❌ "The template has 16 slides covering 5 chapters, so my deck should
  also be roughly that shape." — your deck is as long as your source is.
- ❌ "The template's chapter 02 was an agenda page, so I'll add an agenda
  page even though the source doesn't have one." — agenda exists only if
  the deck is long enough to need one.
- ❌ Copying the template's narrative beats (e.g. "5 north stars",
  "3 phases", "向内 / 向外") into your content's labels.

**Right mental model:** the template is a **type system + component
library**, not a Word doc to translate-and-fill.

## 🛑 RULE — Match component to information density (vertical fill)

A 1920×1080 slide is **TALL**. Components in the rolling-deck library
are sized for specific information densities — if you pick a component
whose natural fill is denser than your content, the slide leaves a big
black band at the bottom and looks empty. The auto-shrink in `slide-fit`
only DOWN-scales when content overflows; it does NOT UP-scale to fill
empty space. The author has to size content to fit.

**Each component's natural density** (what it's designed for):

| component | expects | use it when |
|---|---|---|
| `hero-stats` | 3-4 big numbers w/ labels | you have headline stats to anchor on |
| `cards-3` (3-col) | 3 items, each 5-8 lines | parallel comparable items |
| `cards-3` (3-col) with 1-2 lines each | ⚠️ underfills → ugly skinny row | don't — switch to `hero-stats` or make cards taller |
| `cards-3` 2-row (6 items) | 6 items, similar weight | rare; usually 5-item layouts read better as 3+2 stretched |
| `goals-grid` (`lead-card + 4`) | 1 hero + 4 supporting, distinct weights | when there's a clear "primary + supporting" structure |
| `approach-grid` (2-col) | 2-way contrast, 4-6 items per side | scope vs deliverables, before vs after |
| `tl-weeks` (4-col strip) | 4 weeks/items per phase | week-by-week timelines |
| `tl-weeks` with 1 item per row | ⚠️ collapses to leftmost 25% | don't — use `cards-3` (3 phases as 3 cards) or `phase-strip` |
| `calendar-wrap` + `<table>` | rows × cols data | the source IS a table |
| `synth-band` / `band` | 1-2 sentences full-width | closing punchline at slide bottom |

**Before authoring each slide, ask three questions in order:**

1. **What's the information shape?** (parallel / contrast / timeline / table / single stat / hero claim)
2. **How many items?** (3 / 4 / 5 / 6 / table-rows / unbounded)
3. **Will the chosen component naturally fill ~60-80% of slide height with this content?** If no, EITHER:
   - swap to a component with a denser natural footprint, OR
   - add a `synth-band` or `band` row below to claim the bottom 1/3, OR
   - vertically center the component block, OR
   - beef each card (larger padding, bigger headline, longer body) until it fills

**The empty-bottom test:** open the rendered slide in the browser at
1920×1080. If the bottom 30% is pure background with no element in it,
the slide is under-filled — fix the component choice, NOT the content.

**Common rescue patterns** (no content fabrication required):

- 3 items but slide looks thin → switch `cards-3` (short cards) to
  `hero-stats` (big-number cards) or add a `synth-band` below summarizing the three.
- 3 phases but `tl-weeks` is for 4-week strips → use `cards-3` (one card per phase) or write a custom 3-column grid; each phase-card holds 子工作 + 交付物 + 周次 stacked.
- 5 items in `cards-3` 2-row but underfilled → use 3 cards on top + 2 wider cards below with more breathing room (set `grid-template-columns: 1fr 1fr` on the 2-card row), and add `padding: 28px 32px` per card.

**Rationale:** under-filled looks worse than over-filled in this design
system. The glass/metal aesthetic depends on substantial card weight —
thin pancake cards floating in the void read as broken layout.

## Role in the architecture

```
   ┌─────────────────────────┐
   │ user prompt / template  │ ─┐
   └─────────────────────────┘  │
                                ├──> slide-design ──> deck.json
   ┌─────────────────────────┐  │                     (new entries
   │ optional: existing      │ ─┘                      appended OR
   │ deck.json to append to  │                         new deck)
   └─────────────────────────┘
```

The output is a standard deck.json. Render via **feishu-deck-h5**.

## When to invoke

  - User wants to add a brand-new slide to an existing deck.
  - User is starting a deck from scratch with no source Keynote.
  - User says "make me a slide about X" without referring to existing content.

Do NOT use this skill for:
  - Replacing an existing slide that came from import (use **slide-redesign**).
  - Importing a Keynote (use **keynote-to-html**).

## How a slide-design invocation should work (planned)

1. Read existing `deck.json` (if provided) to understand context: brand,
   color theme, existing layouts used, page count.
2. Decide authoring mode:
   - If the requested content fits a known layout → mode A (structured).
   - If it's a custom hero / dashboard / unique composition → mode B (raw).
3. Generate the slide entry and append to `deck.json`'s `slides` array, OR
   create a new `deck.json` if starting fresh.
4. Hand off to user to render via `feishu-deck-h5`.

## Constraints

  - **Match the brand of the deck**: read `deck.deck` metadata and existing
    slide styles to infer color palette / typography. Don't blindly pick
    new colors.
  - **Number slides correctly**: new entries use a unique `key` (e.g.
    `slide-NEW-001`, or pick from the source's numbering scheme).
  - **Same canvas size**: 1920×1080. Same PPT-feel rules from slide-redesign.
  - **🛑 ALWAYS wire the player** when hand-authoring `index.html` from
    scratch (no `render-deck.py`). The deck MUST include, in this order:
    1. `<link rel="stylesheet" href="_renderer/assets/feishu-deck.css">`
    2. `<link rel="stylesheet" href="_renderer/assets/edit-mode/deck-edit-mode.css">`
    3. The boot-check banner (red error banner if JS doesn't init) — see
       `plugin/skills/feishu-deck-h5/assets/boot-check.partial.html`
    4. `<div class="deck" data-layout-pack="feishu-deck-h5">…</div>`
    5. `<script src="_renderer/assets/feishu-deck.js"></script>` before `</body>`
    6. `<script src="_renderer/assets/edit-mode/deck-edit-mode.js" defer></script>`

    After authoring, run the static verifier:

    ```bash
    bash plugin/skills/feishu-deck-h5/assets/verify-deck-shell.sh \
        <deck-output-dir>
    ```

    It MUST print `==> OK: deck shell wiring looks correct.` before the
    deck is considered shippable. Background: a hand-authored deck once
    rendered all slides stacked vertically (no present mode, no scaling,
    no keyboard nav) because the two `<script>` tags were forgotten —
    visually the slides "looked fine" but the player was inert. Defense
    in depth: the boot-check banner makes that exact failure scream
    at-runtime; this verifier catches it at-author-time.

## Pipeline files (placeholder)

| File | Status |
|---|---|
| `assets/draft.py` | not yet written — will turn a prompt → slide entry |
| `assets/append.py` | not yet written — will append a slide to existing deck.json |

These will be implemented when the RollingAI design tokens / layout
inventory finalize.
