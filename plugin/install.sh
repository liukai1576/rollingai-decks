#!/usr/bin/env bash
# rolling-deck · dev install (symlink into ~/.claude/skills/)
#
# Run from the plugin/ directory (or from anywhere — it resolves its own path).
# Symlinks plugin/skills/rolling-deck/ into ~/.claude/skills/rolling-deck/
# so changes show up live in Claude Code without re-installing.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/skills/rolling-deck"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
LINK_PATH="$CLAUDE_DIR/skills/rolling-deck"

if [ ! -d "$SKILL_SRC" ]; then
  echo "ERROR — $SKILL_SRC not found. Run install.sh from the plugin/ dir of this repo." >&2
  exit 1
fi

mkdir -p "$CLAUDE_DIR/skills"

if [ -L "$LINK_PATH" ] || [ -e "$LINK_PATH" ]; then
  echo "==> removing existing $LINK_PATH"
  rm -rf "$LINK_PATH"
fi

ln -s "$SKILL_SRC" "$LINK_PATH"
echo "==> symlinked: $LINK_PATH -> $SKILL_SRC"

# Optional: also install as a plugin via marketplace if you want /plugin to manage it.
# For dev, the symlink above is enough — Claude Code picks the skill up next session.

echo
echo "DONE. Restart Claude Code to pick up the skill."
echo "Verify: bash $LINK_PATH/assets/preflight.sh"
