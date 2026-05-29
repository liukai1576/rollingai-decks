---
name: thumb-gen
kind: [管理分析]
version: "0.3"
input:  slides.db (rows pointing at rendered deck output dirs)
output: 480×270 JPG per slide under library/db/data/thumbs/<deck_id>/<slide_key>.jpg
triggers:
  - "生成缩略图"
  - "thumbnails"
  - "regen thumbs"
invocation: |
  python3 library/db/gen_thumbnails.py [--deck <id>] [--only <slide_id>] [--force]
requires:
  - macOS Chrome at /Applications/Google Chrome.app
  - "pip: websocket-client Pillow"
---

# thumb-gen

Drives headless Chrome over CDP (Chrome DevTools Protocol) to render
each slide once into a 480×270 JPG. One persistent Chrome instance per
run, one tab per deck; for each slide it flips `location.hash`, waits
for `.slide-frame.is-current` to settle on the target `data-slide-key`,
captures.

Steady-state cost: **~1.3s/slide** (the deck's JS still has to parse
the full DOM each tab, but subsequent slides reuse the loaded deck).

CSS for `.deck-ui`/`.nav-hint` is injected to hide the player chrome
in the thumbnail (no "翻页·F全屏" tab, no page indicator).

## When to invoke

- After `deck-ingest` for a new deck
- After `slide-redesign` / `slide-design` changed slide content
- When admin UI shows "无缩略图" placeholders

## Flags

- `--force` regenerate even if JPG already exists
- `--deck <id>` limit to one deck
- `--only <slide-id>` (e.g. `kangshifu/slide-004`) — single slide

## See also

- `platform/admin/server.py` serves thumbs at `/thumbs/<deck_id>/...`
