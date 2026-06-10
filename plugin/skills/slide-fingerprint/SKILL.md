---
name: slide-fingerprint
display_name: 幻灯片指纹
author: liukai
kind: [管理分析]
version: "0.4"
input:  deck_id + path to original .key bundle
output: slides.db rows get iwa_uuid + element_sig + template_sig filled
triggers:
  - "给 slide 打指纹"
  - "extract slide fingerprints"
  - "找出哪些 slide 是同一张"
invocation: |
  python3 library/db/collect_fingerprints.py <deck_id> <path/to/.key>
requires:
  - "pip: keynote-parser"
---

# slide-fingerprint

Walks a `.key` bundle's IWA archives to extract three identity signals
per slide:

- **`iwa_uuid`** — internal Keynote object ID. Stable across "duplicate
  slide" operations, so two slides with the same UUID are provably the
  same source.
- **`element_sig`** — strict structural + asset + text-storage-id hash.
  Two slides with the same `element_sig` differ only in re-renderings
  with literally the same content.
- **`template_sig`** — loose: structure + assets only, **ignores text**.
  Detects "same template, different content" (e.g. case-card slides
  with the same layout but different customer names).

Writes them onto the existing `slides` rows (matched by `slide_key`).

## When to invoke

- After `deck-ingest` for a new deck, when you have the original `.key`
- To find near-duplicate slides across decks (combined with `dedup-probe`)

## See also

- `dedup-probe` — cross-channel similarity report
- `asset-fingerprint` — image / video binary hashing
