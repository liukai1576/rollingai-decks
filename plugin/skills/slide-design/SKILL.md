---
name: slide-design
kind: [创建, 构思]
version: "0.5"
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

## Pipeline files (placeholder)

| File | Status |
|---|---|
| `assets/draft.py` | not yet written — will turn a prompt → slide entry |
| `assets/append.py` | not yet written — will append a slide to existing deck.json |

These will be implemented when the RollingAI design tokens / layout
inventory finalize.
