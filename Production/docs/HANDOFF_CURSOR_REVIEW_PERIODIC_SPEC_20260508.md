# Handoff — Cursor Cross-Review of PERIODIC Class Tech Spec

**For:** Cursor (with Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (867 lines, dual-Opus debated)

---

## What to do in Cursor

1. Open the project root in Cursor: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`
2. Open `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` in the editor
3. Open Cursor Composer or chat
4. Paste the prompt below

---

## Prompt to paste into Cursor

```
I have a tech spec at Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md (867 lines) that was authored via dual-Opus debate (one advocate, one counter) and concluded the Advocate wins with two Counter-derived modifications.

The spec proposes adding a third "PERIODIC" class to our SHORTCUT LD classification system (alongside existing EVENT_DRIVEN and RARE_NEVER). It would add 3 new fields to the prod_locked_decisions Directus table (review_cadence, next_review_date, last_reviewed_date) and a new branch in our weekly audit logic.

I want an independent cross-review. Read the spec end-to-end. Then identify:

1. ARCHITECTURAL CONCERNS not covered:
   - What schema migration risks aren't addressed?
   - What downstream tooling could break? (anything else that reads prod_locked_decisions and expects the current 22 fields?)
   - Are there test gaps in the implementation phases?

2. CLASSIFICATION SYSTEM CONCERNS:
   - Is "PERIODIC" the right name? Other ecosystems call this "scheduled review" or "recurring decision" — does the proposed name carry implicit baggage?
   - The 6 cadence enum values are: monthly, quarterly, semi-annually, annually, event-driven, none. Are any missing? Any redundant? Should "biweekly" or "5-year" be options?
   - The migration cohort is just LD 249. Is the spec convincing that LD 200 should stay EVENT_DRIVEN (the Counter's argument)? Or did the Advocate cave too easily?

3. AUDIT LOGIC CONCERNS:
   - Spec proposes WARN at day 0 of past-due, CRITICAL at +7 days. Other tools warn earlier (30 days before due) for periodic reviews. Is "warn day 0 / critical +7" too late?
   - Should there be a "missed-review" auto-escalation (e.g., if next_review_date is past by 30 days with no last_reviewed_date update, auto-CRITICAL)?

4. DECISIONS THAT WERE DEBATED BUT MIGHT MERIT RE-DEBATE:
   - Spec §5.4 defers `last_reviewed_date` cadence-consistency check to v2. Is this the right call, or is it a v1 must-have?
   - Spec §5.5 reuses severity=critical with title prefix. Is a new severity (e.g., "review-overdue") better?

5. RISKS NOT IN §13 (Risk Assessment):
   - What happens if Directus loses a `next_review_date` value silently (data loss)? Audit fail-mode?
   - What if the audit runs before the schema migration completes?
   - What if Kim updates LD 249 manually during Phase B and the migration overwrites her edit?

6. IMPLEMENTATION SEQUENCING:
   - Phases A→G in §16 — is there a phase ordering risk? E.g., should Phase F (LD authoring) come before Phase A (schema migration)?
   - Could any phase be parallelized to reduce wall-clock time?

For each concern: short-form analysis (2-3 sentences). Don't try to redesign — just flag what the dual-Opus debate may have missed.

End with a bottom-line question: should Kim authorize implementation as-written, request a v2 amendment, or pause for more debate?
```

---

## Why ask Cursor

Cursor's strengths complement Claude Code:
- Different model architecture catches different blind spots
- Codebase-context navigation in Cursor is excellent
- Independent reviewer per memory `feedback_cursor_integration` (architectural Phase 3 cross-review pattern)

The spec was dual-Opus debated within a single session — same training, same context, same biases. Cursor adds a true outside-view check.

---

## After Cursor responds

Bring the response back to Claude Code (paste into the next session, or copy the salient findings into a v2 amendment doc). If Cursor flags ≥1 substantive concern, author `PERIODIC_CLASS_TECH_SPEC_v2.md` addressing it before authorizing implementation. If Cursor returns "looks good, no major concerns" — authorize implementation.

---

## What you DON'T need to do

- Don't have Cursor edit the spec (let it review only)
- Don't have Cursor implement anything (that's the Terminal CLI handoff at `HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`)
- Don't paste sensitive info; the spec doesn't contain any
