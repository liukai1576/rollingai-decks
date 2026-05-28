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
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket  # pip install websocket-client
from PIL import Image

# ---- Paths ----
REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "library" / "db" / "data" / "slides.db"
THUMBS_DIR = REPO / "library" / "db" / "data" / "thumbs"

DECK_RENDER_DIRS: dict[str, Path] = {
    "kangshifu": REPO / "imports" / "RollingAI分享-康师傅" / "render-output-full",
}

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Render at 960×540 (2x retina) — paints faster than 1920×1080 and
# is plenty for a 480×270 thumbnail. The deck CSS reads viewport
# dimensions and computes --fs-scale to fit the 1920×1080 slide in.
VIEW_W, VIEW_H = 960, 540
THUMB_W, THUMB_H = 480, 270


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

    # ---- WebSocket per tab ----
    def screenshot(self, url: str, ready_signal: str = "[data-js-ready]",
                   max_wait: float = 8.0) -> bytes:
        """Open a new tab, navigate, wait for ready_signal, capture PNG, close tab."""
        tab = self.new_tab("about:blank")
        ws_url = tab["webSocketDebuggerUrl"]
        target_id = tab["id"]
        ws = websocket.create_connection(ws_url, timeout=15)
        try:
            self._send(ws, "Page.enable")
            self._send(ws, "Runtime.enable")
            self._send(ws, "Page.navigate", {"url": url})

            # Poll the DOM for ready_signal (deck JS sets data-js-ready
            # on .deck after readHash + goTo). This is the cleanest cue
            # that the target slide is laid out.
            deadline = time.time() + max_wait
            while time.time() < deadline:
                resp = self._send(ws, "Runtime.evaluate", {
                    "expression": f"!!document.querySelector('{ready_signal}')",
                    "returnByValue": True,
                })
                if resp.get("result", {}).get("result", {}).get("value"):
                    break
                time.sleep(0.1)
            # Small grace for the slide transition to settle.
            time.sleep(0.15)

            shot = self._send(ws, "Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": False,
            })
            return base64.b64decode(shot["data"])
        finally:
            ws.close()
            self.close_tab(target_id)

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


def shoot_to_jpg(chrome: Chrome, index_html: Path, slide_key: str,
                 out_jpg: Path) -> None:
    url = f"file://{index_html}#{slide_key}"
    png = chrome.screenshot(url)
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
        out_rel = f"thumbs/{deck_id}/{slide_key}.jpg"
        out_abs = THUMBS_DIR.parent / out_rel
        if out_abs.is_file() and not args.force:
            skipped += 1
            if r["thumbnail_path"] != out_rel:
                conn.execute(
                    "UPDATE slides SET thumbnail_path = ? WHERE id = ?",
                    (out_rel, r["id"])
                )
            continue
        render_dir = DECK_RENDER_DIRS.get(deck_id)
        if not render_dir or not render_dir.is_dir():
            print(f"{r['id']}  no render dir, skip", file=sys.stderr)
            failed += 1
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
    try:
        for i, (sid, idx_html, slide_key, out_abs, out_rel) in enumerate(jobs, 1):
            t = time.time()
            try:
                shoot_to_jpg(chrome, idx_html, slide_key, out_abs)
                conn.execute(
                    "UPDATE slides SET thumbnail_path = ? WHERE id = ?",
                    (out_rel, sid)
                )
                made += 1
                print(f"[{i}/{len(jobs)}] {sid}  ok ({time.time()-t:.1f}s)",
                      flush=True)
            except Exception as e:
                failed += 1
                print(f"[{i}/{len(jobs)}] {sid}  FAIL: {e}",
                      file=sys.stderr, flush=True)
    finally:
        chrome.close()
    conn.commit()
    conn.close()
    print(f"\nDone in {time.time()-t0:.1f}s: "
          f"{made} made, {skipped} skipped, {failed} failed.")
    print(f"Output: {THUMBS_DIR}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
