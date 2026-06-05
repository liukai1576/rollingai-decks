#!/usr/bin/env bash
# Remove the .no-render sentinel so plugin/_player/render.py can overwrite
# index.html again. After this, render is still gated behind an interactive
# 'YES' confirmation — see plugin/_player/render.py.
#
# Usage:
#   bash library/tools/unlock-deck.sh <render-output-dir>
set -euo pipefail
if [[ $# -lt 1 ]]; then
    echo "usage: unlock-deck.sh <render-output-dir>" >&2
    exit 2
fi
TARGET="$1"
if [[ ! -d "$TARGET" ]]; then
    echo "ERROR: not a directory: $TARGET" >&2
    exit 2
fi
SENTINEL="$TARGET/.no-render"
if [[ ! -f "$SENTINEL" ]]; then
    echo "ℹ  Already unlocked (no .no-render in $TARGET)"
    exit 0
fi
rm "$SENTINEL"
echo "🔓 UNLOCKED for rendering: $TARGET"
echo
echo "  · render.py can now overwrite index.html (with YES confirmation)."
echo "  · Remember to re-lock with lock-deck.sh when done editing."
