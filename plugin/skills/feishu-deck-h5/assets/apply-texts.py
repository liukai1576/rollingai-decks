#!/usr/bin/env python3
"""
feishu-deck-h5  ·  apply-texts

Reads a sidecar `texts.md` and patches every text node in `deck.html`
whose element carries a matching `data-text-id` attribute. Layout, CSS,
SVG mocks, decorations are untouched — only textContent of marked leaves
changes.

Usage:
    python3 assets/apply-texts.py path/to/deck.html path/to/texts.md
    python3 assets/apply-texts.py path/to/deck.html path/to/texts.md --dry-run
    python3 assets/apply-texts.py path/to/deck.html path/to/texts.md --check

Modes:
    (default)  patches deck.html in place, writes a `.bak` copy first
    --dry-run  prints the diff hunks that would change, writes nothing
    --check    fails (exit 1) if any drift exists between texts.md and HTML

Round-trip rules:
    `<br>` in HTML  ⇄  literal `\n` in texts.md value
    Inline tags other than `<br>` are NOT supported on a single leaf —
    split into separate leaves with their own ids.

Exit codes:
    0  applied (or check passed)
    1  drift detected (--check) / unknown id / duplicate id
    2  cannot read input
"""

from __future__ import annotations
import argparse
import re
import shutil
import sys
from pathlib import Path

# Shared symbols with extract-texts.py — moved to texts_common.py
# (PEP-8 module name) so both scripts can import cleanly. The hyphenated
# filenames of the public-facing scripts stay (they're documented in
# SKILL.md and in the deliverable zip), but internal sharing goes through
# the underscored helper.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texts_common import (
    TEXT_LEAF_RE,
    encode_value_to_inner,
    decode_inner_to_value,
    find_leaves,
)

# --------------------------------------------------------------------------
#  texts.md parser
# --------------------------------------------------------------------------

SLIDE_HEADER_RE = re.compile(r'^##\s+(slide-\d+)\b')
KV_RE           = re.compile(r'^([A-Za-z0-9_.\-]+)\s*:\s*(.*)$')


def parse_texts_md(md_text: str) -> dict[str, str]:
    """Return {full-id: value}. Multi-line values use trailing `\\` joiner."""
    out: dict[str, str] = {}
    current_slide: str | None = None
    pending_id: str | None = None
    pending_val: list[str] = []

    def flush():
        nonlocal pending_id, pending_val
        if pending_id is not None:
            value = '\n'.join(pending_val).rstrip()
            value = value.replace('\\n', '\n')
            out[pending_id] = value
        pending_id = None
        pending_val = []

    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line:
            flush(); continue
        if line.startswith('>'):
            flush(); continue
        m_hdr = SLIDE_HEADER_RE.match(line)
        if m_hdr:
            flush()
            current_slide = m_hdr.group(1)
            continue
        if line.startswith('#'):
            flush(); continue
        # continuation line for previous value (indented OR escaped newline)
        if pending_id is not None and (raw.startswith(('  ', '\t')) or raw.startswith(' ')):
            pending_val.append(line.lstrip())
            continue
        m_kv = KV_RE.match(line)
        if m_kv and current_slide:
            flush()
            field, value = m_kv.group(1), m_kv.group(2)
            pending_id = f'{current_slide}.{field}'
            pending_val = [value]
            continue
        # everything else: treated as continuation of value if there's one
        if pending_id is not None:
            pending_val.append(line)
    flush()
    return out


# --------------------------------------------------------------------------
#  HTML scanner symbols moved to texts_common.py (TEXT_LEAF_RE, find_leaves,
#  encode_value_to_inner, decode_inner_to_value). See imports at top.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
#  Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description='feishu-deck-h5 apply-texts',
        epilog='With no positional args, defaults to ./index.html and '
               './texts.md in the same directory as this script — so the '
               'shipped deliverable zip can run as a one-shot.')
    ap.add_argument('html',  nargs='?', default=None,
                    help='deck HTML file (modified in place). '
                         'Defaults to <script-dir>/index.html.')
    ap.add_argument('texts', nargs='?', default=None,
                    help='paired texts.md sidecar. '
                         'Defaults to <script-dir>/texts.md.')
    ap.add_argument('--dry-run', action='store_true',
                    help='print would-change diffs, write nothing')
    ap.add_argument('--check', action='store_true',
                    help='exit 1 if texts.md differs from HTML; write nothing')
    ap.add_argument('--no-backup', action='store_true',
                    help='skip the .bak copy on in-place write')
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    html_path  = Path(args.html)  if args.html  else here / 'index.html'
    texts_path = Path(args.texts) if args.texts else here / 'texts.md'
    if not html_path.is_file():
        print(f'ERROR: html not found: {html_path}', file=sys.stderr); return 2
    if not texts_path.is_file():
        print(f'ERROR: texts.md not found: {texts_path}', file=sys.stderr); return 2

    html      = html_path.read_text(encoding='utf-8')
    texts_md  = texts_path.read_text(encoding='utf-8')
    new_texts = parse_texts_md(texts_md)
    leaves    = find_leaves(html)

    # 1) duplicate-id check (always)
    seen: dict[str, int] = {}
    dups: list[str] = []
    for tid, *_ in leaves:
        seen[tid] = seen.get(tid, 0) + 1
    for tid, n in seen.items():
        if n > 1:
            dups.append(f'{tid}×{n}')
    if dups:
        print('ERROR: duplicate data-text-id in HTML:', file=sys.stderr)
        for d in dups:
            print(f'  - {d}', file=sys.stderr)
        return 1

    html_ids   = set(seen.keys())
    md_ids     = set(new_texts.keys())
    missing_md = sorted(html_ids - md_ids)        # in HTML but not in texts.md
    extra_md   = sorted(md_ids - html_ids)        # in texts.md but not in HTML

    # 2) compute diffs
    changes: list[tuple[str, str, str]] = []
    for tid, _s, _e, _open, inner, _close, _full in leaves:
        if tid not in new_texts:
            continue
        old_value = decode_inner_to_value(inner)
        new_value = new_texts[tid]
        if old_value != new_value:
            changes.append((tid, old_value, new_value))

    # 3) reporting
    print(f'apply-texts  ·  {html_path.name}  ⇄  {texts_path.name}')
    print(f'  HTML text leaves : {len(leaves)}')
    print(f'  texts.md entries : {len(new_texts)}')
    print(f'  changes          : {len(changes)}')
    if missing_md:
        print(f'  ! ids in HTML but missing from texts.md ({len(missing_md)}):')
        for tid in missing_md[:10]:
            print(f'    - {tid}')
        if len(missing_md) > 10:
            print(f'    … +{len(missing_md)-10} more')
    if extra_md:
        print(f'  ! ids in texts.md but missing from HTML ({len(extra_md)}):')
        for tid in extra_md[:10]:
            print(f'    - {tid}')
        if len(extra_md) > 10:
            print(f'    … +{len(extra_md)-10} more')

    for tid, old, new in changes[:20]:
        print(f'\n  ~ {tid}')
        print(f'      - {old!r}')
        print(f'      + {new!r}')
    if len(changes) > 20:
        print(f'\n  … +{len(changes)-20} more changes')

    # 4) check mode — fail on any drift
    if args.check:
        drift = bool(changes or missing_md or extra_md)
        if drift:
            print('\nFAIL — drift detected. Run without --check to apply.')
            return 1
        print('\nPASS — texts.md and HTML are in sync.')
        return 0

    # 5) dry-run — stop before writing
    if args.dry_run:
        print('\n(dry-run, wrote nothing)')
        return 0

    # 6) apply changes
    if not changes:
        print('\nno textual changes to apply.')
        return 0

    # rebuild html by replacing inner of each changed leaf, walking back-to-front
    # so offsets stay valid.
    chg_by_id = {tid: (old, new) for tid, old, new in changes}
    new_html = html
    # use a fresh scan because we already have offsets; iterate reversed
    for tid, s, e, open_tag, inner, close_tag, full in reversed(leaves):
        if tid not in chg_by_id:
            continue
        _old, new_value = chg_by_id[tid]
        new_inner = encode_value_to_inner(new_value)
        new_full  = open_tag + new_inner + close_tag
        new_html  = new_html[:s] + new_full + new_html[e:]

    # Post-apply DOM sanity check — count <div> open vs close in the new
    # body. If they diverge, a textual substitution almost certainly ate
    # a `</div>` (e.g. a value containing literal `<` or `>` got escaped
    # in an unexpected way). Refuse to write and surface the delta.
    # This is the safety net for the apply-texts pipeline that complements
    # validator R-DOM on the deck level.
    def _div_balance(text: str) -> tuple[int, int]:
        body_m = re.search(r'<body[^>]*>(.*)</body>', text, re.S)
        body = body_m.group(1) if body_m else text
        body = re.sub(r'<!--.*?-->',           '', body, flags=re.S)
        body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.S)
        body = re.sub(r'<style[^>]*>.*?</style>',   '', body, flags=re.S)
        opens  = len(re.findall(r'<div\b', body))
        closes = len(re.findall(r'</div>', body))
        return opens, closes

    old_opens, old_closes = _div_balance(html)
    new_opens, new_closes = _div_balance(new_html)
    old_delta = old_opens - old_closes
    new_delta = new_opens - new_closes
    if new_delta != old_delta:
        print(
            f'\nERROR: post-apply DOM imbalance — original div delta '
            f'{old_delta:+d} ({old_opens} open / {old_closes} close) '
            f'changed to {new_delta:+d} after apply. A texts.md value '
            f'almost certainly contained literal `<` or `>` that the '
            f'encoder mishandled, or the HTML was already corrupt. '
            f'NOT writing the file. Inspect texts.md for values with '
            f'unescaped angle brackets; the apply contract is that '
            f'text replacement never touches DOM structure.',
            file=sys.stderr)
        return 1

    if not args.no_backup:
        bak = html_path.with_suffix(html_path.suffix + '.bak')
        shutil.copy2(html_path, bak)
        print(f'\nbacked up: {bak.name}')
    html_path.write_text(new_html, encoding='utf-8')
    print(f'wrote: {html_path}  ({len(changes)} change(s))')
    return 0


if __name__ == '__main__':
    sys.exit(main())
