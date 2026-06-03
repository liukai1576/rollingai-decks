#!/usr/bin/env bash
# slim-deck · run.sh — thin wrapper around slim.py
#
# Usage:
#   bash run.sh <project-dir> [--dry-run] [--keep-source] [--keep-media]
#
# Example:
#   bash plugin/skills/slim-deck/assets/run.sh imports/RollingAI分享
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/slim.py" "$@"
