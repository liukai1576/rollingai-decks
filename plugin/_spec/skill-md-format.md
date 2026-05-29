# SKILL.md format

Every skill in `plugin/skills/<id>/` has a `SKILL.md` at its root. The
front-matter YAML is the **machine-readable** part (consumed by the
registry); the body below `---` is markdown documentation read by humans
and by the LLM at invocation time.

## YAML frontmatter — required fields

| Field | Type | Notes |
|---|---|---|
| `name` | string | Display name (often same as the dir id) |
| `kind` | string OR string[] | One or more of: `构思`, `创建`, `布局风格`, `调整`, `管理分析`. Categories are fuzzy — multi-valued is fine. |
| `description` | string (multi-line ok) | One paragraph. What the skill does, what it doesn't. |

## YAML frontmatter — recommended fields

| Field | Type | Notes |
|---|---|---|
| `input` | string | What the skill consumes ("path to .key", "deck output dir", etc.) |
| `output` | string | What the skill produces ("deck output dir", "modified deck.json", "thumbs jpg") |
| `triggers` | string[] | Plain-language phrases that should make Claude invoke this skill. |
| `invocation` | string (multi-line ok) | Shell / Python command. Use placeholders like `<input>`, `<output>`. |
| `requires` | string[] | Hard prerequisites: OS / installed apps / Python packages. |
| `version` | string | Skill's own version. Bump on contract changes. |

## YAML frontmatter — optional fields

| Field | Type | Notes |
|---|---|---|
| `produces_layout_pack` | bool | True if this skill is a layout pack (also expects `pack.json`). |
| `reads_history` | bool | True if the skill cares about `history.json`. |
| `appends_history` | bool | True if the skill should write a history entry after running. |

## Example: a "transformer" type skill

```yaml
---
name: punchy-titles
kind: [调整]
version: "0.1"
description: |
  Reads deck.json, rewrites slides[].title via LLM to be more eye-catching,
  writes back to deck.json. Re-render via plugin/_player/render.py picks up
  the new titles. Title is content; never edit data.html directly.
input:  deck output directory (with deck.json)
output: same directory, deck.json updated
triggers:
  - "把标题改得更抓眼球"
  - "rewrite titles"
  - "punchy titles"
invocation: |
  python3 plugin/skills/punchy-titles/apply.py <output-dir>
requires:
  - ANTHROPIC_API_KEY in env
appends_history: true
---
```

## Example: a "layout pack" skill

```yaml
---
name: rolling-deck-h5
kind: [布局风格]
version: "0.20"
description: |
  Lark-flavored deck H5 layout pack. 13 base layouts (cover, agenda,
  section, content, stats, flow, quote, image-text, table, logo-wall,
  arch-stack, iframe-embed, end) + 2 specials (replica, raw).
input:  deck.json with layout_pack="rolling-deck-h5"
output: index.html + per-slide rendered HTML
triggers:
  - "feishu style"
  - "lark style"
produces_layout_pack: true
---
```

Layout packs additionally ship a `pack.json` — see
`plugin/_player/README.md`. The `SKILL.md` is the human / LLM-facing
documentation; the `pack.json` is the player's wiring.

## Registry behavior

`plugin/skills/registry.py` scans every `plugin/skills/*/SKILL.md`,
parses the frontmatter, returns a JSON list with the above fields plus
a `path` to the SKILL.md. The admin UI's 技能 tab groups by `kind`.
