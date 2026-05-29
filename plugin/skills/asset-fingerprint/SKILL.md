---
name: asset-fingerprint
kind: [管理分析]
version: "0.2"
input:  deck_id + path to original .key bundle
output: slide_assets table populated with sha256 + dimensions per asset
triggers:
  - "扫一下资产指纹"
  - "asset fingerprints"
  - "找出哪些图是同一张"
invocation: |
  python3 library/db/collect_assets.py <deck_id> <path/to/.key>
requires:
  - "pip: keynote-parser Pillow"
---

# asset-fingerprint

Content-addressed storage hashing for images / videos referenced by a
deck. For each non-template asset (template assets reused on ≥3 slides
in the source deck are filtered out as scenery, see
`TEMPLATE_ASSET_REUSE_THRESHOLD` in `collect_assets.py`), records:

- **`sha256`** — bytes hash, catches binary-identical reuse across decks
- **`pixel_w` / `pixel_h`** — natural dimensions
- **`mime`** — png / jpeg / mp4 / ...
- **per-slide bbox** — where this asset appears (so the same hero image
  used at different sizes on different slides is still detected)

Catches screenshots / photo backgrounds shared across decks that
`slide-fingerprint` would miss because they have different iwork ids.

## When to invoke

- Pair with `slide-fingerprint` to get the full picture
- Looking for "this hero image is reused in 4 decks"

## See also

- `slide-fingerprint` — structural identity
- `dedup-probe` — unified report combining all 5 channels
