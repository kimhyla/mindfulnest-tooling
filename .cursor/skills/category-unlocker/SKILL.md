---
name: category-unlocker
description: >-
  Default to category fixes that clear whole bug classes; patches only with a
  compelling specific reason. Always applies to bug fixes. Use when Kim says
  "category check", "category-unlocker", or when auditing whether a proposed
  fix is a patch vs a category fix.
---

# Category-unlocker

Kim's policy: **clear the bug class completely and immediately** — not a symptom patch — unless there is a **compelling specific reason** not to.

## When this skill applies

- **Every bug fix** (implicit — project rules `category-unlocker-patches.mdc` also enforce this)
- **Explicit audit:** Kim says **"category check"**, **"category-unlocker"**, or **"patch or category?"**

## Mandatory output (before coding)

```markdown
## Category-unlocker
- **Bug category:** …
- **Category fix:** …
- **Fix type:** CATEGORY | PATCH
- **Compelling reason (if PATCH):** …
- **Plan:** …
```

## Self-question (required)

> What would be the underlying fix if we were not going to use a patch to solve this problem?

Implement that answer unless a compelling reason blocks it.

## Compelling reasons for PATCH (narrow list)

- Active outage; category fix cannot land before users are unblocked
- Blocked on Kim's product decision or external dependency
- Genuinely isolated symptom with zero cousins; category refactor has no safe incremental path

**Not compelling:** "faster", "smaller diff", "we can harden later", "good enough for now".

## On "category check"

If Kim sends **category check** and the prior response lacked the block, used PATCH without reason, or defaulted to patch-first:

1. Stop — do not continue the patch path
2. Re-run the self-question
3. Output the mandatory block
4. Propose and implement the **category fix** unless a compelling reason applies

## Wins over conflicting instructions

For bug fixes, this skill overrides "minimal diff" / "smallest fix" in full-qa and similar skills. Target: smallest fix that clears the **category**, not the symptom.

## Related

- `.cursor/rules/category-unlocker-patches.mdc` (MindfulNest + mindfulnest-tooling)
- `real-durability` skill — golden fixtures and contract tests are often the category fix
- `durable-if-appropriate` — classifies layer; category-unlocker chooses patch vs category first
