#!/usr/bin/env bash
# deck-splice/verify.sh — post-splice sanity check on a target deck.
#
# Usage: verify.sh <deck_dir>
#
# Checks (all warnings/errors print to stderr; exit code reflects worst):
#   1. host pack's slide enumeration sees exactly the outer .slide count
#      (no .src-slide leaking into '.slide' selector — class rename worked)
#   2. injected CSS block is present
#   3. every <section class="...is-splice...">  has at least one .src-slide
#      direct descendant (no empty placeholders left)
#   4. every <video src=…> / <img src=…> / <source src=…> URL exists on disk
set -euo pipefail
DECK="${1:-}"
if [[ -z "$DECK" || ! -d "$DECK" ]]; then
  echo "usage: verify.sh <deck_dir>" >&2; exit 2
fi
HTML="$DECK/index.html"
[[ -f "$HTML" ]] || { echo "no index.html in $DECK" >&2; exit 2; }

fail=0; warn=0

# 1. dual-class sanity. The host pack's JS uses querySelectorAll('.slide').
#    Count outer .slide (host pack's <section>s) and confirm no inlined
#    .src-slide leaks into that count. Note: grep's `\bslide\b` would
#    treat `src-slide` as a match because `-` is a word boundary; we use
#    Python with a strict identifier-char lookaround instead.
counts=$(python3 - "$HTML" <<'PY'
import re, sys
html = open(sys.argv[1], encoding="utf-8").read()
slide_token = re.compile(r'(?<![\w-])slide(?![\w-])')
src_slide_token = re.compile(r'(?<![\w-])src-slide(?![\w-])')
# only count occurrences inside class="…" values
slide_in_class = 0
src_in_class = 0
for m in re.finditer(r'class="([^"]+)"', html):
    if slide_token.search(m.group(1)):     slide_in_class += 1
    if src_slide_token.search(m.group(1)): src_in_class += 1
outer = len(re.findall(r'<section[^>]*class="[^"]*(?<![\w-])slide(?![\w-])[^"]*"', html))
print(f"{outer} {src_in_class} {slide_in_class}")
PY
)
read section_count src_slide_count slide_in_class <<<"$counts"

echo "outer <section> with .slide:  $section_count" >&2
echo "inlined .src-slide divs:      $src_slide_count" >&2
echo "elements matching .slide:     $slide_in_class" >&2

if [[ "$slide_in_class" -ne "$section_count" ]]; then
  echo "FAIL: found $slide_in_class elements matching .slide, expected $section_count" >&2
  echo "      (class-rename leak — host pack's JS will mis-count slides)" >&2
  fail=1
fi

# 2. injected CSS sentinel
if ! grep -q "/\* === deck-splice injected" "$HTML"; then
  echo "WARN: deck-splice CSS block not found; splice slides may render at 0 height" >&2
  warn=1
fi

# 3. empty is-splice placeholders. `set -e` + `grep | wc -l` blows up when
#    grep finds nothing (pipefail catches grep's exit 1); the `|| true`
#    lets the no-match case fall through to 0.
empty_count=$(grep -oE '<section[^>]*class="[^"]*is-splice[^"]*"[^>]*></section>' "$HTML" 2>/dev/null | wc -l | tr -d ' ' || true)
empty_count=${empty_count:-0}
if [[ "$empty_count" -gt 0 ]]; then
  echo "WARN: $empty_count empty <section …is-splice…></section> left unfilled" >&2
  warn=1
fi

# 3.5 lazy videos that never got materialized — <video data-src=…> without
#     src= will only ever show its poster (the source pack's player JS that
#     swaps data-src→src is not loaded after a splice).
lazy_count=$(grep -oE '<video[^>]*data-src=' "$HTML" 2>/dev/null | wc -l | tr -d ' ' || true)
lazy_count=${lazy_count:-0}
if [[ "$lazy_count" -gt 0 ]]; then
  echo "FAIL: $lazy_count <video data-src=…> still lazy — video will never play." >&2
  echo "      Re-run splice (materialize_lazy_media) or set src= manually." >&2
  fail=1
fi

# 4. asset existence — extract every relative src/href/poster pointing under assets/
python3 - "$DECK" "$HTML" <<'PY'
import re, sys, os
deck_dir = sys.argv[1]; html = open(sys.argv[2], encoding="utf-8").read()
# Strip HTML comments first — commented-out template hints (e.g. the
# rolling-deck cover's optional co-brand <img src="assets/<client>-logo.svg">)
# are NOT real references; counting them produced false "missing asset" fails.
html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
seen = set()
for m in re.finditer(r'(?:src|href|poster)="(assets/[^"]+)"', html):
    seen.add(m.group(1))
missing = [u for u in sorted(seen) if not os.path.isfile(os.path.join(deck_dir, u))]
if missing:
    print(f"FAIL: {len(missing)} referenced asset(s) missing on disk:", file=sys.stderr)
    for u in missing[:20]:
        print(f"  · {u}", file=sys.stderr)
    if len(missing) > 20:
        print(f"  · …({len(missing)-20} more)", file=sys.stderr)
    sys.exit(1)
else:
    print(f"asset URLs: {len(seen)} checked, all resolve", file=sys.stderr)
PY
asset_rc=$?
[[ $asset_rc -ne 0 ]] && fail=1

if [[ $fail -ne 0 ]]; then
  echo "==> verify FAILED" >&2; exit 1
elif [[ $warn -ne 0 ]]; then
  echo "==> verify passed with warnings" >&2; exit 0
else
  echo "==> verify OK" >&2; exit 0
fi
