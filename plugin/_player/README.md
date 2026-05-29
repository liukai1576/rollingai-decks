# plugin/_player/

The deck **player runtime + render dispatcher**. Common code that every
layout pack relies on, so each layout pack can stay small and focused on
"how my slides look".

What lives here:

- `render.py` — the entry point for "given a deck.json, produce an
  output directory". Reads `deck.layout_pack` from deck.json, looks up
  the pack under `plugin/skills/<id>/`, calls that pack's render entry
  (declared in its `pack.json`).
- `chrome.js` *(planned)* — page navigation, keyboard handling, scale,
  hash sync, progress bar, idle fade. Shared across all layout packs.
- `base.css` *(planned)* — the `.slide-frame` 16:9 box + scaling rules,
  plus `data-role` semantic helpers. Layout pack CSS is layered on top.

## Contract for layout packs

Each layout pack is a skill under `plugin/skills/<id>/` with a
`pack.json` at its root:

```json
{
  "id": "feishu-deck-h5",
  "render_entry": "deck-json/render-deck.py",
  "css": ["assets/feishu-deck.css"],
  "js":  ["assets/feishu-deck.js"],
  "layouts": [
    { "name": "raw",           "data_schema": { "html": "string" } },
    { "name": "cover",         "data_schema": { "title": "string", "subtitle": "string" } },
    ...
  ]
}
```

`render_entry` is invoked with positional args `<deck.json> <output_dir>`.
The pack is responsible for emitting `index.html` (and any per-slide
assets it needs) into the output dir.

## Why this exists

Without it, every layout pack would fork the chrome JS / nav handling
/ scaling — bug fixes have to land in every pack. With it, those live
once, and a layout pack only ships its CSS + per-layout HTML fragments.

See `plugin/_spec/deck-json-v2.md` for how `deck.layout_pack` is wired.
