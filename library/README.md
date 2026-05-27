# library/

Truth source for all RollingAI deck stories. Pure filesystem, no DB.

## Layout

```
library/
├── stories/                 ← one folder per story (4-5 page narrative unit)
│   └── <story-id>/
│       ├── story.json       ← metadata + tags + owners (the platform reads this)
│       ├── deck.json        ← DeckJSON spec (renderer input)
│       ├── index.html       ← rendered deck (what users see in a browser)
│       ├── thumb.svg|jpg    ← block-view cover
│       └── pages/           ← (only for replica/imported decks) page rasters
├── shared-assets/           ← cross-story re-usable PNGs / videos / logos
├── business-rules.yaml      ← ingest-gate rules (data, not code)
└── index.json               ← built by `index-build.py` — what platform/ loads
```

## Adding a story

```bash
# 1. Generate or import a deck under runs/<ts>/output/
# 2. Make sure runs/<ts>/output/deck.json has story.id, story.tags
# 3. Run ingest:
python3 plugin/skills/rolling-deck/assets/library-ingest.py \
    runs/<ts>/output/  my-new-story-id
# This copies the folder in, writes story.json, refreshes index.json.
```

## Tag conventions

Format: `<axis>/<value>`. Examples:
- `pillar/product` · `pillar/strategy` · `pillar/case-study`
- `audience/customer` · `audience/investor` · `audience/internal`
- `form/narrative` · `form/data-driven` · `form/quote`
- `length/short` · `length/medium` · `length/long`
- `mood/conclusive` · `mood/exploratory` · `mood/comparison`

Axes are free-form — new ones self-organize in the UI when used.

## Rebuilding the index

```bash
python3 plugin/skills/rolling-deck/assets/index-build.py
```

Run this after any manual edit to `stories/*/story.json`.
