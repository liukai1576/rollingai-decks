---
name: tag-refine
display_name: 标签精修
kind: [管理分析]
version: "0.3"
input:  slides.db (existing slides + stories rows)
output: slides.db with type/subtype/customer/free_tags refined from story context
triggers:
  - "第二轮打标"
  - "refine tags from story context"
  - "把孤立 slide 标 needs-review"
invocation: |
  python3 library/db/refine_tags.py
---

# tag-refine

Second-pass tagging. Runs **after** `deck-ingest` (which does the rough
heuristic pass) and **after** `STORY-PROPOSAL` stories are loaded.

For each story, infers:

- Story title contains a customer name → propagate `customer_tag` to all
  member slides that don't have one
- Story title says "方法论 X" → propagate `type_tag='方法论'`
- Slide is not in any story → tag `free_tags += ['needs-review']`
- Slide title is empty / a placeholder / pure number → rewrite to
  `(pN · 待补标题)`

This is idempotent: running twice produces the same DB.

## When to invoke

- Right after loading stories for a new deck
- Whenever you change the STORY-PROPOSAL.md taxonomy

## See also

- `deck-ingest` — first-pass tagging
- `library/db/data/STORY-PROPOSAL.md` — the tag convention
