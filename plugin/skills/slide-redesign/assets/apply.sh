#!/usr/bin/env bash
# slide-redesign · apply.sh
#
# Apply per-slide HTML overrides to an existing deck.json.
#
# Usage:
#   bash apply.sh <input.json> <redesigns-dir> [<output.json>]
#
# If <output.json> is omitted, the input is updated in place (with .bak backup).

set -euo pipefail

if [[ $# -lt 2 ]]; then
    cat >&2 <<EOF
usage: bash apply.sh <input-deck.json> <redesigns-dir> [<output-deck.json>]

  <input-deck.json>   deck.json from any source (keynote-to-html, slide-design, hand-authored)
  <redesigns-dir>     directory containing slide-NN.html or slide-XYZ.html
                      (PDF page index OR zero-padded slide-key)
  <output-deck.json>  optional; defaults to in-place update of input

Next step: render with feishu-deck-h5.
EOF
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/apply.py" "$@"
