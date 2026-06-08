---
name: dedup-probe
display_name: 跨册查重
kind: [管理分析]
version: "0.4"
input:  one source deck_id + N target deck_ids (in slides.db)
output: library/db/data/UNIFIED-PROBE-<source>.md report
triggers:
  - "看看哪些 slide 在多个 deck 里"
  - "dedup report"
  - "跨 deck 相似度"
invocation: |
  python3 library/db/unified_probe.py <source-deck> <target-deck-1> [<target-deck-2> ...]
---

# dedup-probe

Cross-deck similarity report. Combines 5 channels per source-slide:

1. **iwa_uuid** match — provably the same source slide
2. **element_sig** match — same structure + same text
3. **template_sig** match — same template, possibly different text
4. **text overlap** — Chinese 2-gram tokenization, Jaccard + overlap_coef
5. **asset content hash** — same image/video bytes

Emits a markdown sheet listing every source slide and the most similar
hits in target decks across all channels. Used to:

- Decide what's reusable from an old deck for a new one
- Spot when a slide has drifted from its template's intent
- Build the slide-library's "similar slides" affordance

Pre-requisites: slides for all probed decks must already have
fingerprints (`slide-fingerprint`) and assets (`asset-fingerprint`).

## See also

- `slide-fingerprint`, `asset-fingerprint`
