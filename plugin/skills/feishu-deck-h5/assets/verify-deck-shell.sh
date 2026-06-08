#!/usr/bin/env bash
# verify-deck-shell.sh — pack-aware sanity check that a rendered deck has
# the wiring it needs to actually boot the player.
#
# Auto-detects which layout pack the deck uses (from data-layout-pack on
# .deck for feishu-deck-h5, or from the rolling-deck template fingerprint)
# and runs the appropriate per-pack checklist.
#
# Usage:
#   bash plugin/skills/feishu-deck-h5/assets/verify-deck-shell.sh <deck-dir>
#
# Past mistakes this catches:
#   · feishu-deck-h5: forgot the two <script> tags before </body>
#                     → slides render but no nav / scale / edit
#   · rolling-deck:   spliced new <section>s but accidentally deleted the
#                     <div class="deck-controls"> + <aside class="confirm-panel">
#                     block that lived between the last </section> and </main>
#                     → JS loads but every getElementById returns null,
#                       silently no controls
#
# Exits non-zero on any missing wiring.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: bash verify-deck-shell.sh <deck-dir>" >&2
    exit 2
fi

DIR="$1"
INDEX="$DIR/index.html"
ERRORS=0

fail() { echo "  ✗ $1" >&2; ERRORS=$((ERRORS+1)); }
ok()   { echo "  ✓ $1"; }

if [[ ! -f "$INDEX" ]]; then
    echo "ERROR: index.html missing under $DIR" >&2
    exit 1
fi

# ─── Detect pack ───────────────────────────────────────────────────────────
# feishu-deck-h5: <div class="deck" data-layout-pack="feishu-deck-h5">
# rolling-deck:   <main class="deck" id="deck"> + cover-hero particle canvas
PACK=""
if grep -qE 'class="deck"[^>]*data-layout-pack="feishu-deck-h5"' "$INDEX"; then
    PACK="feishu-deck-h5"
elif grep -qE '<main[^>]*class="deck"[^>]*id="deck"' "$INDEX" && \
     grep -q 'particle-canvas' "$INDEX"; then
    PACK="rolling-deck"
fi

if [[ -z "$PACK" ]]; then
    echo "==> $DIR" >&2
    echo "ERROR: cannot detect layout pack. Expected ONE of:" >&2
    echo "  · feishu-deck-h5:  .deck must have data-layout-pack=\"feishu-deck-h5\"" >&2
    echo "  · rolling-deck:    <main class=\"deck\" id=\"deck\"> + particle-canvas" >&2
    exit 1
fi

echo "==> checking deck shell at: $DIR"
echo "    detected layout pack: $PACK"

# ─── feishu-deck-h5 wiring ────────────────────────────────────────────────
if [[ "$PACK" == "feishu-deck-h5" ]]; then
    for f in \
        "$DIR/_renderer/assets/feishu-deck.css" \
        "$DIR/_renderer/assets/feishu-deck.js" \
        "$DIR/_renderer/assets/edit-mode/deck-edit-mode.css" \
        "$DIR/_renderer/assets/edit-mode/deck-edit-mode.js"
    do
        if [[ -f "$f" ]]; then ok "asset present: ${f#$DIR/}"
        else fail "asset MISSING: ${f#$DIR/}"
        fi
    done

    check_ref() {
        if grep -qE "$1" "$INDEX"; then ok "index.html references $2"
        else fail "index.html does NOT reference $2"
        fi
    }
    check_ref '<link[^>]+_renderer/assets/feishu-deck\.css'         'feishu-deck.css'
    check_ref '<script[^>]+_renderer/assets/feishu-deck\.js'        'feishu-deck.js'
    check_ref '<link[^>]+_renderer/assets/edit-mode/deck-edit-mode\.css'  'edit-mode css'
    check_ref '<script[^>]+_renderer/assets/edit-mode/deck-edit-mode\.js' 'edit-mode js'

    if grep -q 'id="fs-boot-check"' "$INDEX"; then
        ok "runtime boot-check banner present"
    else
        fail "runtime boot-check banner missing — copy plugin/skills/feishu-deck-h5/assets/boot-check.partial.html"
    fi
fi

# ─── rolling-deck wiring ──────────────────────────────────────────────────
if [[ "$PACK" == "rolling-deck" ]]; then
    # 1. logo asset present
    if [[ -f "$DIR/assets/rolling-ai-logo.svg" ]]; then
        ok "asset present: assets/rolling-ai-logo.svg"
    else
        fail "asset MISSING: assets/rolling-ai-logo.svg (cp from plugin/skills/rolling-deck/assets/)"
    fi

    # 2. brand-rail wired with the logo
    if grep -qE 'class="brand-rail"' "$INDEX" && \
       grep -qE '<img[^>]+class="rolling-logo"[^>]+rolling-ai-logo\.svg' "$INDEX"; then
        ok "brand-rail uses real rolling-ai-logo.svg"
    else
        fail "brand-rail missing or not pointing at assets/rolling-ai-logo.svg"
    fi

    # 3. cover-hero is the FIRST slide and has the particle canvas + active class
    if grep -qE '<section[^>]+class="slide active cover-hero"' "$INDEX"; then
        ok "cover-hero is first slide with class=\"active\""
    else
        fail "first slide must be <section class=\"slide active cover-hero\">"
    fi
    if grep -q '<canvas class="particle-canvas" id="particleCanvas">' "$INDEX"; then
        ok "particle-canvas present inside cover-hero"
    else
        fail "particle-canvas missing — cover earth animation won't render"
    fi

    # 4. Controls block — THE EASY-TO-DELETE BIT. Each ID must exist.
    #    These live between the last </section> and </main> in the template
    #    and the JS hard-references them by id. If you splice new slides
    #    you can accidentally wipe them — every control silently breaks.
    for need_id in prevBtn nextBtn pageNo fullscreenBtn upBtn downBtn \
                   confirmToggle confirmPanel confirmClose modeSwitch \
                   editTools confirmEdit exportPdf progressBar; do
        if grep -qE "id=\"$need_id\"" "$INDEX"; then
            ok "control element present: #$need_id"
        else
            fail "control element MISSING: #$need_id (deck-controls block was deleted?)"
        fi
    done

    # 5. The init script tail — show(0) must be the last JS line that runs.
    if grep -qE '\bshow\(0\)\s*;' "$INDEX"; then
        ok "init call show(0) present"
    else
        fail "init call show(0) missing — slides won't activate"
    fi
fi

echo
if [[ $ERRORS -gt 0 ]]; then
    echo "==> FAIL: $ERRORS issue(s) found. Fix before shipping." >&2
    exit 1
else
    echo "==> OK: $PACK deck shell wiring looks correct."
fi
