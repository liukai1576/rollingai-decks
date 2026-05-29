---
name: deck-ingest
kind: [管理分析]
version: "0.3"
input:  deck_id (slug) + path to deck.json
output: rows in slides.db (slides + slides_fts)
triggers:
  - "把这个 deck 入库"
  - "ingest deck into slides.db"
  - "导入到 slide 库"
invocation: |
  python3 library/db/ingest_deck.py <deck_id> <path/to/deck.json>
requires:
  - sqlite3
  - "pip: beautifulsoup4"
appends_history: true
---

# deck-ingest

Read a rendered deck (`deck.json` + `index.html`) and insert one row per
slide into `library/db/data/slides.db`. Also seeds initial `type_tag`,
`subtype_tag`, `customer_tag`, `media_tag` heuristically from page text
(see `data/STORY-PROPOSAL.md` for the tag convention).

Run **once** per fresh deck. To re-seed tags after content changes,
re-run with the same deck_id (rows are upserted by `slide_key`).

## When to invoke

- Just finished a `keynote-to-html` (or `slide-design`) run
- Need slides visible in admin UI / FTS searchable
- Adding a 2nd / 3rd / Nth deck to the library

## When NOT to invoke

- You only changed display text in admin UI — that already updates DB
- You only want fingerprints / dedup — use those skills instead

## Output convention

Inserts/updates `slides` rows + writes to `slides_fts` (FTS5 full-text
index). `title_source` is set to `extracted` if a clear largest-font
title was found, otherwise `auto-summary`.

## See also

- `library/db/README.md` — tag conventions, tools overview
- `library/db/data/STORY-PROPOSAL.md` — naming / tagging / story rules
