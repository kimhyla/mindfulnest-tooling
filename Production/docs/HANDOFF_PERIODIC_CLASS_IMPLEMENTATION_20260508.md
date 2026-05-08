# Handoff — PERIODIC Class Implementation (Terminal CLI)

**For:** dedicated Terminal Claude Code CLI session
**From:** worktree `gallant-bouman-804b4f` session, 2026-05-08
**Source spec:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (867 lines, dual-Opus reviewed)
**Estimated time:** 4–6 hours autonomous execution; depends on Directus schema migration + audit refactor latency.

---

## What you're doing

Implementing the PERIODIC class for SHORTCUT-style LDs per the tech spec. This adds a third classification (alongside EVENT_DRIVEN and RARE_NEVER) for "deliberate calibration with scheduled re-evaluation cadence" decisions.

The spec is design-only. You execute Phases A→G defined in §16 of the spec. Each phase has an audit-checklist gate.

---

## Pre-flight (MUST do before starting)

1. **Read the spec end-to-end.** Don't skim. Especially §5 (per-decision resolutions), §6 (class-level meta-debate), §7 (migration cohort), §15 (pre-implementation gates), §16 (sequence).

2. **Confirm the 10 pre-implementation gates have been Kim-approved.** If §15's gates 1-10 are NOT yet checked off in this handoff or in `prod_locked_decisions` notes, HALT and surface to Kim — do NOT proceed without authorization.

3. **Read these reference files:**
   - `Production/scripts/weekly_preflight_audit.py` — current state of `check_shortcut_ld_closure_dates` + `check_pr_merge_closure_events` + the SHORTCUT_LD_CLASSIFICATION dict
   - `Production/docs/MINDFULNEST_PROFESSIONAL_SETUP_ROADMAP_v1.md` §1.6 (current SHORTCUT table) and §1.7 (LD 576 PR-merge auto-close)

4. **Verify Directus access** via `lib/directus_admin_client.py`. Test by querying `/fields/prod_locked_decisions` — confirm 22 fields present.

5. **Verify the migration cohort.** GET LD 249 from Directus — confirm current `notes` matches what the spec describes. If notes have drifted (e.g., re-classified to something else by another session), HALT.

---

## Execute Phase A → G per spec §16

The spec breaks implementation into 7 phases. Read §16 carefully — each has explicit deliverables, audit-checklist gates, and rollback procedure.

**Phase A — Schema migration (Directus):** add 3 new fields to `prod_locked_decisions`:
- `review_cadence` enum (monthly, quarterly, semi-annually, annually, event-driven, none)
- `next_review_date` (date, optional at DB level)
- `last_reviewed_date` (date, optional)

**Phase B — Migration cohort PATCH:** PATCH LD 249 to PERIODIC class with `review_cadence: quarterly`, `next_review_date: 2026-07-18`, `last_reviewed_date: 2026-04-18`.

**Phase C — Audit script logic:** add PERIODIC branch to `check_shortcut_ld_closure_dates`. WARN at days_until_review = 7; CRITICAL at days_overdue ≥ 0.

**Phase D — SHORTCUT_LD_CLASSIFICATION dict:** add LD 249 → PERIODIC.

**Phase E — Roadmap §1.6 update:** add PERIODIC column to the table; update LD 249 row.

**Phase F — LD authoring:** author `PERIODIC_CLASS_ESTABLISHMENT_V1` in `prod_locked_decisions` documenting the new class.

**Phase G — Verification:** dry-run audit, confirm zero false positives + LD 249 emits no warning yet (next_review_date is in the future).

Each phase has rollback. Document each phase's actual diff and audit-output verbatim.

---

## Hard rules

- Per Rule 35: read-back-after-write for every Directus PATCH/POST.
- Multipass: re-Read every file after edit.
- Rule 24: confidence tags throughout.
- DS-13 Layer 6: for each new audit logic branch, write a synthetic test that proves WARN fires at 7 days, CRITICAL at 0 days, and silent at >7 days.
- DS-23 (post-fix pattern sweep): if you change cap-decision logic, grep the audit script for ALL classification branches and ensure each one is exercised.
- HALT if any audit dry-run shows unexpected new findings (other than the expected migration of LD 249).

---

## Final report

Write a final proof report at `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_<DATE>.md`:

1. Per-phase diff (verbatim)
2. Per-phase audit-checklist results
3. LD 249 before/after state
4. New LD `PERIODIC_CLASS_ESTABLISHMENT_V1` row id captured
5. Roadmap §1.6 before/after
6. Final dry-run audit output
7. Confidence tags per Rule 24
8. Self-classification per change
9. Limitations + future-state
10. Authorization for Kim's review

---

## What NOT to do in this session

- Do NOT migrate any LD other than 249 to PERIODIC (the spec explicitly excludes LD 200; do not second-guess).
- Do NOT add a `consistency_check` against `last_reviewed_date` (spec §5.4 explicitly defers to v2).
- Do NOT modify the warn-vs-block thresholds (spec §5.3 sets WARN day-0, CRITICAL +7).
- Do NOT touch existing EVENT_DRIVEN or RARE_NEVER LDs.

---

## Context for the agent

Session origin: `gallant-bouman-804b4f`, 2026-05-08, ran in parallel with PR #8 V59 gap-fix follow-up work. The PERIODIC class question arose when 4 retroactively-capped LDs (199, 200, 201, 249) were triaged. LDs 199 + 201 closed; LD 200 mapped to EVENT_DRIVEN; LD 249 mapped to EVENT_DRIVEN as INTERIM pending PERIODIC class. This implementation completes the INTERIM resolution.

Prior commits to be aware of (Dropbox tree, may not yet be committed):
- audit script meta-fix B+C (prospective-only cap + grandfather rule)
- LD 545 auto-close protocol (LD 576 + `check_pr_merge_closure_events` sub-check)
- DS-23/24/25 zero-error-qa amendments

Verify against current state before assuming — Dropbox-tree commit status as of handoff: see git status when you start.
