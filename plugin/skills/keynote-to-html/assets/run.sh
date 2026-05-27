#!/usr/bin/env bash
# keynote-to-html · run.sh
#
# Orchestrate: open .key in Keynote → extract per-slide elements → build HTML.
#
# Usage:
#   bash run.sh <path-to-.key> <output-dir> [--limit N] [--feishu-skill PATH]

set -euo pipefail

if [[ $# -lt 2 ]]; then
    cat >&2 <<EOF
usage: bash run.sh <path-to-.key> <output-dir>
              [--limit N]
              [--feishu-skill PATH]
              [--rasters-dir DIR]     # per-page PNGs for fallback crops
              [--pdf PATH]            # source PDF for on-demand fallback rasterization
              [--redesigns DIR]       # dir with slide-NN.html HTML overrides for redesigned slides

  .key file is opened in Keynote.app (read-only). Element data is extracted
  via AppleScript to <output-dir>/extract.tsv, then build.py composes HTML
  and feishu-deck-h5/render-deck.py wraps it in present-mode chrome.
EOF
    exit 1
fi

KEY_PATH="$1"
OUT_DIR="$2"
shift 2

# Optional args (passed through to build.py)
EXTRA_ARGS=()
EXTRACT_LIMIT=0
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--limit" && $# -gt 1 ]]; then
        EXTRACT_LIMIT="$2"
        EXTRA_ARGS+=("$1" "$2")
        shift 2
    else
        EXTRA_ARGS+=("$1")
        shift
    fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Sanity checks
if [[ ! -e "$KEY_PATH" ]]; then
    echo "ERROR: .key not found: $KEY_PATH" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
TSV_PATH="$OUT_DIR/extract.tsv"

# Target Keynote by bundle id, NOT by app name. Two installs commonly coexist
# on macOS:
#   · com.apple.iWork.Keynote  → "Keynote" (14.x stable; what the App Store ships)
#   · com.apple.Keynote        → "Keynote Creator Studio" (15.x next-gen)
# Plain `tell application "Keynote"` resolves to whichever the system picks,
# which is non-deterministic and often the old one. We pin to the new bundle.
KN_BUNDLE="com.apple.Keynote"

# 1. Open .key in Keynote (idempotent — if already open, focuses it)
echo "==> opening Keynote (bundle: $KN_BUNDLE): $KEY_PATH"
osascript -e "tell application id \"$KN_BUNDLE\" to open POSIX file \"$KEY_PATH\"" >/dev/null
# Wait until Keynote has a front document loaded — large .keys can take many
# seconds to open from cold. Poll up to 30 s.
for i in $(seq 1 30); do
    n=$(osascript -e "tell application id \"$KN_BUNDLE\" to count of documents" 2>/dev/null || echo 0)
    if [[ "$n" -gt 0 ]]; then break; fi
    sleep 1
done
sleep 1  # final settle

# 2. Run AppleScript extractor.
# Pass the .key file's basename as the doc name — Keynote may have multiple
# documents open and `front document` would pick the wrong one. We open the
# file in step 1 above, but on some Keynote versions that doesn't bring the
# window forward if the doc was already open. Naming the doc explicitly fixes
# this.
KEY_BASENAME="$(basename "$KEY_PATH")"
echo "==> extracting elements via AppleScript (limit=$EXTRACT_LIMIT, doc='$KEY_BASENAME')"
osascript "$SCRIPT_DIR/extract.applescript" "$TSV_PATH" "$EXTRACT_LIMIT" "$KEY_BASENAME"
echo "    wrote $TSV_PATH ($(wc -l <"$TSV_PATH" | tr -d ' ') lines)"

# 3. Run Python builder + feishu renderer
echo "==> running build.py"
# IMPORTANT: do NOT use `"${EXTRA_ARGS[@]:-}"` — under `set -u` with an empty
# array, the `:-` default is an empty STRING, which gets passed as an empty
# positional arg that argparse then rejects. Build the argv conditionally.
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
    python3 "$SCRIPT_DIR/build.py" "$TSV_PATH" "$KEY_PATH" "$OUT_DIR" "${EXTRA_ARGS[@]}"
else
    python3 "$SCRIPT_DIR/build.py" "$TSV_PATH" "$KEY_PATH" "$OUT_DIR"
fi

echo
echo "==> open in browser:"
echo "    open \"$OUT_DIR/index.html\""
