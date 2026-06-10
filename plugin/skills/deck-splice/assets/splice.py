#!/usr/bin/env python3
"""
deck-splice — inline a slide from one deck into a placeholder section of
another deck. Handles class-name collision (`.slide` → `.src-slide`), inline-
`<style>` rewriting, asset copy + path rewrite, and the rolling-deck
`.slide-fit` flex wrapper trap.

Usage:
    python3 splice.py --target <deck_dir> --manifest <manifest.json>
    python3 splice.py --target <deck_dir> --manifest -        # stdin

Manifest schema (v1):
    {
      "host_pack": "rolling-deck",                # informational
      "splices": [
        { "outer_key":         "liby-bc-recorder",
          "source_deck_id":    "RollingAI分享",
          "source_slide_key":  "slide-041" },
        ...
      ]
    }

Contract on the *target* deck (caller must prepare this):
    For every splice, the target index.html must contain a *placeholder
    section* with matching outer_key, marked `is-splice`:
        <section class="slide is-splice"
                 data-slide-key="liby-bc-recorder"
                 data-screen-label="08 立白 · BC"></section>
    splice.py *only fills* these sections — it never creates or reorders
    them. Page count, screen-labels, and act structure stay in the human's
    hands.

What gets injected:
    1. The full <div class="slide" data-slide-key="<src>">…</div> markup
       from the source deck, RENAMED to <div class="src-slide" …> so the
       host pack's JS (`querySelectorAll('.slide')`) never picks it up.
    2. All `.slide(?![\\w-])` selectors inside the slide's own <style>
       are rewritten to `.src-slide` (lookahead so `.slide-fit` /
       `.slide-frame` survive).
    3. Every relative asset URL in the slide (img/video/source src,
       poster, href, srcset, plus url() inside inline <style>) gets
       copied to <target>/assets/_borrowed/<source_deck_id>/<orig path>
       and the URL is rewritten to that local copy.
    4. A small CSS block (`.slide.is-splice { padding: 0 }` and
       `.src-slide { position:absolute; inset:0; width:1920px;
       height:1080px; overflow:hidden; }`) is appended to the target's
       last <style> block if not already there. This handles the
       rolling-deck `.slide-fit` flex-wrapper trap.

What it does NOT do:
    – does not load the source deck's player JS (visual splice only)
    – does not rename other source classes (.card / .grid / etc.) — if the
      host pack has its own .card, you may see styling bleed. The script
      WARNS on shared class names but does not auto-resolve them.
    – does not touch deck.json or DB — re-run deck-ingest after splicing.
"""
from __future__ import annotations
import argparse, json, re, shutil, sys
from pathlib import Path
from bs4 import BeautifulSoup, Tag

REPO_ROOT = Path(__file__).resolve().parents[4]   # plugin/skills/deck-splice/assets/splice.py → repo root

# CSS that the rolling-deck host needs for splice slides to display right.
# Idempotent: skill checks if `.src-slide {` already in the host's CSS.
HOST_CSS_BLOCK = """
    /* === deck-splice injected (see plugin/skills/deck-splice) === */
    .slide.is-splice { padding: 0 !important; }
    .src-slide {
      position: absolute; inset: 0;
      width: 1920px; height: 1080px;
      overflow: hidden;
      background: #0a1126;        /* fallback under sources without their own bg */
    }
    /* If the host pack auto-wraps slide children in a flex container
       (rolling-deck does this; class .slide-fit), the inlined .src-slide
       above is also a flex item and needs an explicit flex basis. */
    .slide-fit > .src-slide { flex: 1 1 0; min-height: 0; }
    /* === /deck-splice === */
"""

# Asset attributes we copy & rewrite.
ASSET_ATTRS = ("src", "href", "poster", "data-src")

# `.slide` not followed by an identifier character. This protects
# `.slide-fit`, `.slide-frame`, `.slideX`, etc.
SLIDE_SELECTOR_RE = re.compile(r'\.slide(?![A-Za-z0-9_-])')

# url(...) inside CSS — captures the URL string.
CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""")

# Class names that frequently collide between packs — we warn if a source
# slide uses any of these (host pack may style them differently).
COMMON_COLLISIONS = {"card", "cards", "grid", "stat", "kicker", "copy",
                     "hero", "title", "subtitle", "section"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_manifest(path: str) -> dict:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    m = json.loads(raw)
    if "splices" not in m or not isinstance(m["splices"], list):
        sys.exit("manifest: missing or invalid 'splices' list")
    for i, s in enumerate(m["splices"]):
        for k in ("outer_key", "source_deck_id", "source_slide_key"):
            if k not in s:
                sys.exit(f"manifest.splices[{i}]: missing '{k}'")
    return m


def source_path_of(deck_id: str) -> Path:
    """Resolve a source deck id to its rendered index.html path.

    Resolution order:
      1. library/db/deck_mounts.discover_mounts — handles DB deck_ids that
         alias to a different directory name (imports/.deck-mounts.json)
      2. plain <repo>/imports/<deck_id>/render-output-full/
    """
    try:
        sys.path.insert(0, str(REPO_ROOT / "library" / "db"))
        from deck_mounts import discover_mounts
        mount = discover_mounts(REPO_ROOT).get(deck_id)
        if mount and (mount / "index.html").is_file():
            return mount / "index.html"
    except ImportError:
        pass
    p = REPO_ROOT / "imports" / deck_id / "render-output-full" / "index.html"
    if not p.exists():
        sys.exit(f"source deck not found: no mount for '{deck_id}' and no "
                 f"imports/{deck_id}/render-output-full/index.html")
    return p


def extract_source_slide(src_html: str, slide_key: str) -> Tag | None:
    """Find <div class="slide" data-slide-key="<key>"> in the source deck."""
    soup = BeautifulSoup(src_html, "html.parser")
    for d in soup.find_all("div"):
        if d.get("data-slide-key") == slide_key and "slide" in (d.get("class") or []):
            return d
    return None


def copy_asset(rel_path: str, source_deck_id: str, target_dir: Path) -> str:
    """Copy <source_deck>/render-output-full/<rel_path> to
    <target>/assets/_borrowed/<source_deck>/<rel_path>. Returns the new
    URL to use (relative to the target index.html)."""
    src = source_path_of(source_deck_id).parent / rel_path
    dst = target_dir / "assets" / "_borrowed" / source_deck_id / rel_path
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
    else:
        log(f"  ! missing asset: {source_deck_id}/{rel_path}")
    return f"assets/_borrowed/{source_deck_id}/{rel_path}"


def rewrite_asset_paths(div: Tag, source_deck_id: str, target_dir: Path) -> None:
    """Mutate div: rewrite every relative asset URL to point at the
    borrowed copy. Handles both attributes and url() in inline <style>."""
    for tag in div.find_all(True):
        for attr in ASSET_ATTRS:
            v = tag.get(attr)
            if not v or isinstance(v, list): continue
            v = v.strip()
            if not v or v.startswith(("http://", "https://", "data:", "#",
                                       "mailto:", "javascript:")):
                continue
            # If it's already pointing at our _borrowed dir (e.g. re-splicing
            # a deck that already has borrowed paths), don't double-prefix.
            if v.startswith("assets/_borrowed/"):
                continue
            tag[attr] = copy_asset(v, source_deck_id, target_dir)
    # url() in inline <style>
    for style in div.find_all("style"):
        txt = style.get_text()
        def _sub(m):
            v = m.group(1).strip()
            if v.startswith(("http", "data:", "#", "assets/_borrowed/")):
                return m.group(0)
            return f"url('{copy_asset(v, source_deck_id, target_dir)}')"
        new = CSS_URL_RE.sub(_sub, txt)
        if new != txt:
            style.string = new


def materialize_lazy_media(div: Tag) -> None:
    """Activate lazy-loaded videos so they play without the source pack's
    player JS.

    feishu-deck-h5 ships videos as <video data-src="…" preload="none"
    class="lazy-video"> and its player swaps data-src → src when the slide
    becomes current. We splice DOM only (no source JS), so without this
    step the video keeps showing its poster and never plays.

    Playback itself (play on slide-enter, pause+reset on slide-leave,
    unmute after first user interaction) is handled by the video runtime
    injected via inject_host_js() — we deliberately do NOT set autoplay
    here, otherwise every video in the deck decodes simultaneously at
    page load.

    Sound default is derived FROM THE SOURCE MARKUP: the feishu player
    only unmutes `video.lazy-video` after user engagement (its unmute
    selector is literally 'video.lazy-video'), so in the source deck
    lazy videos are audible and plain <video muted autoplay> ones are
    silent forever. We mirror that: lazy-video → data-sound. The
    manifest "sound" flag / 有声视频 · 静音视频 free_tags override this
    per slide."""
    for v in div.find_all("video"):
        if v.get("data-src") and not v.get("src"):
            v["src"] = v["data-src"]
            del v["data-src"]
            v["preload"] = "none"   # runtime's play() triggers the load
        if "lazy-video" in (v.get("class") or []):
            v["data-sound"] = "1"   # audible in the source deck → keep audible


def namespace_rename(div: Tag) -> None:
    """Rename .slide → .src-slide on root and inside inline <style>."""
    classes = div.get("class") or []
    div["class"] = ["src-slide" if c == "slide" else c for c in classes]
    for style in div.find_all("style"):
        txt = style.get_text()
        new = SLIDE_SELECTOR_RE.sub(".src-slide", txt)
        if new != txt:
            style.string = new


def warn_collisions(div: Tag, source_deck_id: str, source_slide_key: str) -> None:
    """Heads-up if the source slide uses class names that often clash
    with host packs (e.g. .card)."""
    seen = set()
    for tag in div.find_all(True):
        for c in tag.get("class") or []:
            if c in COMMON_COLLISIONS:
                seen.add(c)
    if seen:
        log(f"  ⚠  {source_deck_id}/{source_slide_key} uses common classes: "
            f"{', '.join(sorted(seen))} — check host pack doesn't restyle them")


def fill_placeholder(target_html: str, outer_key: str, inlined_markup: str) -> tuple[str, bool]:
    """Find <section class="slide is-splice" data-slide-key="<outer_key>"…></section>
    in target_html and replace its inner contents with inlined_markup. Returns
    (new_html, was_filled)."""
    pat = re.compile(
        r'(<section\b[^>]*class="[^"]*\bis-splice\b[^"]*"[^>]*'
        rf'data-slide-key="{re.escape(outer_key)}"[^>]*>)'
        r'(.*?)'
        r'(</section>)',
        re.DOTALL
    )
    m = pat.search(target_html)
    if not m:
        # Also accept the section with attributes in a different order.
        pat = re.compile(
            rf'(<section\b[^>]*data-slide-key="{re.escape(outer_key)}"[^>]*'
            r'class="[^"]*\bis-splice\b[^"]*"[^>]*>)(.*?)(</section>)',
            re.DOTALL
        )
        m = pat.search(target_html)
    if not m:
        return target_html, False
    indented = "\n".join("        " + line for line in inlined_markup.splitlines())
    new_html = target_html[:m.start()] + m.group(1) + "\n" + indented + "\n      " + m.group(3) + target_html[m.end():]
    return new_html, True


# Video runtime injected into the host deck.
#   · only the ACTIVE slide's videos play; leaving a slide pauses + rewinds
#   · sound is OPT-IN per video: every source mp4 carries an audio track
#     (street-noise b-roll, AI-gen bgm, …) and was muted by markup in the
#     source deck, so "should this be audible" is editorial intent that the
#     data doesn't carry. Videos marked data-sound="1" are unmuted after the
#     first user interaction (autoplay policy); everything else stays muted
#     forever. The flag comes from the source slide's free_tag 有声视频
#     (set in the admin slide drawer) — see materialize_lazy_media/insert.py.
# Works on every <video> in the deck — spliced AND host-authored alike.
HOST_JS_BLOCK = """
<script>
/* === deck-splice video runtime === */
(function () {
  let engaged = false;
  function markEngaged() {
    if (engaged) return;
    engaged = true;
    document.querySelectorAll('.slide.active video[data-sound]').forEach(v => {
      if (!v.paused) v.muted = false;
    });
  }
  ['keydown', 'click', 'touchstart'].forEach(ev =>
    document.addEventListener(ev, markEngaged, { passive: true }));

  let lastActive = null;
  function tick() {
    const cur = document.querySelector('.slide.active');
    if (cur !== lastActive) {
      lastActive = cur;
      document.querySelectorAll('.slide').forEach(sl => {
        const isCur = sl === cur;
        sl.querySelectorAll('video').forEach(v => {
          if (isCur) {
            v.muted = !(engaged && v.hasAttribute('data-sound'));
            const p = v.play();
            if (p && p.catch) p.catch(() => { v.muted = true; v.play().catch(() => {}); });
          } else if (!v.paused || v.currentTime > 0) {
            v.pause();
            try { v.currentTime = 0; } catch (_) {}
          }
        });
      });
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
/* === /deck-splice video runtime === */
</script>
"""


def inject_host_js(target_html: str) -> str:
    """Append the video runtime before </body>, once (sentinel-guarded)."""
    if "deck-splice video runtime" in target_html:
        return target_html
    if "</body>" not in target_html:
        log("  ! target has no </body>; video runtime not injected")
        return target_html
    return target_html.replace("</body>", HOST_JS_BLOCK + "</body>", 1)


def inject_host_css(target_html: str) -> str:
    """Append HOST_CSS_BLOCK before the last </style> in target_html, if
    not already injected. Idempotent."""
    if "/* === deck-splice injected" in target_html:
        return target_html
    # Find the last </style> in <head>.
    head_end = target_html.find("</head>")
    if head_end < 0:
        log("  ! target has no </head>; appending CSS to body instead")
        return target_html.replace("</body>", f"<style>{HOST_CSS_BLOCK}</style></body>", 1)
    head_chunk = target_html[:head_end]
    last_style = head_chunk.rfind("</style>")
    if last_style < 0:
        log("  ! target <head> has no <style>; inserting one")
        return target_html.replace("</head>", f"<style>{HOST_CSS_BLOCK}</style></head>", 1)
    return target_html[:last_style] + HOST_CSS_BLOCK + target_html[last_style:]


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(prog="deck-splice")
    ap.add_argument("--target", required=True, type=Path,
                    help="Target deck directory (must contain index.html).")
    ap.add_argument("--manifest", required=True,
                    help="Path to manifest JSON, or '-' for stdin.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse + validate manifest, but don't write changes.")
    args = ap.parse_args()

    target_dir = args.target.resolve()
    target_html_path = target_dir / "index.html"
    if not target_html_path.exists():
        sys.exit(f"target/index.html not found: {target_html_path}")
    target_html = target_html_path.read_text(encoding="utf-8")

    manifest = load_manifest(args.manifest)
    filled = []
    missing_placeholder = []
    missing_source = []

    for entry in manifest["splices"]:
        outer_key   = entry["outer_key"]
        src_deck_id = entry["source_deck_id"]
        src_key     = entry["source_slide_key"]

        src_path = source_path_of(src_deck_id)
        src_html = src_path.read_text(encoding="utf-8")
        div = extract_source_slide(src_html, src_key)
        if div is None:
            log(f"  ! source slide not found: {src_deck_id}/{src_key}")
            missing_source.append(f"{src_deck_id}/{src_key}")
            continue

        rewrite_asset_paths(div, src_deck_id, target_dir)
        materialize_lazy_media(div)
        # Optional per-splice sound OVERRIDE (manifest "sound": true/false —
        # insert.py sets it from the source slide's 有声视频 / 静音视频
        # free_tags). Absent → markup-derived default from
        # materialize_lazy_media stands.
        if "sound" in entry:
            for v in div.find_all("video"):
                if entry["sound"]:
                    v["data-sound"] = "1"
                elif v.has_attr("data-sound"):
                    del v["data-sound"]
            log(f"  · {outer_key}: sound override → "
                f"{'有声' if entry['sound'] else '静音'}")
        namespace_rename(div)
        warn_collisions(div, src_deck_id, src_key)
        # slide-anim hooks (data-anim / data-count / .bar-fill …) are DOM
        # attributes that splice copies fine, but the GSAP engine lives at
        # deck level. If the source slide expects it and the target deck
        # doesn't ship RollingSlideAnim, those elements render static.
        if (div.find(attrs={"data-anim": True}) or div.find(attrs={"data-count": True})) \
                and "RollingSlideAnim" not in target_html:
            log(f"  ⚠  {outer_key}: source slide has slide-anim hooks "
                f"(data-anim/data-count) but the target deck has no "
                f"RollingSlideAnim engine — install the slide-anim skill on "
                f"the target or these elements stay static")

        markup = str(div)
        target_html, ok = fill_placeholder(target_html, outer_key, markup)
        if not ok:
            log(f"  ! placeholder missing in target: outer_key='{outer_key}'")
            missing_placeholder.append(outer_key)
            continue
        filled.append((outer_key, src_deck_id, src_key))
        log(f"  ✓ {outer_key:32s}  ←  {src_deck_id}/{src_key}")

    target_html = inject_host_css(target_html)
    target_html = inject_host_js(target_html)

    if args.dry_run:
        log(f"\ndry-run: would fill {len(filled)} placeholders")
    else:
        target_html_path.write_text(target_html, encoding="utf-8")
        log(f"\nwrote {target_html_path}  ({len(filled)} splices inlined)")

    if missing_source or missing_placeholder:
        log("\nproblems:")
        for s in missing_source:       log(f"  · source slide not found:   {s}")
        for k in missing_placeholder:  log(f"  · target placeholder missing: outer_key='{k}'")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
