# platform/web

Static React UI for browsing / searching / multi-selecting RollingAI deck stories.

## What it does

- Reads `library/index.json` (built by the skill's `index-build.py`)
- Left sidebar: free text search + tag filters grouped by axis (`pillar/*`, `audience/*`, …)
- Right block view: cards in a dense grid, hover to preview, click thumb to open the rendered HTML in an inline iframe
- Multi-select cards → "复制合并命令" copies a ready-to-run `library-merge.py` invocation to the clipboard

## What it does NOT do (yet)

- **No writes over HTTP.** All mutation (ingest, merge, regenerate) goes through the Skill CLIs. The UI is read-only-over-the-wire by design — that keeps the platform stateless and easy to deploy on a static host
- No auth — internal network, two users only
- No DB — pure file-based, loads one JSON

When we eventually need "click button → server does the merge", we'll add a tiny Node sidecar that exposes a few POST endpoints. For now: CLI is the action layer.

## Dev

```bash
npm install
npm run dev          # → http://localhost:5174
```

The Vite config has a custom middleware that maps `/library/*` to the repo-root `library/` folder, so the React app can `fetch('/library/index.json')` and `<iframe src="/library/stories/.../index.html">` without any copy step.

## Build

```bash
npm run build        # → dist/
```

In production, serve `dist/` and `../library/` from the same nginx (or any static server). Map both under the same origin so the same `/library/*` URLs keep working.
