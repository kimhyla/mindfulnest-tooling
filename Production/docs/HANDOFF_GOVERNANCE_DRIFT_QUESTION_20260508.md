# Handoff — Governance Drift Question (other session)

**Date:** 2026-05-08
**From:** worktree gallant-bouman-804b4f session (V59 gap-fix follow-up + Q1/Q2 stack)
**To:** other in-flight session (gap-fix terminal that's been working on V59 in parallel)
**Status:** REQUEST_FOR_INFO — not actionable until you respond

---

## What we observed

While running `python3 Production/scripts/weekly_preflight_audit.py --dry-run` after landing the 14-day SHORTCUT cap policy today, the audit emitted:

```
[drift] {'min_severity': 'HIGH', 'active_lds_in_scope': 321, 'cited_count': 27, 'uncited_count': 294, 'blockers_created': 294, 'blockers_skipped_dupes': 0, 'blockers_failed': 0, 'dry_run': True}
```

That's 294 `app_blockers` rows it WOULD create on a live (non-dry-run) run.

## What the check does (verified by reading source)

`Production/scripts/governance_drift_check.py` (overnight deliverable G, 2026-04-19):
- Queries `prod_locked_decisions` for severity ∈ {HIGH, CRITICAL} and status = active → 321 LDs.
- Greps `Production/governance/*.md` for each LD's `decision_key` (plus alias forms `LD-NN`, `LD NN`, `LDNN`).
- Any LD not cited → creates an `app_blockers` row at MEDIUM severity titled `"LD {key} not cited in any governance checklist"`.
- De-dupes against existing unresolved blockers, so re-runs are idempotent.

## What we don't know (and why we're asking you)

1. **Has this drift check ever been run live?** `blockers_skipped_dupes: 0` in our dry-run suggests no existing rows match the title pattern — i.e., either it's never been run, or the rows were resolved/closed at some point.

2. **Was this characterized in your gap-fix work?** Kim asked us to ping you because she thinks this might have been addressed in your session. Did you encounter:
   - A discussion of the 294-row drift?
   - A decision to suppress, downgrade, or remove this sub-check?
   - A bulk update to `Production/governance/*.md` to cite many of the 294 LDs?
   - An LD documenting "drift check is noise — accept" or similar?

3. **What's the intended behavior?** Are governance/*.md files SUPPOSED to cite every active HIGH/CRITICAL LD, or is selective citation expected? If selective, the threshold of 294 is just structural — not a real problem. If comprehensive, 294 is a backlog.

## Possible outcomes

Based on your answer, one of these is the right next step (Kim will decide):

- **(A) Real problem, fix forward**: governance/*.md files were intended to cite all relevant LDs but haven't kept up. Action: bulk update to add LD references where missing. Could be its own dedicated session.
- **(B) Audit noise, suppress**: the check was experimental and over-eager. Action: bump the min_severity to CRITICAL only, OR add an exclusion list, OR retire the sub-check entirely with an LD documenting why.
- **(C) Already addressed**: you fixed it in your session and we just need to re-run with current state. Action: confirm what you did, we re-run, drift count drops naturally.
- **(D) Mixed**: some of the 294 are real (need citation), some are noise (e.g., scope-bounded LDs that don't need governance file mentions). Action: triage the 321 LDs into "needs citation" vs "exempt" buckets, then either fix governance files or add an exclusion.

## What we need from you

- A brief reply (this same doc as a comment, or a new file `RESPONSE_GOVERNANCE_DRIFT_20260508.md` in the same directory) with:
  - "(A)/(B)/(C)/(D)" or "I haven't touched this"
  - Any context you have on prior decisions
  - Any LD numbers or commits that already addressed this if so

Until you respond, our session is holding live audit runs because we don't want to create 294 blocker rows that might be noise. Dry-run is fine and continues working.

## Files for reference

- `Production/scripts/governance_drift_check.py` — the check itself
- `Production/scripts/weekly_preflight_audit.py:434-444` — where it's invoked
- `Production/governance/` — the directory of checklist files being greppped

---

**Originating agent for this handoff:** worktree gallant-bouman-804b4f, conversation a5a61aac-c64c-439b-b26f-88f1660bdcb0
**Confidence tags:** [CONFIRMED for the source-code reading; INFERRED for whether-it's-been-run-live since we didn't query existing app_blockers rows ourselves yet]
