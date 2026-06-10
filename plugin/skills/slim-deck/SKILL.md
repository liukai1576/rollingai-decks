---
name: slim-deck
display_name: Deck 瘦身
author: liukai
kind: [管理分析]
version: "0.3"
input:  a deck project directory (containing render-output-full/, optionally media/, source.pdf, redesigns/, etc.)
output: "same directory, slimmed: deck made self-contained, orphans + cache + external sources removed"
triggers:
  - "瘦身这个 deck"
  - "清理孤儿 asset"
  - "slim this deck"
  - "去掉 .cache 和 source.pdf"
  - "把 media/ 里被引用的图搬进去，然后把 media/ 删掉"
invocation: |
  bash plugin/skills/slim-deck/assets/run.sh <deck-project-dir> [--dry-run] [--keep-source]
description: |
  Takes a deck project directory and slims it to the minimum
  shippable bytes, in this order:

  1. **Absorb external refs**: scan every <src>/<href>/<poster>/<data-src>
     in deck.json + index.html. Anything pointing OUTSIDE
     render-output-full/ (relative `../...`, absolute paths) is resolved,
     the actual file is copied into render-output-full/assets/_shared/,
     and the ref is rewritten to that local path. After this the deck is
     genuinely self-contained.
  2. **Orphan sweep**: delete files under render-output-full/assets/ that
     no slide HTML or index.html references.
  3. **Cross-slide dedup**: SHA-256-group every remaining asset; any
     file that appears in two or more slide dirs is moved to
     assets/_shared/<basename> and all refs are rewritten.
  4. **Build artifacts**: drop `.cache/`, `extract.tsv`, `deck.json.bak`.
  5. **External sources**: with the deck now self-contained, the
     project-level `media/`, `source.pdf`, and stray `phone-*.png`-style
     files at the project root are no longer needed. Delete them. (Pass
     `--keep-source` to keep source.pdf around for reference.)

  Reports BEFORE → AFTER total size so you see the win.

  Idempotent: re-running on an already-slim deck is a no-op.

  Safe by default: with `--dry-run` it just prints what it would do.
---

# slim-deck

## When to invoke

After a deck has been rendered (via `keynote-to-html`, `slide-redesign`, or
hand-authored) and is "done" for now. Run this before sharing the deck
with a colleague, or before forking the deck for a new customer.

Do NOT run mid-edit — step 5 deletes the original `media/` and
`source.pdf`. If you still need to re-render from scratch, skip slim
until you're done iterating.

## Why it exists

Two recurring problems on Keynote-imported decks:

  · The build pipeline copies every IWA-referenced asset into every
    slide that touches it, leaving many identical files across
    `assets/slide-NNN/` dirs. The `Video (6)-20616.mp4` issue: 6 copies
    of the same 29 MB file in 6 slide dirs = 174 MB on disk.

  · Hand-authored redesign HTMLs reference assets via `../media/...`
    paths that escape the deck dir. The deck looks fine when served
    from the project root, but zipping just `render-output-full/`
    leaves the videos behind → broken videos at the recipient end.

slim-deck fixes both: pulls external refs in, dedupes within, scrubs
build artifacts and source files.

## Pipeline

```
project root
├── render-output-full/
│   ├── index.html         (refs to assets/ + _renderer/)
│   ├── deck.json          (source of truth for slide HTML)
│   ├── assets/
│   │   ├── slide-001/...
│   │   ├── slide-002/...
│   │   └── _shared/       ← step 3 creates this for dedup'd files
│   ├── _renderer/         (not touched)
│   ├── .cache/            ← step 4 deletes
│   ├── extract.tsv        ← step 4 deletes
│   └── deck.json.bak      ← step 4 deletes
├── media/                 ← step 1 pulls used files in; step 5 deletes
├── redesigns/             (not touched — source for re-build)
├── source.pdf             ← step 5 deletes (unless --keep-source)
└── phone-li.png, ...      ← step 5 deletes if absorbed
```

## Verifying

After running, open `render-output-full/index.html` and click through
every slide. Every image / video / icon should still display. If
anything is broken: the source file lived in a location slim-deck
didn't detect — file a one-line note here so the path resolver can
learn that location too.

## Flags

  · `--dry-run` — print the plan, don't touch anything.
  · `--keep-source` — keep `source.pdf` at the project root (the rest
    of step 5 still runs).
  · `--keep-media` — keep the project-level `media/` dir (useful when
    you'll re-render from scratch and still want it).
