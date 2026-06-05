#!/usr/bin/env bash
# Mark a deck's render-output dir as "no-render". The HTML itself stays
# freely editable — only plugin/_player/render.py will refuse to overwrite
# it. Manual edits via editor, sed, Python scripts, etc. all work fine.
#
# Usage:
#   bash library/tools/lock-deck.sh <render-output-dir> ["optional reason text"]
#   bash library/tools/lock-deck.sh imports/RollingAI分享/render-output-full \
#                                   "hand-edited slide 6 / 38; rendering destroys it"
set -euo pipefail
if [[ $# -lt 1 ]]; then
    echo "usage: lock-deck.sh <render-output-dir> [\"reason\"]" >&2
    exit 2
fi
TARGET="$1"
REASON="${2:-Deck contains hand edits not mirrored in deck.json.}"
if [[ ! -d "$TARGET" ]]; then
    echo "ERROR: not a directory: $TARGET" >&2
    exit 2
fi
SENTINEL="$TARGET/.no-render"
{
    echo "$REASON"
    echo
    echo "Locked at: $(date)"
    echo "Locked by: $(id -un)@$(hostname -s)"
} > "$SENTINEL"
echo "🔒 LOCKED for rendering: $TARGET"
echo "    sentinel: $SENTINEL"
echo
echo "  · render.py refuses to overwrite anything in this dir."
echo "  · HTML / CSS / assets remain FULLY editable by hand."
echo "  · To unlock:  bash library/tools/unlock-deck.sh \"$TARGET\""
