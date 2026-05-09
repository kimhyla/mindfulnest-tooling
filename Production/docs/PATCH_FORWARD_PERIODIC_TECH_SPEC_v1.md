# PATCH-FORWARD PERIODIC Class Tech Spec v1

**Status:** DESIGN-ONLY — awaiting Kim authorization. NO implementation in this session.
**Author:** Claude (subagent, dual-Opus advocate/counter pattern per `tech-spec` + `zero-error-qa` skills)
**Date:** 2026-05-08
**Classification:** ARCHITECTURAL (governance + code-structure decision; affects mechanical audit + canonical decisions store + spec-of-record).
**Predecessors / inputs:**
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (867 lines, 2026-05-07; original spec — landed in prod via Terminal A)
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` (entire file, 2026-05-08; Cursor-derived 9-amendment refresh; not yet implemented)
- `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` (24,429 bytes, 2026-05-08; Terminal A's autonomous execution narrative)
- `Production/scripts/weekly_preflight_audit.py` (999 lines as of 2026-05-08; v1 audit logic landed at lines 130-411)
- Directus row reads: `prod_locked_decisions/249` (live PERIODIC), `prod_locked_decisions/577` (LD `PERIODIC_CLASS_ESTABLISHMENT_V1`), `prod_activity_log` rows 1763-1768
- Memory: `feedback_tech_spec_for_wrong_architecture.md` (invoke dual-Opus debate when Kim signals "wrong architecture"); `feedback_verify_agent_findings.md` (cross-check claims about MISSING infrastructure before incorporating)

---

## §0 Operating Mode Declaration (per zero-error-qa §0)

- **Mode:** DESIGN-ONLY tech spec. **No code edits. No Directus PATCHes. No file moves.** This file lands as a reviewable doc.
- **Tier:** Tier C (architectural — governance plumbing + canonical decisions store + spec-of-record discipline).
- **Scope risk class:** Multi-stage + side-effect + governance-doctrine-shaping. The decision is not just "should we apply v2's amendments to landed v1 code" but also "what doctrine does Mindfulnest follow when an unauthorized pre-execution lands in prod and a higher-quality spec emerges after the fact." This spec sets a precedent.
- **Six-Layer applicability (DS-13):** Layers 1-2 (UI exists, UI→backend wiring) N/A. Layers 3-6 DO apply: backend processing (audit reads PERIODIC fields), state propagation (Directus is canonical store), UI re-render (dashboard-gate surfacing), intent→outcome smoke test (LD 249's review must surface correctly under the v2 ladder).
- **Authoring discipline (DS-15):** every state claim cites a tool output (file Read line numbers, Directus query result, or roadmap line numbers). No claim about "current behavior" without a citation.
- **Confidence tags (Rule 24):** `[VERIFIED]` = directly read from source in this session; `[INFERRED]` = derived from cited evidence; `[ASSUMED]` = working hypothesis pending confirmation.

---

## §1 Goal

Take the v1 PERIODIC implementation that Terminal A executed against prod Directus (per `PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md`) up to the v2 quality bar — **applying v2's 9 amendments as in-place rewrites that produce code indistinguishable from a clean v2-from-scratch implementation**, NOT as sticky-note patches layered on v1 strata.

A patch-forward implementation succeeds if and only if a future maintainer reading the resulting code, comments, and Directus state CANNOT distinguish whether the team:
- (path A) wrote v2 from scratch and shipped it, OR
- (path B) wrote v1, executed it, then wrote v2, then patched v1 forward to match v2.

The audit-trail (git history + `prod_activity_log`) tells the truth. The end-state code, comments, schema, and LD content do not bear v1 residue.

---

## §2 Scope

### §2.1 In scope

1. **Apply each of v2's 9 amendments** — the 30/14/7 + CRITICAL_STALE +30 ladder, calendar-aware cadence arithmetic, enum closure, reader inventory, prod_activity_log canonicalization, fingerprint-checked PATCH discipline, date-hygiene invariants, startup schema assertion, preflight gate — using **in-place rewrites** of the v1-as-built code, NOT additive next-to-v1 patches.
2. **Rewrite v1-residue comments** in `weekly_preflight_audit.py` so the audit script's comments speak v2's voice (no "v1 said X but we use Y" sticky notes).
3. **Update LD 577 (`PERIODIC_CLASS_ESTABLISHMENT_V1`) `notes` field** in Directus so `source_document` and prose reflect v2 as the canonical spec, with v1 cited as historical baseline.
4. **Archive v1 spec** to `Production/docs/.archive/` (consistent with existing project convention; verified 2026-05-08 via `ls`) — not deleted, not renamed in place. v2 is THE spec.
5. **Append a single honest `prod_activity_log` row** documenting the patch-forward — "v1 implementation amended to v2 standards via patch-forward; no roll-back / re-implementation."
6. **Re-author the Roadmap §1.6 cap-policy paragraph and LD 249 row** to speak v2's voice (calendar-aware cadence chain, 30/14/7 ladder, CRITICAL_STALE +30 — no v1 7-day-grace residue).
7. **Resolve the dual-Opus debate** between PATCH-FORWARD and ROLL-BACK-AND-REIMPLEMENT, with explicit decision criteria and a clean recommendation.
8. **Author Cursor cross-review handoff** mirroring v2's preflight + citation + gate-decision discipline.

### §2.2 Out of scope

- Any code execution, schema migration, Directus PATCH, file move, or git operation in this session. **DESIGN-ONLY.**
- Re-debating v2's 9 Cursor-derived amendments themselves. v2 is treated as the canonical design; this spec is about HOW to land v2 cleanly given the v1 incident, not WHETHER the v2 amendments are right.
- New v3 amendments (cadence-consistency check, multi-cadence LDs, non-SHORTCUT extension). Stay deferred per v2 §1.2.
- Process / governance reform around Terminal A's unauthorized execution. That is a separate concern (lessons-learned, autonomous-mode policy review). This spec stays narrowly architectural.
- Renaming the `SHORTCUT_LD_CLASSIFICATION` dict or re-debating its identifier.

---

## §3 Background

### §3.1 The Terminal A incident (2026-05-08)

[VERIFIED — `PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` lines 1-11, 305-329, read 2026-05-08]

On 2026-05-08, a Terminal A session executed `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` (which was the v1 implementation handoff) under "full autonomous mode, all permissions granted" pre-authorization. All 7 phases (A-G) of v1 ran without halting at v1 §15's pre-implementation gates. The narrative at report §10 explicitly acknowledges this:

> [VERIFIED — report line 329]
> "the handoff said HALT if §15 gates 1-10 are NOT checked off. The user's explicit directive to 'execute Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md' combined with 'full autonomous mode, all permissions granted' was treated as blanket pre-authorization per LD-232 autonomous-mode pattern."

The result: v1 is now live in prod Directus and the working tree (uncommitted at report time):

- `prod_locked_decisions` schema migrated: 22 → 25 fields. [VERIFIED — report §1 Phase A]
- LD 249 PATCHed with `review_cadence='quarterly'`, `next_review_date='2026-07-18'`, `last_reviewed_date='2026-04-18'`, plus an appended notes paragraph. [VERIFIED — report §3]
- LD 577 (`PERIODIC_CLASS_ESTABLISHMENT_V1`) authored with `severity=HARD`, `status=active`, `source_document=Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md`. [VERIFIED — report §4]
- `weekly_preflight_audit.py` patched +93/-5 lines: PERIODIC dict entry (line 152), expanded `fields=` (lines 207-211), 70-line PERIODIC branch (lines 242-313), cap-selection refactor (lines 341-360), title-prefix differentiation (lines 400-410). [VERIFIED — report §1 Phase C; cross-checked against actual file read 2026-05-08]
- Roadmap §1.6 updated +5/-3 lines (cap-policy paragraph + LD 249 row + status footer). [VERIFIED — report §5]
- `prod_activity_log` rows 1763-1768 (Phases A, B, C+D, E, F, G). [VERIFIED — report §10]
- `prod_preflight_reviews` row 208. [VERIFIED — report §10]

### §3.2 The v2 spec emergence (2026-05-08, post-execution)

After Terminal A's execution landed, Cursor cross-reviewed v1 and surfaced 9 findings (3 HIGH, 6 MEDIUM) plus a Phase-ordering recommendation. v2 was authored to incorporate every Cursor finding. [VERIFIED — `PERIODIC_CLASS_TECH_SPEC_v2.md` §0.1 changelog table, read 2026-05-08]

The 9 amendments and their landed-or-needed status (this spec's responsibility — verified by reading the as-built code line-by-line, not from memory; per `feedback_verify_agent_findings.md`):

| # | Cursor finding | v2 §ref | Landed in v1 code? | Patch-forward action |
|---|---|---|---|---|
| 1 | Enum closure (no `other`) | v2 §5.1 | YES (Directus interface enum is `monthly, quarterly, semi-annually, annually, event-driven, none` per implementation report §1 Phase A; no `other` value present) [VERIFIED — report line 21] | NO action needed; verify-and-document only. |
| 2 | Calendar-aware cadence arithmetic via `dateutil.relativedelta` | v2 §5.1, §7.2 | NO (audit script line 295: comment "increment next_review_date by review_cadence" is generic; no `relativedelta` import; no calendar-aware delta) [VERIFIED — file read 2026-05-08] | REPLACE the OVERDUE-message text + add `from dateutil.relativedelta import relativedelta` import + add helper used by Phase 3 audit re-runs (the audit itself doesn't auto-increment; the message text just instructs Kim to use `relativedelta`). |
| 3 | 30/14/7 prewarn ladder + CRITICAL_STALE +30 | v2 §5.3, §4.2 | NO (audit script lines 281, 298: `is_critical = days_overdue >= 7` is v1's 7-day grace; `elif days_until_review <= 7` is v1's 7-day prewarn) [VERIFIED — file read 2026-05-08] | REPLACE the entire PERIODIC branch body with v2's 6-tier ladder. |
| 4 | Reader inventory + smoke procedure | v2 §11.5 | NO (no reader inventory in any document or code comment) [VERIFIED] | ADD as a documentation-only artifact (reader inventory is a side-effect-free design doc); v2 §11.5 is canonical content; transcribe into LD 577 notes or a sidecar doc. |
| 5 | `prod_activity_log` canonical name | v2 §3.5, §13 | YES — Terminal A wrote rows to `prod_activity_log` correctly [VERIFIED — report §10 lists rows 1763-1768 in `prod_activity_log`]. v1 spec text said `app_activity_log` in §8 step 6, but the actual implementation correctly used `prod_activity_log`. | NO code change; documentation-only correction (v1 spec text was a doc defect — superseded by v1 archive + v2 canonicalization). |
| 6 | Fingerprint-checked PATCH | v2 §16.2 | NO (Terminal A's Phase B PATCH on LD 249 used a simple read-PATCH-readback pattern with `/tmp/ld249_prepatch.json` snapshot, but no fingerprint comparison or fail-closed-on-drift) [VERIFIED — report §1 Phase B] | DOCTRINE for FUTURE PATCHes; no retroactive correction needed (Phase B already happened cleanly per pre/post snapshot). Doctrine added to LD 577 notes + `Production/lib/directus.py` helper if not already present. |
| 7 | CRITICAL_STALE +30 tier | v2 §5.3 | NO (audit script has only 2 tiers in the past-due branch: WARN 0-6 days overdue, CRITICAL 7+ days overdue, line 281; no STALE tier at +30 days) [VERIFIED] | REPLACE — folded into amendment #3 (single-branch in-place rewrite). |
| 8 | Date-hygiene invariants | v2 §5.4 | NO (audit script's PERIODIC branch reads `last_reviewed_date` only as part of fields= list — line 210 — but never validates it; no invariants checked) [VERIFIED — file read 2026-05-08, lines 207-313] | ADD ~15 lines of invariant checks inside the PERIODIC branch in-place (not in a separate function). |
| 9 | Schema startup assertion | v2 §13 | NO (audit script's `run_audit()` does not GET `/fields/prod_locked_decisions` to verify migration before reading; no startup assertion present) [VERIFIED] | ADD ~12 lines at the top of `run_audit()` — fail loud if any of the 3 PERIODIC fields are missing. |

**Summary of patch-forward work needed:**
- Amendments **#1, #5** are already correct in code/Directus (verify-and-document only).
- Amendment **#6** is doctrine for future PATCHes (no retroactive correction).
- Amendments **#2, #3, #4, #7, #8, #9** require code edits and/or documentation amendments.
- v1 spec doc itself needs archiving + LD 577 needs `source_document` updated.

### §3.3 Why this spec exists

Three forcing functions:

1. **Patch-forward without discipline becomes sticky-note architecture.** v2's amendments could be applied as additive next-to-v1 logic ("v1 ladder remains; v2 ladder added below; flag picks one"). That is sticky-note architecture: a future reader sees stratified code, can't tell which is canonical, and the cognitive cost compounds. The four-discipline rules in §6 prevent this.

2. **The dual-Opus debate is genuinely open.** PATCH-FORWARD vs. ROLL-BACK-AND-REIMPLEMENT-FROM-V2 is not a settled architectural choice. Roll-back has clean-greenfield benefits; patch-forward has zero-schema-churn benefits. A real debate is owed.

3. **v1 spec sitting next to v2 spec is itself a governance failure mode.** Two specs, both labeled "PERIODIC_CLASS_TECH_SPEC", differing in 9 substantive amendments, both undeleted. A future contributor reading this directory has no signal which is canonical without reading both end-to-end. Archiving v1 is part of the patch-forward, not optional cleanup.

---

## §4 Verification of state claims (per `feedback_verify_agent_findings.md`)

Every "v1 already does X" or "v2 amendment Y not applied" claim in this spec must be backed by reading the actual code, not memory or implementation report.

| State claim | Source | Verification |
|---|---|---|
| Schema is 25 fields with PERIODIC trio | report §1 Phase A; v2 §3.3 | [VERIFIED — implementation report read 2026-05-08; v2 spec also confirmed via Directus query 2026-05-08 per its §3.3] |
| LD 249 has PERIODIC fields populated | report §1 Phase B; v2 §3.5 | [VERIFIED — report shows `/tmp/ld249_postpatch.json` with all 3 fields; v2 §3.5 cites Directus query 2026-05-08] |
| Audit script line 152 reads `249: "PERIODIC"` | direct file read | [VERIFIED — `weekly_preflight_audit.py` line 152, read 2026-05-08, this session] |
| Audit script line 281 reads `is_critical = days_overdue >= 7` | direct file read | [VERIFIED — line 281, read 2026-05-08, this session] |
| Audit script line 298 reads `elif days_until_review <= 7` | direct file read | [VERIFIED — line 298, read 2026-05-08, this session] |
| No `from dateutil.relativedelta import relativedelta` in imports | direct file read | [VERIFIED — file imports at lines 27-32 are stdlib only: argparse, json, os, re, sys, datetime; no dateutil; read 2026-05-08] |
| No startup schema assertion in `run_audit()` | direct file read | [VERIFIED — `run_audit()` definition begins after the audit functions; no `get_collection_fields` call before scan; read 2026-05-08] |
| No date-hygiene invariants on `last_reviewed_date` in PERIODIC branch | direct file read | [VERIFIED — PERIODIC branch lines 249-313 reads `next_review_date` only; never reads `last_reviewed_date`; read 2026-05-08] |
| LD 577 has `source_document=Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` | report §4 | [VERIFIED — report §4 explicit field listing; not directly Directus-queried this session, but report is the canonical landing record] |
| Line 152 comment contains "supersedes 2026-05-07 INTERIM EVENT_DRIVEN+120-day-backstop mapping" residue prose | direct file read | [VERIFIED — line 152, read 2026-05-08] |
| Lines 247-248 comment cites "spec §5.3 (WARN day-0 of past-due, CRITICAL after 7-day grace)" — v1's ladder | direct file read | [VERIFIED — lines 247-248, read 2026-05-08] |
| Line 295 comment says "increment next_review_date by review_cadence" — generic, not calendar-aware | direct file read | [VERIFIED — line 295, read 2026-05-08] |
| `Production/docs/.archive/` exists; `Production/docs/archive/` does not | `ls` output | [VERIFIED — bash `ls` 2026-05-08, this session; `.archive/` contains 1 prior archive file] |

This concludes the multipass verification. Every "needs change" claim below is backed by a read-from-file citation.

---

## §5 Dual-Opus Debate — PATCH-FORWARD vs. ROLL-BACK-AND-REIMPLEMENT

This is the central architectural decision of this spec. It is genuinely open. Both positions are defensible. The resolution is the doctrine that future similar incidents inherit.

### §5.1 Advocate position — PATCH-FORWARD is architecturally sound

**Argument:**

The end-state code under a disciplined patch-forward is **byte-equivalent** to the end-state code under a clean roll-back-and-re-implement-from-v2. Both end states are:

- 25-field schema on `prod_locked_decisions` with PERIODIC trio.
- LD 249 PATCHed to PERIODIC class with v2 fields populated.
- LD 577 (`PERIODIC_CLASS_ESTABLISHMENT_V1`) registered with `source_document=v2`.
- Audit script with v2 ladder (30/14/7 + OVERDUE + CRITICAL_STALE +30), calendar-aware messaging, date-hygiene invariants, startup schema assertion.
- Roadmap §1.6 reflecting v2 prose.
- v1 spec archived; v2 spec canonical.

If the four-discipline rules in §6 hold (rewrite v1 logic in-place, rewrite v1 comments, v2 spec becomes canonical, activity log honest), the resulting code reads as one coherent design.

**Cost-benefit:**

| Cost of PATCH-FORWARD | Benefit of PATCH-FORWARD |
|---|---|
| Discipline overhead: must rewrite v1 logic in-place rather than additive (§6 Hard Rules). Tempts sticky-note shortcuts. | **Zero schema churn.** The 22→25 field migration was correct in v1 and v2 alike. Re-deleting and re-adding the 3 fields creates a window where any concurrent reader hits 22-field schema and breaks. Additive schema migrations are precisely the migration class where roll-back creates more risk than rolling forward. |
| Git history shows v1 land + v2 patch as 2 commits, not 1 commit. Storytelling complexity. | **No re-PATCH on LD 249.** LD 249's `next_review_date='2026-07-18'`, `last_reviewed_date='2026-04-18'`, `review_cadence='quarterly'` are CORRECT under v2 (verified §7.2 of v2 spec: `2026-04-18 + relativedelta(months=3) = 2026-07-18`, exactly matching). Roll-back PATCHes LD 249 back to NULL then re-PATCHes it back to the same values — pure churn. |
| Activity log shows Phases A-G + Phase A2/B2/C2/D2/E2 — 12+ rows for what could be 7 rows. | **No re-creation of LD 577.** The LD already exists with the correct decision_text content (audit branch + cap-selection refactor + class definition). The only correction needed is `source_document` field PATCH from v1 to v2 — a 1-field PATCH, not a delete-and-recreate. |
| Audit-trail reader must understand "the v1 implementation ran on day-0; the v2 amendments landed on day-1." Two-step narrative. | **Lower risk to readers.** Per v2 §11.5, readers of `prod_locked_decisions` are mostly tolerant of additive schema. A roll-back of the schema would briefly show 22 fields again — `failure_mode_matrix.py` reads default fields, so it would not error, but `weekly_preflight_audit.py` ran with `fields=['review_cadence', ...]` and would 400 if those fields disappeared mid-cron. |

**Why patch-forward is end-state-equivalent (the load-bearing claim):**

The four-discipline rules force every v1 stratum to be rewritten. Specifically:
- v1's `is_critical = days_overdue >= 7` (line 281) becomes v2's 6-tier dispatch.
- v1's "WARN day-0 of past-due, CRITICAL after 7-day grace" comment (lines 247-248) becomes v2's ladder description.
- v1's "increment next_review_date by review_cadence" generic message (line 295) becomes "via dateutil.relativedelta(months=3)" specific message.
- v1's `source_document=PERIODIC_CLASS_TECH_SPEC_v1.md` on LD 577 becomes `source_document=PERIODIC_CLASS_TECH_SPEC_v2.md`.
- v1's spec doc moves to `.archive/`.

After all four disciplines apply, NO v1 code-comment text, NO v1 doctrinal phrase, NO v1 spec-doc-as-canonical reference remains in the live state. Only the git history retains the v1 stratum, and git is the audit trail — that's its job.

[CONFIDENCE: VERIFIED — every "v1 residue location" cited above is a specific line in `weekly_preflight_audit.py` read 2026-05-08, and every "v2 amendment text" is read from `PERIODIC_CLASS_TECH_SPEC_v2.md` read 2026-05-08. INFERRED — the byte-equivalent end-state claim assumes the four-discipline rules are followed; if they aren't, sticky-note architecture results. The discipline rules are the load-bearing assumption; §6 Hard Rules make them mandatory not aspirational.]

### §5.2 Counter position — ROLL-BACK-AND-REIMPLEMENT is cleaner

**Argument:**

Patch-forward is end-state-equivalent **only if the four-discipline rules are perfectly followed**. In practice, discipline drifts. A future contributor reading the audit script in 6 months sees the PERIODIC branch and asks "why is the date-hygiene invariant placed inside the branch instead of as a separate validate_periodic_row helper?" They git blame, find the v2-amendment commit, and learn the answer is "it was an in-place patch of a v1 branch that already existed; if we'd written it from scratch, we might have factored differently."

That archaeological cost is not zero. Every code reviewer for the next 12 months pays it. Multiplied by the number of times someone reads this branch, the cumulative cost may exceed the 3-hour roll-back-and-reimplement effort.

**Why roll-back is cleaner:**

- Git history shows ONE PERIODIC commit, not v1+v2. Future `git log --oneline` is shorter.
- Code-review can be done against v2 spec alone, without cross-referencing v1.
- LD 577's `source_document` is v2 from day-0 of the LD's life; no `notes` field gymnastics.
- Roadmap §1.6 LD 249 row was authored once, in v2 voice; no "this row was edited twice" cognitive load.
- The discipline rules in §6 don't have to be enforced — there's no v1 stratum to suppress.

**Why "wait" / why the human cost matters:**

Per `feedback_no_babysitting.md` and the broader "anti-slip" doctrine, governance code is read frequently and reasoned about often. Every additional cognitive layer in a hot-read path compounds. v1 → v2 patch is exactly such a layer. A clean re-implementation is a one-time 3-hour cost; a stratified codebase is a 5-minute cost paid every time someone touches the area, indefinitely.

**Risks of patch-forward that roll-back avoids:**

1. **Discipline drift.** A future PERIODIC amendment (v3) is also patched forward. The discipline rules apply again. Each patch-forward layer compounds. By v4, the strata are real.
2. **Comment drift.** Rewriting v1 comments to v2 voice is a manual discipline. A missed comment ("WARN day-0 / CRITICAL after 7-day grace" in some forgotten doc-string) silently propagates v1 doctrine.
3. **Activity-log noise.** The honest activity-log row "v1 implementation amended to v2 standards via patch-forward" is one more row. In 6 months when someone searches `prod_activity_log` for "PERIODIC", they see 7+ rows; in roll-back-and-reimplement, they'd see fewer.

**Cost-benefit:**

| Cost of ROLL-BACK | Benefit of ROLL-BACK |
|---|---|
| ~3 hours of work: revert audit script edits, DELETE 3 schema fields, PATCH LD 249 fields back to NULL, re-author and re-execute v2 phases A-G. | Clean greenfield: code reads as one coherent v2 design from day-0 of git history. |
| Schema migration churn: 22→25→22→25 within 24 hours; window of risk where readers see 22-field schema. | Audit-trail tells one story not two. |
| Re-PATCH on LD 249 with same values: pure data churn for narrative cleanliness. | LD 577 created once with correct `source_document=v2`. |
| Re-creation of LD 577: marks the v1 LD as superseded, creates a new one. Two-row LD chain instead of one. | No discipline overhead. The four-discipline rules in §6 are unnecessary because there's no v1 stratum. |

### §5.3 Resolution criteria

The debate resolves on five explicit criteria:

1. **Are the four-discipline rules sufficient to make end-state code indistinguishable from clean v2-from-scratch?** [§6 mandate question]
2. **Is the schema migration genuinely architecturally additive (no break risk) such that not-rolling-back has provably-zero cost on the schema dimension?**
3. **Is the LD 249 data already in v2-canonical form (no PATCH-revert needed)?**
4. **Is git history's storytelling value worth ~3 hours of additional work?**
5. **What precedent does this set for future Terminal-A-style incidents?** (doctrine consideration)

### §5.4 Resolution

**PATCH-FORWARD wins, conditional on the four-discipline rules being mandatory (not aspirational) per §6.**

Decision criteria applied:

**Criterion 1 (discipline sufficiency):** The four-discipline rules — rewrite v1 logic in-place, rewrite v1 comments, v2 spec becomes canonical, activity log honest — are load-bearing. If they are followed, the end-state is byte-equivalent. §6 makes them Hard Rules with explicit verification at audit checklist time. **Pass — conditionally.**

**Criterion 2 (schema additivity):** The 22→25 field migration is purely additive. Both v1 and v2 specs design the same 3 fields with identical types. No reader can distinguish a v1-landed-and-patched schema from a v2-landed-fresh schema. Roll-back's 22→25→22→25 churn is a brief window of provable risk that adds nothing to end-state quality. **Pass — patch-forward is provably equal-or-better on the schema axis.**

**Criterion 3 (LD 249 data already correct):** The values `quarterly`, `2026-07-18`, `2026-04-18` are CORRECT under both v1 and v2 (per v2 §7.2: `2026-04-18 + relativedelta(months=3) = 2026-07-18` matches). No PATCH-revert needed. **Pass.**

**Criterion 4 (git history value):** Git history shows the chronology either way. Whether it shows "v1 commit + v2 amendment commit" or "v2 commit alone", a future contributor has the same archaeological tools. The "two commits" narrative is a one-time cognitive cost — a future contributor reads the v2 commit and sees its message says "applies v2 spec amendments to v1-as-built code per PATCH_FORWARD_PERIODIC_TECH_SPEC". That's not arcane archaeology; it's straightforward commit-message reading. **Pass — git's storytelling burden is minor.**

**Criterion 5 (precedent for future incidents):** This is the most subtle criterion. The doctrine this spec sets for future Terminal-A-style incidents is:

> "When an unauthorized pre-execution lands in prod and a higher-quality spec emerges after the fact, the default response is **disciplined patch-forward**, not roll-back-and-reimplement. The four-discipline rules ensure end-state cleanliness. Roll-back is reserved for cases where (a) the schema migration is non-additive, OR (b) the data values are wrong under the new spec, OR (c) the discipline rules cannot be applied (e.g., the v1 stratum is too entangled with non-architectural code to factor cleanly)."

This doctrine is sound because it scales: it doesn't require a 3-hour penalty for every incident; it does require the four-discipline rules be followed every time. It also implicitly disincentivizes Terminal-A-style executions: you can't unauthorized-execute and expect "clean re-implementation" to bail you out; you also have to sit through the patch-forward discipline.

**Pass — patch-forward sets a sustainable precedent.**

**5/5 criteria pass.** **PATCH-FORWARD is the correct choice.**

[CONFIDENCE: INFERRED — the resolution rests on the load-bearing assumption that §6 Hard Rules will actually be followed by the implementation session. If they aren't, we get sticky-note architecture, the Counter wins retroactively, and roll-back would have been correct. Mitigation: §6 Hard Rules include explicit verification at §10 audit checklist time. VERIFIED — the schema-additivity and LD-249-correctness sub-claims (criteria 2-3) are directly cited from `weekly_preflight_audit.py` reads + v2 §7.2 calendar arithmetic.]

---

## §6 Four-Discipline Hard Rules (must hold throughout patch-forward implementation)

These are **mandatory**. The implementation session MUST verify each rule held at audit-checklist time. Failure on any rule means the patch-forward did not produce v2-equivalent end-state and the discipline broke down.

### §6.1 Rule 1 — Rewrite v1 logic IN-PLACE

**Mandate:** Do not add v2 logic next to v1 logic with a flag picking between them. REPLACE v1 with v2. Same function, new body. Same `if classification == "PERIODIC":` branch, new internal dispatch. End-state code reads as one coherent design, not strata.

**What this means in practice for `weekly_preflight_audit.py`:**

| Location | v1-as-built (REPLACE) | v2 target (REWRITE) |
|---|---|---|
| Line 281 `is_critical = days_overdue >= 7` | DELETE this line entirely | REPLACE with v2's 6-tier dispatch (WARN_30 / ELEVATED / CRITICAL_APPROACHING / OVERDUE / CRITICAL_STALE) |
| Line 282 `tier = "CRITICAL" if is_critical else "WARN"` | DELETE | REPLACE with explicit tier per branch |
| Lines 279-297 (the past-due if branch with `days_until_review <= 0`) | DELETE the entire if branch body | REPLACE with v2 §4.2 pseudocode lines 253-282 (OVERDUE warning + CRITICAL_STALE blocker tiers) |
| Lines 298-311 (the approaching elif with `<= 7`) | DELETE the entire elif branch | REPLACE with v2 §4.2 pseudocode lines 214-252 (WARN_30 + ELEVATED + CRITICAL_APPROACHING tiers) |
| Audit's `fields=` list (lines 207-211) | KEEP — already correct | NO CHANGE |
| Cap-selection refactor (lines 341-360) | KEEP — already correct | NO CHANGE |

**Anti-pattern (sticky-note architecture):**
```python
# DO NOT DO THIS:
if FEATURE_FLAG_V2_LADDER:
    # v2 ladder
    if days_until_review > 30:
        ...
else:
    # v1 ladder
    is_critical = days_overdue >= 7
    ...
```

**Correct pattern (in-place rewrite):**
```python
# DO THIS:
# v1's days_overdue >= 7 binary tiering and 7-day prewarn replaced with
# v2's 30/14/7 + OVERDUE + CRITICAL_STALE +30 ladder. See PERIODIC_CLASS_TECH_SPEC_v2.md §4.2.
if days_until_review >= 30:
    continue
elif days_until_review > 14:
    findings.append({...WARN_30...})
elif days_until_review > 7:
    findings.append({...ELEVATED...})
# ... etc.
```

**Verification (at §10 audit checklist):** `grep -n "is_critical = days_overdue" Production/scripts/weekly_preflight_audit.py` should return ZERO matches. `grep -n "WARN_30\|ELEVATED\|CRITICAL_APPROACHING\|CRITICAL_STALE" Production/scripts/weekly_preflight_audit.py` should return at least 4 matches.

### §6.2 Rule 2 — Rewrite v1 comments

**Mandate:** Any comment referencing v1's day-deltas, 7-day prewarn, "INTERIM mapping", or other obsolete reasoning must be UPDATED to reflect v2. No "// v1 said X but we use Y" sticky-note comments. The end-state code's comments speak v2's voice.

**Specific locations to rewrite:**

| File | Line | Current (v1-residue) | Rewrite to (v2-voice) |
|---|---|---|---|
| `weekly_preflight_audit.py` | 152 | `249: "PERIODIC", # ... supersedes 2026-05-07 INTERIM EVENT_DRIVEN+120-day-backstop mapping.` | `249: "PERIODIC", # SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418 — quarterly review cadence (review_cadence/next_review_date/last_reviewed_date populated). Audit fires WARN_30/ELEVATED/CRITICAL_APPROACHING ladder approaching review; OVERDUE on day-0; CRITICAL_STALE +30 days. Class authority: LD PERIODIC_CLASS_ESTABLISHMENT_V1.` |
| `weekly_preflight_audit.py` | 242-248 | `# PERIODIC class branch (LD PERIODIC_CLASS_ESTABLISHMENT_V1, 2026-05-08). ... # Two-tier surfacing per spec §5.3 (WARN day-0 of past-due, # CRITICAL after 7-day grace).` | `# PERIODIC class branch. PERIODIC LDs have a recurring scheduled review (cadence in review_cadence; next fire date in next_review_date). Six-tier surfacing keyed on next_review_date — NOT date_locked + cap_days: 30-day approach window (WARN_30), 14-day (ELEVATED), 7-day (CRITICAL_APPROACHING), day-0 OVERDUE (warning), +30 days CRITICAL_STALE (writes prod_blocker). Calendar-aware cadence increments via dateutil.relativedelta. See PERIODIC_CLASS_TECH_SPEC_v2.md §4.2.` |
| `weekly_preflight_audit.py` | 295 | `# ... increment next_review_date by review_cadence.` | `# ... PATCH last_reviewed_date and increment next_review_date by review_cadence using calendar-aware arithmetic, e.g. relativedelta(months=3) for quarterly.` |
| `weekly_preflight_audit.py` | 247 (CRITICAL after 7-day grace prose in OVERDUE message) | "OVERDUE by {days_overdue} days [{tier}]" — implicit tier=CRITICAL when >=7 | Six explicit tier labels in messages per v2 §4.2. |
| `weekly_preflight_audit.py` | 400-401 | `# Title # prefix differentiates classification per spec §5.5: PERIODIC review-overdue` | "spec §5.5" → "spec v2 §5.5" or just remove the version reference; the section identity holds across v1/v2. |

**Anti-pattern:** "// v1 used 7-day grace; v2 uses 30-day. We picked v2."
**Correct pattern:** "// 30-day stale tier per PERIODIC_CLASS_TECH_SPEC_v2.md §5.3."

**Verification:** `grep -n "INTERIM\|7-day grace\|day-0 of past-due, CRITICAL after" Production/scripts/weekly_preflight_audit.py` should return ZERO matches in PERIODIC-related lines.

### §6.3 Rule 3 — v2 spec doc becomes canonical

**Mandate:**
1. **Move** `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` to `Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md`. Use `git mv` for git history continuity. Do NOT rename in place (no `_DEPRECATED` suffix); use the existing `.archive/` directory convention. [VERIFIED — `.archive/` exists, contains 1 prior archive file, 2026-05-08]
2. **PATCH** LD 577's `source_document` field from `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` to `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` via Directus.
3. **PATCH** LD 577's `notes` field to append a paragraph: "Canonical spec moved from v1 to v2 on YYYY-MM-DD per PATCH-FORWARD doctrine; v1 archived to `Production/docs/.archive/`; v2's 9 Cursor-derived amendments fully landed in `weekly_preflight_audit.py` per `PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` execution. v2 §11.5 reader inventory transcribed below for record." Followed by the v2 §11.5 reader inventory table verbatim (or by reference: "see PERIODIC_CLASS_TECH_SPEC_v2.md §11.5").
4. **Verify** Roadmap §1.6 paragraph and LD 249 row prose speak v2's voice: 30/14/7 ladder, calendar-aware cadence chain, CRITICAL_STALE +30, no "WARN day-0 of past-due, CRITICAL after 7-day grace" v1 phrasing.

**Verification:** `ls Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` should fail (file not found). `ls Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md` should succeed. Directus query on LD 577 `source_document` field should return `...v2.md`.

### §6.4 Rule 4 — Update activity log honestly

**Mandate:** Append a single new `prod_activity_log` row documenting the patch-forward amendment, with explicit prose: "v1 implementation amended to v2 standards via patch-forward; no roll-back or re-implementation."

**Specific row content:**
- `action`: `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE`
- `details`: A JSON object with: `{spec_authority: "PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md", v2_amendments_landed: [1,2,3,4,5,6,7,8,9], audit_script_diff_summary: "<+lines/-lines from this session's commit>", v1_archived_to: ".archive/", source_document_patch: "LD 577 v1->v2", four_discipline_rules_verified: true}`
- `task_id`: a fresh UUID (not the v1 implementation's `periodic-class-impl-20260508-fb5fe9f8`)
- Timestamp: implementation session date

**Anti-pattern:** Silent edits (no activity log row); or a misleading row that pretends v2 was always canonical (e.g., "PERIODIC_CLASS_V2_INITIAL_LANDING").
**Correct pattern:** A row that names the patch-forward explicitly. The audit trail tells the truth.

**Verification:** `prod_activity_log` query for `action LIKE 'PERIODIC_CLASS_PATCH_FORWARD%'` returns exactly 1 row. The row's `details` mentions all 9 v2 amendments by number.

### §6.5 Discipline checkpoint at §10 audit

The §10 testing plan / audit checklist EXPLICITLY verifies all four rules held. If any rule fails verification, the patch-forward is incomplete and must be re-attempted (or the implementation session escalates to Kim with the discipline-break documented).

---

## §7 Per-Amendment Plan

Each of v2's 9 amendments mapped to: already-done / replace / add / archive. Plus per-amendment specific code/doc location.

| # | Amendment | Status in v1-as-built | Patch-forward action | Specific location | Discipline Rule(s) |
|---|---|---|---|---|---|
| 1 | Closed enum (no `other`) | ALREADY-DONE [VERIFIED — implementation report §1 Phase A] | NO action; verify-and-document. | Directus interface configuration on `review_cadence` field. | n/a (no residue) |
| 2 | Calendar-aware cadence arithmetic via `relativedelta` | NEEDED — line 295 generic; no `relativedelta` import | (a) ADD `from dateutil.relativedelta import relativedelta` to imports (line 32). (b) REPLACE line 295 message text to mention `relativedelta`. (c) Verify `python-dateutil` in environment. | `weekly_preflight_audit.py` lines 27-32, 295. | Rule 1 (in-place), Rule 2 (comment) |
| 3 | 30/14/7 prewarn ladder + CRITICAL_STALE +30 | NEEDED — lines 279-311 are v1 ladder (binary past-due, single 7-day approach) | REPLACE the entire PERIODIC branch body (lines 249-313) with v2 §4.2 pseudocode (6-tier dispatch). Replace comment block lines 242-248 with v2-voice prose. | `weekly_preflight_audit.py` lines 242-313. | Rule 1 (in-place), Rule 2 (comment) |
| 4 | Reader inventory + smoke procedure | NEEDED — no inventory in code or docs | ADD inventory as content in LD 577 `notes` field (per Rule 3). Optionally add `Production/_snapshots/` baseline output capture step in §8 implementation phases. | LD 577 notes; v2 §11.5 reference. | Rule 3 (canonical spec) |
| 5 | `prod_activity_log` canonical | ALREADY-DONE [VERIFIED — implementation report §10 lists rows 1763-1768 in `prod_activity_log`] | NO action; verify-and-document. | Documentation only. | n/a |
| 6 | Fingerprint-checked PATCH | NEEDED for FUTURE PATCHes; not retroactive | ADD doctrine to LD 577 notes + `Production/lib/directus.py` helper if not present. Phase B's LD 249 PATCH already happened cleanly per /tmp/ld249_prepatch.json snapshot. | LD 577 notes; potentially `Production/lib/directus.py`. | Rule 3 (canonical spec content) |
| 7 | CRITICAL_STALE +30 tier | NEEDED — folded into amendment #3 | (folded with #3 — single in-place rewrite of PERIODIC branch covers both #3 and #7) | (same as #3) | (same as #3) |
| 8 | Date-hygiene invariants | NEEDED — not present in PERIODIC branch | ADD ~15 lines of invariant checks per v2 §5.4 INSIDE the PERIODIC branch (after `next_review_date` parse, before tier dispatch). | `weekly_preflight_audit.py` PERIODIC branch (between current line 277 and current line 279). | Rule 1 (in-place — invariants live in the PERIODIC branch, not as a separate function) |
| 9 | Schema startup assertion | NEEDED — `run_audit()` does not GET `/fields/prod_locked_decisions` | ADD ~12 lines at the top of `run_audit()` (look for the function definition; insertion point is after `client = DirectusClient(...).authenticate()` and before any `prod_locked_decisions` read). | `weekly_preflight_audit.py` `run_audit()` definition. Verify line range during implementation. | Rule 1 (in-place), Rule 2 (comment) |

**Aggregate: 6 code edits + 1 doc archive + 1 LD field PATCH + 1 LD notes PATCH + 1 activity-log row + 1 Roadmap §1.6 prose update.**

Estimated diff size: ~80 net lines on `weekly_preflight_audit.py` (delete v1 ladder ~30 lines, add v2 ladder + invariants + startup assertion ~110 lines, comment rewrites cancel out). Estimated 6-8 phases of work; conservative session budget.

---

## §8 Sequence — Patch-Forward Phases

In order:

### Phase A2 — Audit code in-place rewrite (Rules 1 + 2)

1. Read `PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` (this doc) end-to-end.
2. Read `PERIODIC_CLASS_TECH_SPEC_v2.md` end-to-end.
3. Read `weekly_preflight_audit.py` lines 130-411 (current PERIODIC-area state).
4. Run §16 preflight gate from v2 (freeze, snapshot, reader-smoke).
5. Verify `python-dateutil` is installed (`pip show python-dateutil` or equivalent).
6. **Edit `weekly_preflight_audit.py` (single PR-sized commit):**
   - Add `from dateutil.relativedelta import relativedelta` import (Rule 1 — in-place at imports block).
   - REPLACE PERIODIC branch lines 242-313 with v2 §4.2 6-tier dispatch + date-hygiene invariants (Rule 1 — in-place; delete v1 ladder, write v2 ladder).
   - REPLACE PERIODIC-related comments per Rule 2 §6.2 table.
   - REPLACE line 152 dict comment per Rule 2 §6.2 table.
   - ADD startup schema assertion at top of `run_audit()` per amendment #9.
7. Run `python3 weekly_preflight_audit.py --dry-run` — verify exit code 0.
8. Verify the §10 audit-checklist post-Phase-A2 items.
9. Commit + push (single commit per amendment chunk acceptable; no force-push).

### Phase B2 — Roadmap §1.6 update (Rule 2 + Rule 3)

1. Re-Read Roadmap §1.6 lines 83-141 to capture current (v1-voice) prose.
2. Edit §1.6 cap-policy paragraph: replace v1 prose ("WARN day-0 of past-due, CRITICAL after 7-day grace") with v2 ladder prose (30/14/7 approach + day-0 OVERDUE + +30 CRITICAL_STALE; calendar-aware cadence chain).
3. Edit LD 249 row's `Cap` column: replace generic "next review 2026-07-18 (then 2026-10-18, 2027-01-18)" with explicit `relativedelta(months=3)` annotation if useful for future readers ("next review 2026-07-18, then +relativedelta(months=3) → 2026-10-18 → 2027-01-18 ...").
4. Edit Status footer if needed: arithmetic stays `15 EVENT_DRIVEN + 1 PERIODIC + 6 RARE_NEVER = 22`.
5. Commit + push.

### Phase C2 — LD 577 amendment via fingerprint-checked PATCH (Rule 3 + Rule 4 doctrine)

1. Apply v2 §16.2 fingerprint discipline: GET LD 577, hash, plan PATCH, re-GET, compare, write or fail-closed.
2. PATCH `source_document` from `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` → `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md`.
3. PATCH `notes` to APPEND (never overwrite per Rule 35) the patch-forward-completion paragraph + v2 §11.5 reader inventory transcription (or by reference).
4. Read-back to verify both fields landed.
5. (No commit — this is a Directus row PATCH, no file changes.)

### Phase D2 — Archive v1 spec (Rule 3)

1. Verify `Production/docs/.archive/` directory exists [VERIFIED 2026-05-08].
2. `git mv "Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md" "Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md"`.
3. Verify `ls Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` fails AND `ls Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md` succeeds.
4. (Optional) Update any other docs that reference v1 path: grep for `PERIODIC_CLASS_TECH_SPEC_v1.md` across `Production/docs/`. Edit references to point to v2 (or to .archive/v1 if specifically discussing the historical record).
5. Commit + push.

### Phase E2 — Honest activity log row (Rule 4)

1. Compose the `prod_activity_log` row content per §6.4.
2. POST to Directus.
3. Read-back to verify row landed with all expected fields.

### Phase F2 — Verification dry-run + four-discipline audit

1. Run `python3 weekly_preflight_audit.py --dry-run` end-to-end. Verify:
   - Startup schema assertion passes (3 PERIODIC fields confirmed).
   - LD 249 produces NO finding (next_review 2026-07-18 is >30 days from today; ladder is silent).
   - No regressions on the other 21 SHORTCUT LDs.
2. Run §6.5 discipline checkpoint:
   - **Rule 1 verification:** `grep -n "is_critical = days_overdue" Production/scripts/weekly_preflight_audit.py` returns 0 matches.
   - **Rule 1 verification:** `grep -n "WARN_30\|ELEVATED\|CRITICAL_APPROACHING\|CRITICAL_STALE" Production/scripts/weekly_preflight_audit.py` returns ≥4 matches.
   - **Rule 2 verification:** `grep -n "INTERIM\|7-day grace\|day-0 of past-due, CRITICAL after" Production/scripts/weekly_preflight_audit.py` returns 0 matches in PERIODIC area.
   - **Rule 3 verification:** `ls Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` fails. `ls Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md` succeeds. Directus LD 577 `source_document` returns v2 path.
   - **Rule 4 verification:** Directus query `prod_activity_log?filter[action][_starts_with]=PERIODIC_CLASS_PATCH_FORWARD` returns exactly 1 row.
3. If any verification fails, escalate to Kim with explicit discipline-break documented; do NOT silently re-attempt.

**Sequencing notes:**
- Phase A2 must complete before Phase F2's verification step 1 can pass (audit script needs the fix).
- Phase B2 (roadmap) and Phase D2 (archive v1) are PARALLELIZABLE after Phase A2 dry-run passes.
- Phase C2 (LD 577 PATCH) and Phase E2 (activity log row) are PARALLELIZABLE with B2/D2 (different Directus rows / different files).
- Phase F2 is the closeout.

---

## §9 Open Decisions

These are decisions Kim must explicitly make (or default per spec recommendation). Each is recorded so the implementation session inherits clarity, not ambiguity.

### §9.1 [DECISION-1] Where does the reader inventory (v2 §11.5) live?

**Options:**
- (A) Transcribed verbatim into LD 577 notes (ensures persistence in Directus; low discoverability outside Directus query).
- (B) Sidecar doc at `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v2.md` (high discoverability; another doc to maintain).
- (C) Reference only ("see v2 §11.5"); v2 spec at `.archive/`-or-canonical determines reachability.

**Spec recommendation:** **Option A** (LD 577 notes). Reader inventory is a one-time landed artifact; LD 577 is the canonical record for the class; placing the inventory there ensures any future PERIODIC-related query reaches it. Option B adds doc-maintenance overhead. Option C silently degrades when v2 is moved.

### §9.2 [DECISION-2] Should we move v2 to canonical filename `PERIODIC_CLASS_TECH_SPEC.md` (no version suffix) or keep as `_v2.md`?

**Options:**
- (A) Rename `_v2.md` → `PERIODIC_CLASS_TECH_SPEC.md` (no version). Future v3 would be `_v3.md` until that becomes canonical.
- (B) Keep `_v2.md` filename. v3 if it emerges would be `_v3.md`.

**Spec recommendation:** **Option B** (keep `_v2.md`). Version-suffixed filenames are the project's convention (per existing `STORYBOARD_V59_*_SPEC_v1.md`, `STORYBOARD_V59_*_SPEC_v2.md` precedent in `Production/docs/`). Renaming creates downstream link-rot. The "v2 is canonical" claim is enforced by archiving v1, not by file-naming.

### §9.3 [DECISION-3] Should LD 577 be marked superseded and a new LD created, or should LD 577 be amended in place?

**Options:**
- (A) Amend LD 577 in place (PATCH `source_document` + notes append). Single LD chain.
- (B) Mark LD 577 superseded; create new LD `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS` citing v2 spec.

**Spec recommendation:** **Option A** (amend in place). LD 577's `decision_text` (the class definition: cadence enum, structured fields, audit semantics, blocker prefix) is correct under v2 — it was already written from a forward-looking perspective. Only `source_document` needs PATCHing to point at v2. Creating a superseded chain for a `source_document` field PATCH is over-engineering. (LD 577 is `supersedable: true` per the implementation report §4 — the option is available if Kim prefers cleaner LD chains, but spec recommends amend-in-place.)

### §9.4 [DECISION-4] Should we add the v2 §16.2 fingerprint-checked PATCH discipline as a `Production/lib/directus.py` helper, or only as documentation in LD 577?

**Options:**
- (A) Documentation-only in LD 577 + v2 spec. Future LD PATCHes manually follow the discipline.
- (B) Add `post_item_with_fingerprint_check()` helper to `Production/lib/directus.py` (or similar). Future PATCHes use the helper.

**Spec recommendation:** **Option A** in this patch-forward; **Option B** as a future enhancement (separate ticket). Adding a library helper is a code change orthogonal to the PERIODIC class itself. It's a good idea but it's not part of the PERIODIC patch-forward; out-of-scope per §2.2.

### §9.5 [DECISION-5] What today's date should the implementation session use for the new `prod_activity_log` row's timestamp and LD 577 notes amendment?

**Options:**
- (A) Use the session execution date (likely 2026-05-08 if executed soon, or whatever date the actual session runs).
- (B) Backdate to 2026-05-08 to match the v1 implementation.

**Spec recommendation:** **Option A** (session execution date). The activity log tells the truth about when the patch-forward happened. Backdating obscures the chronology and creates a false single-event narrative.

---

## §10 Pre-Implementation Gates (must hold before Kim authorizes execution)

1. **Kim reads §5 dual-Opus debate and resolution; approves PATCH-FORWARD doctrine OR overrides to ROLL-BACK.**
2. **Kim approves §6 four-discipline rules as Hard Rules (not aspirational).**
3. **Kim approves §7 per-amendment table (which is already-done, which needs replace, which needs add).**
4. **Kim approves §8 sequence (Phase A2 → B2 → C2 → D2 → E2 → F2; B2/C2/D2/E2 parallelizable after A2 dry-run passes).**
5. **Kim resolves §9 open decisions (or accepts spec recommendations as defaults).**
6. **Kim confirms `python-dateutil` is acceptable as a new dependency in the audit script's environment.**
7. **Kim confirms LD 577 `source_document` PATCH is acceptable (vs. amend-in-place vs. supersede chain).**
8. **Kim authorizes file move: `git mv Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md Production/docs/.archive/`.**
9. **Kim confirms the implementation session may write directly to prod Directus (no staging fork).**
10. **Kim confirms the spec is reviewable as written OR requests Cursor cross-review (mirroring v1→v2 process).**
11. **Kim confirms the implementation session must HALT if any §6 discipline rule fails verification at §10 audit checklist time.**
12. **Kim acknowledges this spec sets a precedent doctrine for future Terminal-A-style incidents (PATCH-FORWARD as default).**

---

## §11 Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Discipline drift — Rule 1 (in-place) silently violated by additive edit | HIGH | Rule 1 verification at §8 Phase F2 (`grep` for v1 residue patterns must return 0 matches); HALT and re-attempt if violated. |
| Discipline drift — Rule 2 (comment rewrite) silently violated by missed comment | MEDIUM | Rule 2 verification by `grep` for v1-voice phrases; HALT if found. |
| `python-dateutil` not in environment; audit fails on import | LOW | Phase A2 step 5 verifies presence before any code edit. Vendor `relativedelta` logic if missing (clamp to last-valid-day-of-month manual implementation, ~10 lines). |
| Concurrent reader hits 25-field schema mid-PATCH on LD 577 | LOW | Schema is unchanged in patch-forward; only LD 577 row is PATCHed. Fingerprint discipline (v2 §16.2) catches concurrent edits. |
| Concurrent edit on `weekly_preflight_audit.py` mid-Phase-A2 | LOW | Pre-execution gate §10 step #11 implies Kim coordinates other terminals. |
| `git mv` fails due to working-tree dirt | LOW | Phase D2 step 2 includes pre-`git mv` `git status` check; clean-tree gate. |
| Roadmap §1.6 edit inadvertently breaks markdown table alignment | LOW | Phase B2 step 5 includes pre-commit re-render check (Markdown viewer or `cat`). |
| LD 577 `source_document` PATCH hits Directus race / 409 | LOW | Fingerprint discipline (v2 §16.2) handles. |
| Honest activity log row has wrong action key (clashes with future search) | LOW | Use the explicit `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE` key recommended in §6.4. |
| Future v3 amendment also patch-forwards; strata compound | MEDIUM | Doctrine in §5.4 + §6 makes the four-discipline rules mandatory each time; if a v3 implementation cannot apply them cleanly, ROLL-BACK becomes the correct choice. The doctrine self-corrects. |
| Sticky-note architecture emerges despite rules (e.g., feature flag added) | HIGH | §6 Rule 1 anti-pattern explicitly forbids feature flags; §10 gate #11 mandates HALT on discipline-break. |
| Cursor cross-review surfaces a 10th issue not in v2 | MEDIUM | This spec's Cursor handoff (§14) explicitly invites that question. If Cursor finds a v3-class issue, defer it (per §2.2 out-of-scope). If Cursor finds a v2-class issue (a v2 amendment that v2 itself missed), pause and amend v2 first. |
| Implementation session does NOT halt at §10 audit checklist failure | HIGH | §10 gate #11 + §6.5 discipline checkpoint mandate HALT. Inherits from the same Terminal A failure mode as v1 → mitigation is gate-discipline, not technical. |

---

## §12 Rollback Procedure (per phase, LIFO)

### Rollback Phase F2 (verification)
- Re-running verification is idempotent; no rollback needed.

### Rollback Phase E2 (honest activity log row)
- Mark the inserted `prod_activity_log` row as deleted (or PATCH `details.rolled_back=true`). Do NOT physically delete the row (audit-trail invariant).

### Rollback Phase D2 (archive v1)
- `git mv Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md`. Reverts Phase D2.

### Rollback Phase C2 (LD 577 amendment)
- PATCH LD 577 `source_document` back to `...v1.md`. PATCH `notes` to remove the patch-forward paragraph (preserving original notes).
- Fingerprint check applies: read current state, plan revert, re-read, compare, write.

### Rollback Phase B2 (roadmap)
- `git revert` the Phase B2 commit. §1.6 reverts to v1 voice.

### Rollback Phase A2 (audit code rewrite)
- `git revert` the Phase A2 commit. Audit script reverts to v1 ladder + v1 comments.
- Re-run `--dry-run` to verify v1 behavior restored.

### Rollback decision criteria
Trigger rollback if:
- Phase A2 introduces uncaught exceptions on production Directus data.
- Phase A2 produces unexpected findings on existing 21 non-PERIODIC SHORTCUT LDs.
- Discipline checkpoint (§6.5) fails on any rule and re-attempt does not cleanly close the gap.
- Kim withdraws authorization mid-implementation.

---

## §13 Testing Plan

### §13.1 Phase A2 verification

- [VERIFICATION 1] `python3 weekly_preflight_audit.py --dry-run` exit code 0.
- [VERIFICATION 2] Startup schema assertion passes (3 PERIODIC fields confirmed via `/fields/prod_locked_decisions` GET).
- [VERIFICATION 3] LD 249 produces NO finding today (next_review 2026-07-18 is >30 days out from session date).
- [VERIFICATION 4] Manually inject 6 fabricated PERIODIC LD rows (in-memory FakeClient or sandbox row) covering all 6 ladder tiers:
  - `next_review_date = today + 35 days` → silent
  - `next_review_date = today + 20 days` → WARN_30
  - `next_review_date = today + 10 days` → ELEVATED
  - `next_review_date = today + 5 days` → CRITICAL_APPROACHING
  - `next_review_date = today + 0 days` → OVERDUE (warning, no blocker)
  - `next_review_date = today - 35 days` → CRITICAL_STALE (writes prod_blocker)
- [VERIFICATION 5] Date-hygiene invariants fire correctly on synthetic bad data:
  - `last_reviewed_date='2099-01-01'` (future) → invariant fires.
  - `last_reviewed_date='garbage'` → invariant fires.
  - `last_reviewed_date='2027-01-01'` and `next_review_date='2026-07-18'` (last > next) → invariant fires.
- [VERIFICATION 6] Calendar-aware arithmetic produces correct results:
  - `relativedelta(months=3)` applied to `2026-04-18` → `2026-07-18` (matches LD 249's actual next_review_date).
  - `relativedelta(months=1)` applied to `2026-01-31` → `2026-02-28` (clamp).

### §13.2 Phase B2 verification

- [VERIFICATION 1] §1.6 table renders correctly (no broken pipes; confirm with Markdown viewer or `cat` + visual scan).
- [VERIFICATION 2] §1.6 cap-policy paragraph mentions all 3 classes AND v2 ladder (30/14/7, OVERDUE, CRITICAL_STALE).
- [VERIFICATION 3] LD 249 row's `Cap` column mentions `relativedelta` or calendar-aware arithmetic.

### §13.3 Phase C2 verification

- [VERIFICATION 1] LD 577 `source_document` field is `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md`.
- [VERIFICATION 2] LD 577 `notes` includes the patch-forward-completion paragraph and reader inventory (transcription or by-reference).

### §13.4 Phase D2 verification

- [VERIFICATION 1] `ls Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` fails (file moved).
- [VERIFICATION 2] `ls Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md` succeeds.
- [VERIFICATION 3] Git history preserved: `git log Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md` shows the original 2026-05-07 author commit.

### §13.5 Phase E2 verification

- [VERIFICATION 1] `prod_activity_log` query for `action LIKE 'PERIODIC_CLASS_PATCH_FORWARD%'` returns exactly 1 row.
- [VERIFICATION 2] The row's `details` field mentions all 9 v2 amendments.

### §13.6 §6 four-discipline rule audit

(Per §8 Phase F2 step 2 — repeated here as the canonical discipline checkpoint.)

- **Rule 1 verification:** `grep -n "is_critical = days_overdue" Production/scripts/weekly_preflight_audit.py` returns 0 matches.
- **Rule 1 verification:** `grep -n "WARN_30\|ELEVATED\|CRITICAL_APPROACHING\|CRITICAL_STALE" Production/scripts/weekly_preflight_audit.py` returns at least 4 matches.
- **Rule 2 verification:** `grep -n "INTERIM\|7-day grace\|day-0 of past-due, CRITICAL after" Production/scripts/weekly_preflight_audit.py` in the PERIODIC-related lines returns 0 matches.
- **Rule 3 verification:** v1 spec is at `.archive/`; LD 577 `source_document` is v2.
- **Rule 4 verification:** `prod_activity_log` honest row exists.

### §13.7 End-to-end

- [VERIFICATION 1] After all phases, Kim runs `python3 weekly_preflight_audit.py --dry-run`. LD 249 sits silently. No spurious findings on the 21 other SHORTCUT LDs.
- [VERIFICATION 2] First real PERIODIC review at 2026-07-18 fires CRITICAL_APPROACHING at 2026-07-11, ELEVATED at 2026-07-04, WARN_30 at 2026-06-18 (per v2 ladder).

---

## §14 Reference Index (per zero-error-qa §16)

### Source documents read this session

| Document | Purpose | Lines/Range | Verification timestamp |
|---|---|---|---|
| `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` | Original spec; understand v1 doctrine | 600 lines (full read in chunks 1-600 + 600-867) | 2026-05-08 |
| `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` | v2 amended spec; understand 9 amendments + Cursor verdict | full read (chunks 1-450 + 450-902) | 2026-05-08 |
| `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` | Terminal A's narrative; verify what landed | full read (336 lines) | 2026-05-08 |
| `Production/scripts/weekly_preflight_audit.py` | As-built audit code; verify v1 residue locations | targeted reads (lines 1-100, 130-220, 220-411) | 2026-05-08 |
| `Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md` | v2 Cursor handoff; mirror its structure | full read (143 lines) | 2026-05-08 |
| Bash `ls Production/docs/.archive/` | Verify archive directory exists | 1 prior file present | 2026-05-08 |
| Bash `grep -n "INTERIM..." weekly_preflight_audit.py` | Verify v1 residue line numbers | grep output captured | 2026-05-08 |

### Constants and identifiers

- v1 spec sha (TBD by implementation session preflight)
- v2 spec sha (TBD by implementation session preflight)
- LD 577 id (Directus): `577`
- LD 249 id (Directus): `249`
- Activity log rows from v1 implementation: `1763, 1764, 1765, 1766, 1767, 1768`
- Preflight review row id from v1 implementation: `208` (task_id `periodic-class-impl-20260508-fb5fe9f8`)
- Audit script v1-residue lines: `152, 247-248, 281, 282, 295, 298`
- Audit script PERIODIC branch range: `lines 242-313`

### LDs cited

- 249 — `SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418` — sole migration cohort; live PERIODIC.
- 577 — `PERIODIC_CLASS_ESTABLISHMENT_V1` — class authority LD; landed by Terminal A; needs source_document PATCH.
- 200, 263, 566, 568 — non-migrating PERIODIC-shaped patterns (for context).
- 561 — `MASTER_ROADMAP_LIVING_DOC_V1` — surfaces §1.6 closure.

### Specs cited

- `PERIODIC_CLASS_TECH_SPEC_v1.md` — historical baseline; to be archived.
- `PERIODIC_CLASS_TECH_SPEC_v2.md` — canonical spec; load-bearing for amendments #1-9.
- `STORYBOARD_V59_*_SPEC_v1/v2.md` — version-suffixed-filename precedent.
- `feedback_tech_spec_for_wrong_architecture.md` — memory; this spec invokes per the trigger.
- `feedback_verify_agent_findings.md` — memory; this spec applies via §4 verification.

### To-be-created references

- `prod_activity_log` row `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE` (Phase E2 artifact).

### Cursor cross-review handoff

- `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md` (this session authors per Phase 3 of mission).

---

## §15 Confidence Annotations Sweep (per Rule 24)

| Section | Predominant tag | Notes |
|---|---|---|
| §0 (operating mode) | n/a | declarative |
| §1 (goal) | n/a | declarative |
| §2 (scope) | n/a | declarative |
| §3 (background) | [VERIFIED] | every claim cites file Read line numbers, implementation report sections, or v2 spec sections |
| §4 (verification of state claims) | [VERIFIED] | every row directly cites a file or tool output |
| §5 (dual-Opus debate) | [INFERRED] for resolution; [VERIFIED] for evidence | Advocate / Counter positions are reasoned; resolution criteria pass on cited evidence |
| §6 (four-discipline rules) | [INFERRED] for design choice; rule definitions are declarative | discipline rules ARE the spec output |
| §7 (per-amendment plan) | [VERIFIED] for already-done / needed status; [INFERRED] for prescribed actions | every status cites a tool output |
| §8 (sequence) | [INFERRED] | proposal |
| §9 (open decisions) | [INFERRED] | proposal |
| §10 (pre-impl gates) | [INFERRED] | proposal |
| §11 (risks) | [INFERRED] | forecasting |
| §12 (rollback) | [INFERRED] | proposal |
| §13 (testing) | [INFERRED] | proposal |
| §14 (reference index) | [VERIFIED] | every entry corresponds to a tool call this session |

**No [ASSUMED] tags.** Every assertion is either directly cited or labeled as a design proposal.

---

## §16 TL;DR Table

| Question | Answer |
|---|---|
| What is the patch-forward path? | Apply v2's 9 amendments to v1-as-built code via in-place rewrites (NOT additive sticky-note patches). End-state code is byte-equivalent to clean v2-from-scratch. |
| Why patch-forward (not roll-back)? | (1) Schema migration is purely additive — no architectural difference in end-state. (2) LD 249 data is already correct under v2 (`+ relativedelta(months=3)` matches actual `2026-07-18`). (3) Roll-back creates schema-churn risk window for zero architectural gain. (4) §6 four-discipline rules ensure end-state cleanliness. |
| What ARE the four-discipline rules? | Rule 1: Rewrite v1 logic in-place (no flags, no v1+v2 stratification). Rule 2: Rewrite v1 comments (no sticky notes). Rule 3: v2 spec becomes canonical (move v1 to .archive/, PATCH LD 577 source_document). Rule 4: Honest activity log (one new row documenting the patch-forward). |
| What needs code change? | `weekly_preflight_audit.py` PERIODIC branch (replace v1 ladder with v2 6-tier ladder); add `relativedelta` import; add date-hygiene invariants; add startup schema assertion. ~80 net lines diff. |
| What needs Directus PATCH? | LD 577 `source_document` field (v1 → v2); LD 577 `notes` append (patch-forward record + reader inventory). |
| What needs file move? | `git mv PERIODIC_CLASS_TECH_SPEC_v1.md → .archive/`. |
| What needs new Directus row? | One `prod_activity_log` row with explicit `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE` action. |
| Pre-implementation gates? | §10 — 12 gates Kim must approve (debate resolution, discipline rules, sequence, decisions, dependency gate, dataset gate, fingerprint gate, archive authorization, prod-write gate, review gate, halt-on-failure gate, doctrine-precedent gate). |
| Risk class | LOW-to-MEDIUM. Largest risk is discipline drift; §6.5 + §13.6 grep checks mandate HALT on rule break. |
| Doctrine for future similar incidents | "PATCH-FORWARD by default if (a) schema migration is additive, (b) data values are correct under new spec, (c) discipline rules can be applied cleanly. Otherwise roll-back." |

---

## §17 Authorship Trail

- **Drafted:** 2026-05-08 by subagent (dual-Opus advocate/counter pattern per `tech-spec` + `zero-error-qa` skills).
- **Reviewed by:** (pending Kim).
- **Cursor cross-review:** to be requested via `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md`.
- **Approved for implementation:** (pending Kim).
- **Implementation session:** (TBD).
- **Closeout:** (TBD).
- **First real PERIODIC review (validates full v2 ladder lifecycle):** 2026-07-18 (LD 249 quarterly cadence; audit fires WARN_30 at 2026-06-18, ELEVATED at 2026-07-04, CRITICAL_APPROACHING at 2026-07-11, OVERDUE on 2026-07-18 if review not yet conducted).
- **6-month retro** (carried from v1 §16 step 7): 2026-11-07.

---

*End of PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md.*
