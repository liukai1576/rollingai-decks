#!/usr/bin/env python3
"""
Generate per-slide thumbnail JPGs by driving headless Chrome over CDP.

Architecture:
  - Spawn one headless Chrome with --remote-debugging-port.
  - For each slide, open a fresh tab, navigate to
    index.html#<slide_key>, wait until JS marks the deck as ready,
    Page.captureScreenshot, downscale to 480×270 JPG, close the tab.
  - Tear Chrome down once at the end.

This amortises the ~10s Chrome cold-start over all 62 slides and
avoids the macOS Google-Updater child-process problem entirely.

Usage:
    python3 library/db/gen_thumbnails.py            # all missing
    python3 library/db/gen_thumbnails.py --force    # regenerate all
    python3 library/db/gen_thumbnails.py --deck kangshifu
    python3 library/db/gen_thumbnails.py --only kangshifu/slide-004
"""
from __future__ import annotations

import argparse
import atexit
import base64
import io
import json
import os
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import websocket  # pip install websocket-client
from PIL import Image

# ---- Paths ----
REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "library" / "db" / "data" / "slides.db"
THUMBS_DIR = REPO / "library" / "db" / "data" / "thumbs"

# Auto-discover from imports/. Legacy DB-id → dir-name aliases (e.g.
# "AI案例分享和AI转型建议-导入" → "AI案例分享") live in the optional,
# gitignored file imports/.deck-mounts.json.
from deck_mounts import discover_mounts  # same package: library/db/

DECK_RENDER_DIRS: dict[str, Path] = discover_mounts(REPO)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Render at 960×540 (2x retina) — paints faster than 1920×1080 and
# is plenty for a 480×270 thumbnail. The deck CSS reads viewport
# dimensions and computes --fs-scale to fit the 1920×1080 slide in.
VIEW_W, VIEW_H = 960, 540
THUMB_W, THUMB_H = 480, 270

# slide_key is interpolated into both a filesystem path AND a JS hash
# expression. Tight allowlist defangs `..`, `/`, null, quote injection.
# The keynote-to-html convention produces `slide-NNN`; hand-authored decks
# may use kebab-case slugs. Both are covered by this pattern.
_SLIDE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DECK_ID_RE = re.compile(
    r"^[A-Za-z0-9一-鿿]"        # first char: ASCII alnum or CJK
    r"[A-Za-z0-9._\-一-鿿]"     # body: same set + . _ -
    r"{0,127}$"
)


# ---- CDP plumbing ----
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Chrome:
    """One headless Chrome instance, driven via Chrome DevTools Protocol."""

    def __init__(self, port: int | None = None):
        self.port = port or _free_port()
        self.tmp = tempfile.mkdtemp(prefix="thumb-chrome-")
        cmd = [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-features=Translate,OptimizationHints,InterestFeedContentSuggestions",
            "--no-pings",
            f"--user-data-dir={self.tmp}/profile",
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--window-size={VIEW_W},{VIEW_H}",
            "about:blank",
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        atexit.register(self.close)

        # Wait for /json endpoint to come up.
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/version", timeout=1
                )
                break
            except Exception:
                time.sleep(0.1)
        else:
            self.close()
            raise RuntimeError("Chrome failed to expose /json/version")

        self._msg_id = 0

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc = None

    # ---- HTTP API ----
    def new_tab(self, url: str = "about:blank") -> dict:
        # Recent Chrome requires PUT for /json/new
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/json/new?{url}", method="PUT"
        )
        return json.load(urllib.request.urlopen(req))

    def close_tab(self, target_id: str) -> None:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/json/close/{target_id}",
                method="GET",
            )
            urllib.request.urlopen(req).read()
        except Exception:
            pass

    # ---- Persistent tab driving one deck ----
    def open_deck(self, url: str, max_wait: float = 20.0):
        """Open a single tab on the deck index.html and wait for it ready.
        Returns a DeckTab handle that can screenshot any slide cheaply by
        flipping location.hash — no need to reload the deck for each one."""
        # Create the tab pointing directly at the target URL — avoids a
        # spurious about:blank → file:// navigation that can race the
        # Runtime.enable handshake on some Chrome builds.
        tab = self.new_tab(url)
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
        self._send(ws, "Page.enable")
        self._send(ws, "Runtime.enable")
        # Lock the viewport to a precise 16:9 box. `--window-size` is just a
        # hint to the OS window; the page's actual innerHeight gets shaved
        # by ~87px on macOS (title bar etc) so we end up with 960×453 instead
        # of 960×540 — non-16:9 viewport → deck-frame letterboxes → screenshot
        # captures the letterbox → resize to 480×270 squashes everything.
        # Emulation.setDeviceMetricsOverride forces exact pixel dimensions
        # regardless of host window chrome.
        self._send(ws, "Emulation.setDeviceMetricsOverride", {
            "width":  VIEW_W,
            "height": VIEW_H,
            "deviceScaleFactor": 1,
            "mobile": False,
        })

        # Wait for the deck to be ready. feishu-deck-h5 stamps
        # `data-js-ready` on its <body>; other packs (rolling-deck etc.)
        # don't, so fall back to a `document.readyState === 'complete'` +
        # short paint settle once we've waited a little.
        deadline = time.time() + max_wait
        ready = False
        ready_via = None
        last_href = None
        FALLBACK_DELAY = 1.2  # seconds after readyState=complete on packs
                              # without a data-js-ready stamp
        complete_since = None
        while time.time() < deadline:
            resp = self._send(ws, "Runtime.evaluate", {
                "expression": (
                    "({href: location.href, ready: "
                    " !!document.querySelector('[data-js-ready]'), "
                    " state: document.readyState})"
                ),
                "returnByValue": True,
            })
            # Runtime.evaluate returns {result: {type, value, ...}}.
            # _send already stripped the outer CDP envelope.
            v = (resp.get("result") or {}).get("value") or {}
            last_href = v
            if v.get("ready"):
                ready = True
                ready_via = "data-js-ready"
                break
            # Fallback: document.readyState complete sustained for
            # FALLBACK_DELAY seconds.
            if v.get("state") == "complete":
                if complete_since is None:
                    complete_since = time.time()
                elif time.time() - complete_since >= FALLBACK_DELAY:
                    ready = True
                    ready_via = "readyState"
                    break
            else:
                complete_since = None
            time.sleep(0.1)
        if not ready:
            ws.close()
            self.close_tab(tab["id"])
            raise RuntimeError(
                f"Deck never became ready. Last probe: {last_href}. URL: {url}"
            )
        # Hide the deck's UI chrome (progress bar, page indicator, "翻页·F全屏"
        # hint) so the thumbnail contains pure slide content.
        self._send(ws, "Runtime.evaluate", {
            "expression": (
                "(() => {"
                " const s = document.createElement('style');"
                " s.textContent = '.deck-ui,.nav-hint{display:none!important}';"
                " document.head.appendChild(s);"
                "})()"
            ),
            "returnByValue": True,
        })
        return DeckTab(self, ws, tab["id"])

    def _send(self, ws, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        mid = self._msg_id
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP error on {method}: {msg['error']}")
                return msg.get("result", {})
            # Events on different ids are ignored.


class DeckTab:
    """One open tab pinned to one deck's index.html. Caller drives it
    by slide_key; we flip location.hash and wait for .slide-frame.is-current
    to settle on that slide before capturing."""

    def __init__(self, chrome: "Chrome", ws, target_id: str):
        self.chrome = chrome
        self.ws = ws
        self.target_id = target_id

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.chrome.close_tab(self.target_id)

    def screenshot_slide(self, slide_key: str, max_wait: float = 4.0) -> bytes:
        # Pack-agnostic slide selector. Try (in order):
        #   1. feishu-deck-h5: location.hash = '#<key>' triggers the deck's
        #      built-in router → .slide-frame.is-current matches.
        #   2. rolling-deck: no hash router; flip .slide.active manually so
        #      the section with matching data-slide-key is visible.
        # Whichever drives the DOM into a "this slide is visible" state,
        # we screenshot.
        sk = json.dumps(slide_key)
        expr = (
            "(() => {"
            f" const k = {sk};"
            # feishu-deck-h5 path
            f" location.hash = '';"
            f" location.hash = '#' + k;"
            # rolling-deck path: toggle .slide.active by data-slide-key
            " const slides = document.querySelectorAll('.slide[data-slide-key]');"
            " let hit = false;"
            " slides.forEach(s => {"
            "   const on = s.dataset.slideKey === k;"
            "   if (on) hit = true;"
            "   s.classList.toggle('active', on);"
            " });"
            # rolling-deck has body.on-cover for particle cover; sync it.
            " if (hit) {"
            "   const cur = document.querySelector('.slide[data-slide-key=\"' + k.replace(/\"/g,'\\\\\"') + '\"]');"
            "   document.body.classList.toggle('on-cover', !!cur && cur.classList.contains('cover-hero'));"
            " }"
            " return hit;"
            "})()"
        )
        self.chrome._send(self.ws, "Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
        })

        # Poll until the slide with the requested key is the visible one.
        # Two acceptable "visible" signals (feishu vs rolling): is-current
        # on the slide-frame, or .slide.active matching the key.
        check = (
            "(() => {"
            f" const k = {sk};"
            " const f = document.querySelector('.slide-frame.is-current');"
            " const fOk = f && f.querySelector('.slide')?.dataset.slideKey === k;"
            " if (fOk) return true;"
            " const a = document.querySelector('.slide.active');"
            " return !!(a && a.dataset.slideKey === k);"
            "})()"
        )
        deadline = time.time() + max_wait
        while time.time() < deadline:
            resp = self.chrome._send(self.ws, "Runtime.evaluate", {
                "expression": check, "returnByValue": True,
            })
            if (resp.get("result") or {}).get("value") is True:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError(f"Slide never became current: {slide_key}")
        # Fixed grace period for the deck's slide-transition / fade.
        # 300ms covers the CSS animation; another 100ms covers raster
        # of any large background images before capture.
        time.sleep(0.4)
        shot = self.chrome._send(self.ws, "Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": False,
        })
        return base64.b64decode(shot["data"])


def shoot_to_jpg(deck_tab: DeckTab, slide_key: str, out_jpg: Path) -> None:
    png = deck_tab.screenshot_slide(slide_key)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS)
        im.save(out_jpg, "JPEG", quality=82, optimize=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Regenerate even if a JPG already exists")
    ap.add_argument("--deck", help="Limit to one deck_id")
    ap.add_argument("--only", help="One specific slide id (e.g. kangshifu/slide-004)")
    args = ap.parse_args()

    if not DB_PATH.is_file():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        return 1
    if not Path(CHROME).is_file():
        print(f"Chrome not found at: {CHROME}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = "SELECT id, deck_id, slide_key, thumbnail_path FROM slides"
    params: list = []
    where = []
    if args.deck:
        where.append("deck_id = ?"); params.append(args.deck)
    if args.only:
        where.append("id = ?"); params.append(args.only)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY deck_id, page_no"
    rows = list(conn.execute(sql, params))

    jobs = []
    skipped = made = failed = 0
    for r in rows:
        deck_id, slide_key = r["deck_id"], r["slide_key"]

        # Defend the filesystem path AND the JS `location.hash` interpolation
        # against weird keys. Bad rows fall into `failed` rather than crashing
        # the whole batch — the batch may legitimately span many decks and
        # one bad row shouldn't cancel the rest.
        if not _DECK_ID_RE.match(deck_id or ""):
            print(f"{r['id']}  invalid deck_id (skipped)", file=sys.stderr)
            failed += 1
            continue
        if not _SLIDE_KEY_RE.match(slide_key or ""):
            print(f"{r['id']}  invalid slide_key (skipped)", file=sys.stderr)
            failed += 1
            continue

        render_dir = DECK_RENDER_DIRS.get(deck_id)
        if not render_dir or not render_dir.is_dir():
            print(f"{r['id']}  no render dir, skip", file=sys.stderr)
            failed += 1
            continue
        # Thumbnails live INSIDE the deck directory so they travel with it
        # when a deck is copied to a colleague's machine ("拷目录就同步" is
        # the team's sync model). The DB path is the admin-server URL form:
        # /decks/<deck_id>/.thumbs/<key>.jpg — served by the deck proxy.
        # (Exclude .thumbs/ when packaging a client deliverable.)
        out_rel = f"decks/{deck_id}/.thumbs/{slide_key}.jpg"
        out_abs = render_dir / ".thumbs" / f"{slide_key}.jpg"
        if out_abs.is_file() and not args.force:
            skipped += 1
            if r["thumbnail_path"] != out_rel:
                conn.execute(
                    "UPDATE slides SET thumbnail_path = ? WHERE id = ?",
                    (out_rel, r["id"])
                )
            continue
        index_html = render_dir / "index.html"
        if not index_html.is_file():
            print(f"{r['id']}  index.html missing, skip", file=sys.stderr)
            failed += 1
            continue
        jobs.append((r["id"], index_html, slide_key, out_abs, out_rel))

    if not jobs:
        print(f"Nothing to do. {skipped} already present.")
        conn.commit(); conn.close(); return 0

    print(f"Launching Chrome (CDP) for {len(jobs)} slides…")
    chrome = Chrome()
    t0 = time.time()

    # Group jobs by index.html. We open ONE tab per deck, navigate it
    # to the deck once, then drive it slide-by-slide via location.hash.
    # The deck JS already supports hash-based navigation, so each shot
    # after the first is just "flip hash → wait for is-current → capture".
    by_deck: dict[Path, list] = {}
    for j in jobs:
        by_deck.setdefault(j[1], []).append(j)

    try:
        done = 0
        for idx_html, deck_jobs in by_deck.items():
            # file:// URL must percent-encode spaces / non-ASCII.
            url = "file://" + urllib.parse.quote(str(idx_html))
            print(f"Opening {url}  ({len(deck_jobs)} slides)…", flush=True)
            tab = chrome.open_deck(url)
            try:
                for sid, _idx, slide_key, out_abs, out_rel in deck_jobs:
                    done += 1
                    t = time.time()
                    try:
                        shoot_to_jpg(tab, slide_key, out_abs)
                        conn.execute(
                            "UPDATE slides SET thumbnail_path = ? WHERE id = ?",
                            (out_rel, sid)
                        )
                        made += 1
                        print(f"[{done}/{len(jobs)}] {sid}  ok "
                              f"({time.time()-t:.2f}s)", flush=True)
                    except Exception as e:
                        failed += 1
                        print(f"[{done}/{len(jobs)}] {sid}  FAIL: {e}",
                              file=sys.stderr, flush=True)
            finally:
                tab.close()
    finally:
        chrome.close()
    conn.commit()
    conn.close()
    print(f"\nDone in {time.time()-t0:.1f}s: "
          f"{made} made, {skipped} skipped, {failed} failed.")
    print("Output: imports/<deck>/render-output-full/.thumbs/ (per deck)")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
