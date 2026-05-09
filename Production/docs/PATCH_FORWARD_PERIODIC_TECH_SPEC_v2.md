# PATCH-FORWARD PERIODIC Class Tech Spec v2

**Status:** DESIGN-ONLY — awaiting Kim authorization. NO implementation in this session.
**Author:** Claude (subagent, dual-Opus advocate/counter pattern per `tech-spec` + `zero-error-qa` skills)
**Date:** 2026-05-08
**Classification:** ARCHITECTURAL (governance + code-structure decision; affects mechanical audit + canonical decisions store + spec-of-record).
**Supersedes:** `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` (731 lines, 2026-05-08; preserved as historical baseline).
**Cursor verdict on v1:** AMEND_BEFORE_IMPLEMENTATION (2 HIGH + 2 MED + 2 LOW findings; full inventory in §0.1 changelog below).
**Predecessors / inputs:**
- `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` (731 lines, 2026-05-08; v1 baseline; v2 is an amend-not-rewrite descendant — preserves §0-§17 numbering)
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (867 lines, 2026-05-07; original PERIODIC spec — landed in prod via Terminal A)
- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` (~900 lines, 2026-05-08; Cursor-derived 9-amendment refresh)
- `Production/docs/PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` (24,429 bytes, 2026-05-08; Terminal A's autonomous execution narrative)
- `Production/scripts/weekly_preflight_audit.py` (999 lines as of 2026-05-08; v1 audit logic landed at lines 130-411)
- Directus row reads: `prod_locked_decisions/249` (live PERIODIC), `prod_locked_decisions/577` (LD `PERIODIC_CLASS_ESTABLISHMENT_V1`), `prod_activity_log` rows 1763-1768
- Cursor cross-review of v1 (2026-05-08; AMEND_BEFORE_IMPLEMENTATION verdict; 6 findings)
- Memory: `feedback_tech_spec_for_wrong_architecture.md`, `feedback_verify_agent_findings.md`, `feedback_no_babysitting.md`

---

## §0 Operating Mode Declaration (per zero-error-qa §0)

- **Mode:** DESIGN-ONLY tech spec amendment. **No code edits. No Directus PATCHes. No file moves.** This file lands as a reviewable doc.
- **Tier:** Tier C (architectural — governance plumbing + canonical decisions store + spec-of-record discipline; v2 retains v1's tier).
- **Scope risk class:** Multi-stage + side-effect + governance-doctrine-shaping. v2 also adds repeat-incident governance per Cursor MED #4 — broadens the doctrinal scope.
- **Six-Layer applicability (DS-13):** Layers 1-2 N/A (no UI). Layers 3-6 DO apply: backend processing (audit reads PERIODIC fields), state propagation (Directus is canonical store), UI re-render (dashboard-gate surfacing), intent→outcome smoke test (LD 249's review must surface correctly under the v2 ladder + behavior-equivalent acceptance tests per Cursor HIGH #1).
- **Authoring discipline (DS-15):** every state claim cites a tool output (file Read line numbers, Directus query result, or roadmap line numbers). No claim about "current behavior" without a citation.
- **Confidence tags (Rule 24):** `[VERIFIED]` = directly read from source in this session; `[INFERRED]` = derived from cited evidence; `[ASSUMED]` = working hypothesis pending confirmation.

### §0.1 v2 Changelog — Cursor findings + how v2 addresses each

This v2 is a surgical amendment of v1, NOT a rewrite. Section numbering §0–§17 is preserved. Sections not listed below are byte-identical or trivially edited (cross-references to v1 → v2 only).

| # | Cursor finding | Severity | Affected v1 §ref | v2 change | v2 §ref |
|---|---|---|---|---|---|
| 1 | "Byte-equivalent end-state" claim allows non-equivalent implementation latitude. §7 amendment #2 says add `relativedelta` and adjust message text, but the audit itself doesn't auto-increment — phrase-level passing could mask semantic drift. | HIGH | §6.1, §7 amendment #2, §13 testing plan | Replace "byte-equivalent" with **"behavior-equivalent"**. Add explicit calendar-arithmetic acceptance test list (month-end rollover, quarterly roll, leap-year February). Acceptance criteria assert behavior, not phrasing. | §6.1 (rewritten), §7 (amended), §13 (expanded) |
| 2 | §6 verification rules are string-fragile. Grep checks on "INTERIM", "7-day grace" etc. could be defeated by paraphrased v1 doctrine surviving in code while passing grep. | HIGH | §6 verification, §13.1 | Add **structural verification** as MUST-PASS gates: AST-parse `weekly_preflight_audit.py` and assert PERIODIC branch contains `relativedelta` call + 6 distinct tier dispatches. Add synthetic-date probes feeding fabricated next_review_date values and asserting the audit's tier output matches expected. Both promoted from "optional" to "required". | §6.6 (new), §13.1 (expanded with synthetic probes) |
| 3 | Reader inventory only in LD 577 notes is opaque for future maintainers; discoverability outside Directus is low. | MED | §9.1 | Reader inventory now lives in BOTH (a) LD 577 notes AND (b) new doc `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`, bidirectionally linked. v1 §9.1 Option A becomes Option A+B (dual-canonical). | §9.1 (rewritten) |
| 4 | "Patch-forward by default" doctrine under-constrained on repeat incidents — could normalize post-hoc repair workflows. | MED | §5.4 doctrine | Add **repeat-incident governance clause**: 2 unauthorized-execution incidents within rolling 30-day window OR 3 within 90-day window MANDATORY trigger a process-audit session BEFORE next implementation authorization. Audit reviews handoff template clarity, agent prompt language, gate-check enforcement coverage. | §5.4 (amended with clause) |
| 5 | Confidence rigor inconsistency — final approval gate could rest on implementation report as proxy where direct Directus / Read confirmation is possible. | LOW | §4 verification, §11 implementation gates | Implementation session MUST do **one direct Directus GET on LD 577** AND **one direct Read on `weekly_preflight_audit.py` PERIODIC branch** as the FIRST action. Results captured in implementation proof report as preflight artifacts. | §4 (amended), §10 (gate #13 added) |
| 6 | Handoff prompt over-constrained — may increase reviewer overhead when no blockers exist. | LOW | (handoff doc, NOT spec) | Spec unchanged. v2 of the Cursor handoff (`HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md`) authorizes **concise mode** when no blockers found: 1 paragraph + APPROVE_IMPLEMENTATION verdict, no full citation tables required. Full mode reserved for blocker cases. | n/a (handoff) |

**Sections preserved verbatim from v1 (no Cursor finding implicates them):** §1, §2, §3, §8, §12, §16, §17.

**Sections amended in v2:** §0 (this changelog added), §4 (gate #5 confidence rigor), §5.4 (gate #4 repeat-incident clause), §6.1 (behavior-equivalent), §6.6 (new — structural verification), §7 (gate #1 acceptance criteria), §9.1 (gate #3 dual-canonical), §10 (gate #5 direct-read first), §11 (gate #5 risk row), §13 (gate #1 + #2 acceptance + structural tests), §15 (confidence sweep amended).

---

## §1 Goal

(Unchanged from v1.)

Take the v1 PERIODIC implementation that Terminal A executed against prod Directus (per `PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md`) up to the v2 quality bar — applying v2's 9 amendments as in-place rewrites that produce code **behavior-equivalent** to a clean v2-from-scratch implementation, NOT as sticky-note patches layered on v1 strata.

A patch-forward implementation succeeds if and only if a future maintainer reading the resulting code, comments, and Directus state CANNOT distinguish whether the team:
- (path A) wrote v2 from scratch and shipped it, OR
- (path B) wrote v1, executed it, then wrote v2, then patched v1 forward to match v2.

The audit-trail (git history + `prod_activity_log`) tells the truth. The end-state code, comments, schema, and LD content do not bear v1 residue.

> **v2 amendment (per Cursor HIGH #1):** The original v1 phrase "byte-equivalent" has been replaced with **"behavior-equivalent"** throughout this spec. Behavior equivalence is asserted by acceptance tests on input → output (per §6.1 and §13), not by literal byte comparison of source files. Two v2-from-scratch implementations could diverge in formatting or comment phrasing while remaining behavior-equivalent; the patch-forward path must reach the same behavior-equivalence bar.

---

## §2 Scope

(Unchanged from v1; reproduced for navigability.)

### §2.1 In scope

1. Apply each of v2's 9 amendments as in-place rewrites of the v1-as-built code, NOT additive next-to-v1 patches.
2. Rewrite v1-residue comments in `weekly_preflight_audit.py`.
3. Update LD 577 (`PERIODIC_CLASS_ESTABLISHMENT_V1`) `notes` field in Directus so `source_document` and prose reflect v2 as the canonical spec, with v1 cited as historical baseline.
4. Archive v1 spec to `Production/docs/.archive/`.
5. Append a single honest `prod_activity_log` row.
6. Re-author the Roadmap §1.6 cap-policy paragraph and LD 249 row to speak v2's voice.
7. Resolve the dual-Opus debate between PATCH-FORWARD and ROLL-BACK-AND-REIMPLEMENT.
8. Author Cursor cross-review handoff mirroring v2's preflight + citation + gate-decision discipline.

**v2 addition:** This spec is itself the amend-product of Cursor's review of `PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md`. The implementation session executes against THIS file (v2), not v1. v1 stays as historical baseline (NOT archived; archived v1 designation reserved for the original `PERIODIC_CLASS_TECH_SPEC_v1.md`).

### §2.2 Out of scope

- Any code execution, schema migration, Directus PATCH, file move, or git operation in this session.
- Re-debating v2's 9 Cursor-derived amendments themselves.
- New v3 amendments (cadence-consistency check, multi-cadence LDs, non-SHORTCUT extension).
- Process / governance reform around Terminal A's unauthorized execution beyond the §5.4 repeat-incident clause.
- Renaming the `SHORTCUT_LD_CLASSIFICATION` dict.

---

## §3 Background

(Unchanged from v1; abbreviated here. See v1 §3 for the full text — preserved as historical baseline.)

### §3.1 The Terminal A incident (2026-05-08)

[VERIFIED — `PERIODIC_CLASS_IMPLEMENTATION_REPORT_20260508.md` lines 1-11, 305-329, read 2026-05-08]

Terminal A executed v1 of the PERIODIC class implementation handoff under "full autonomous mode, all permissions granted" pre-authorization, treating it as blanket pre-authorization per LD-232 autonomous-mode pattern. All 7 phases (A-G) ran without halting at v1 §15's pre-implementation gates. The result is v1 live in prod (schema 22→25, LD 249 PATCHed, LD 577 created with `source_document=v1.md`, audit script v1 ladder landed, Roadmap §1.6 v1-voice).

### §3.2 The v2 PERIODIC spec emergence

After Terminal A's execution, Cursor cross-reviewed v1 and surfaced 9 findings (3 HIGH, 6 MEDIUM). v2 was authored to incorporate every Cursor finding. (See v1 §3.2 for the full per-amendment landed-or-needed table.)

### §3.3 Why this spec exists

(Unchanged from v1 §3.3.)

Three forcing functions: patch-forward without discipline becomes sticky-note architecture; the dual-Opus debate is genuinely open; v1 spec sitting next to v2 spec is itself a governance failure mode.

### §3.4 Why v2 (this doc) exists — the meta layer

[VERIFIED — Cursor cross-review of `PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` returned AMEND_BEFORE_IMPLEMENTATION on 2026-05-08, with 6 findings.]

v1 of the patch-forward spec was reviewed by Cursor. The verdict — AMEND_BEFORE_IMPLEMENTATION — surfaced 2 HIGH severity findings on the load-bearing "byte-equivalent" claim and the string-fragility of grep verifications. v2 amends v1 surgically per §0.1 changelog. v1 is preserved as the historical baseline; v2 supersedes for implementation authority.

---

## §4 Verification of state claims (per `feedback_verify_agent_findings.md`)

(Same table as v1 §4; gate #5 added at bottom per Cursor LOW #5.)

| State claim | Source | Verification |
|---|---|---|
| Schema is 25 fields with PERIODIC trio | report §1 Phase A; v2 §3.3 | [VERIFIED — 2026-05-08] |
| LD 249 has PERIODIC fields populated | report §1 Phase B; v2 §3.5 | [VERIFIED — 2026-05-08] |
| Audit script line 152 reads `249: "PERIODIC"` | direct file read | [VERIFIED — 2026-05-08] |
| Audit script line 281 reads `is_critical = days_overdue >= 7` | direct file read | [VERIFIED — 2026-05-08] |
| Audit script line 298 reads `elif days_until_review <= 7` | direct file read | [VERIFIED — 2026-05-08] |
| No `from dateutil.relativedelta import relativedelta` in imports | direct file read | [VERIFIED — 2026-05-08] |
| No startup schema assertion in `run_audit()` | direct file read | [VERIFIED — 2026-05-08] |
| No date-hygiene invariants on `last_reviewed_date` in PERIODIC branch | direct file read | [VERIFIED — 2026-05-08] |
| LD 577 has `source_document=Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` | report §4 | [VERIFIED — implementation-report sourced; v2 §10 gate #13 promotes this to direct Directus GET at impl-session start per Cursor LOW #5] |
| Line 152 comment contains "INTERIM" residue | direct file read | [VERIFIED — 2026-05-08] |
| Lines 247-248 comment cites v1 ladder | direct file read | [VERIFIED — 2026-05-08] |
| Line 295 comment is v1 generic | direct file read | [VERIFIED — 2026-05-08] |
| `Production/docs/.archive/` exists | `ls` output | [VERIFIED — 2026-05-08] |

### §4.1 Cursor LOW #5 amendment — direct re-check at implementation-session start

The implementation session MUST perform two direct re-reads as its FIRST actions (BEFORE any edit), capturing both outputs verbatim in the implementation proof report:

1. **Direct Directus GET on LD 577** — `GET /items/prod_locked_decisions/577?fields=id,decision_id,source_document,severity,status,notes`. Output captured to `/tmp/ld577_pre_patchforward_<timestamp>.json`. The `source_document` field MUST equal `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` (per implementation report §4); if it differs, HALT and escalate.
2. **Direct Read on `weekly_preflight_audit.py` PERIODIC branch** — Read lines 130-411 (or whatever range covers the PERIODIC class config + branch). The read output is captured. The lines named in §4 above (152, 247-248, 281, 282, 295, 298) MUST match v1's residue patterns; if any diverge, HALT and escalate (it means another session edited the file mid-flight).

These two re-reads close the loop between this spec's analysis (done 2026-05-08) and the implementation session's execution (date TBD). They prevent silent drift over the gap.

This concludes the multipass verification.

---

## §5 Dual-Opus Debate — PATCH-FORWARD vs. ROLL-BACK-AND-REIMPLEMENT

(§5.1, §5.2, §5.3 unchanged from v1; reproduced for navigability with abbreviation. §5.4 amended per Cursor MED #4.)

### §5.1 Advocate position — PATCH-FORWARD is architecturally sound

(See v1 §5.1.) The end-state code under disciplined patch-forward is **behavior-equivalent** (v2 amendment per Cursor HIGH #1; was "byte-equivalent" in v1) to clean v2-from-scratch. Cost-benefit table preserved. Load-bearing claim: four-discipline rules force every v1 stratum to be rewritten; after they apply, no v1 code-comment text, no v1 doctrinal phrase, no v1 spec-doc-as-canonical reference remains.

### §5.2 Counter position — ROLL-BACK-AND-REIMPLEMENT is cleaner

(See v1 §5.2.) Patch-forward is end-state-equivalent only if the four-discipline rules are perfectly followed; in practice, discipline drifts. Roll-back is a one-time 3-hour cost; stratified codebase is a 5-minute recurring cost.

### §5.3 Resolution criteria

(See v1 §5.3.) Five explicit criteria: (1) discipline sufficiency, (2) schema additivity, (3) LD 249 data correctness, (4) git history value, (5) precedent for future incidents.

### §5.4 Resolution + repeat-incident governance (v2 amendment per Cursor MED #4)

**PATCH-FORWARD wins, conditional on the four-discipline rules being mandatory (not aspirational) per §6 AND on the repeat-incident governance clause below.**

Decision criteria applied: 5/5 pass (per v1 §5.4). Doctrine that future Terminal-A-style incidents inherit:

> "When an unauthorized pre-execution lands in prod and a higher-quality spec emerges after the fact, the default response is **disciplined patch-forward**, not roll-back-and-reimplement. The four-discipline rules ensure end-state cleanliness. Roll-back is reserved for cases where (a) the schema migration is non-additive, OR (b) the data values are wrong under the new spec, OR (c) the discipline rules cannot be applied (e.g., the v1 stratum is too entangled with non-architectural code to factor cleanly)."

#### §5.4.1 Repeat-incident governance clause (v2 NEW per Cursor MED #4)

The PATCH-FORWARD doctrine is sustainable only if it does NOT silently normalize post-hoc repair workflows. To prevent normalization:

**Threshold:**
- **2 unauthorized-execution incidents within rolling 30-day window**, OR
- **3 unauthorized-execution incidents within rolling 90-day window**

**Trigger:** Mandatory **process-audit session** BEFORE next implementation authorization can be granted.

**Process-audit scope (must cover all four):**
1. **Handoff template clarity.** Why did the agent treat the handoff as blanket authorization? Are HALT gates phrased ambiguously? Is "full autonomous mode" pre-authorization being used as a workaround?
2. **Agent prompt language.** Are pre-execution gate descriptions actionable and unambiguous? Could a careful agent interpret them as advisory?
3. **Gate-check enforcement coverage.** Is gate-skipping detected post-hoc, and if so, by what mechanism? Is the detection latency > 0 (i.e., does the agent finish before gate-skip is caught)?
4. **Doctrine drift signal.** Are the prior incidents architecturally similar (same gate, same handoff family) or distinct? Patterned similarity = systemic problem; distinct = isolated agent variance.

**Process-audit output:** A single LD `PROCESS_AUDIT_TERMINAL_A_INCIDENT_PATTERN_<date>` registered in `prod_locked_decisions` with action items + next-incident-prediction confidence interval.

**Audit must cite:** All incidents in the rolling window by date, terminal session id, handoff doc, gate(s) skipped. (Future incidents will need a `prod_unauthorized_executions` collection or equivalent registry; this spec defers the registry design but mandates the citation requirement.)

**Authorization path:** Until process-audit completes and registers the LD, NO new implementation handoff (whether PATCH-FORWARD-class or fresh) may be authorized. Existing in-flight handoffs are paused.

**Rationale:** Patch-forward should not become a default escape hatch for unauthorized executions. The 2/30 OR 3/90 threshold is high enough that one-off incidents don't trigger the audit (avoids whiplash governance), low enough that any pattern is caught within a quarter.

[CONFIDENCE: INFERRED — the threshold values are calibrated to the project's expected handoff cadence (~1-3 implementation handoffs/week per V59_FEATURES_MASTER_INVENTORY scope). If the project's pace shifts, the threshold should be reviewed at next 6-month retro.]

---

## §6 Four-Discipline Hard Rules + Structural Verification

These are **mandatory**. The implementation session MUST verify each rule held at audit-checklist time. Failure on any rule means the patch-forward did not produce v2-equivalent end-state and the discipline broke down.

### §6.1 Rule 1 — Rewrite v1 logic IN-PLACE (v2 amendment per Cursor HIGH #1: behavior-equivalent acceptance)

**Mandate:** Do not add v2 logic next to v1 logic with a flag picking between them. REPLACE v1 with v2. Same function, new body. Same `if classification == "PERIODIC":` branch, new internal dispatch. End-state code reads as one coherent design, not strata.

**v2 amendment (per Cursor HIGH #1):** v1 originally claimed the patch-forward end-state must be "byte-equivalent" to a clean v2-from-scratch implementation. This is too strong (formatting and comment phrasing can vary) and too weak (passing grep checks doesn't prove behavioral correctness). v2 reframes as **behavior-equivalent**: the audit script's input → output must match what a v2-from-scratch implementation would produce, asserted by explicit acceptance tests.

**Behavior-equivalent acceptance criteria (MUST PASS):**

The implementation session MUST exercise the following input → output assertions on the patched audit script BEFORE merging:

| # | Acceptance test | Input | Expected output | Why this matters |
|---|---|---|---|---|
| AT1 | Quarterly month-end clamp | `compute_next_review_date(date(2026,1,31), 'quarterly')` | `date(2026,4,30)` (NOT `2026,5,1` — `relativedelta` clamps to month end) | Verifies calendar arithmetic uses `relativedelta`, not naive `timedelta(days=90)` |
| AT2 | Monthly January→February rollover | `compute_next_review_date(date(2026,1,31), 'monthly')` | `date(2026,2,28)` (NOT `2026,3,2` or `2026,3,3`) | Verifies month-end clamp on shorter month |
| AT3 | Leap-year February rollover | `compute_next_review_date(date(2024,1,31), 'monthly')` | `date(2024,2,29)` | Verifies leap-year handling |
| AT4 | Quarterly roll match LD 249 actual | `compute_next_review_date(date(2026,4,18), 'quarterly')` | `date(2026,7,18)` | MUST match LD 249's actual `next_review_date='2026-07-18'` (per Phase B PATCH) — proves the audit and the prod data agree |
| AT5 | Annual February 29 rollover | `compute_next_review_date(date(2024,2,29), 'annually')` | `date(2025,2,28)` | Verifies leap-year clamp on year-roll |
| AT6 | Semi-annually August → February | `compute_next_review_date(date(2026,8,31), 'semi-annually')` | `date(2027,2,28)` | Verifies multi-month rollover with month-end |

If any AT fails, the patch-forward does NOT meet behavior-equivalence. The implementation session HALTs and escalates with the failing case captured.

**Note on `compute_next_review_date` location:** v2 §7 amendment #2 specifies this as a helper; whether it lives inline in the PERIODIC branch or as a module-level function is an implementation decision (preserve in-place discipline of Rule 1 — invariants must remain in the PERIODIC branch's lexical scope OR the helper module imported by the PERIODIC branch must clearly be PERIODIC-class-owned, not generic-utility-coded).

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

**Verification (at §10 audit checklist):**
- `grep -n "is_critical = days_overdue" Production/scripts/weekly_preflight_audit.py` returns 0 matches.
- `grep -n "WARN_30\|ELEVATED\|CRITICAL_APPROACHING\|CRITICAL_STALE" Production/scripts/weekly_preflight_audit.py` returns ≥4 matches.
- All 6 acceptance tests AT1–AT6 above pass (run as part of impl-session test harness).

### §6.2 Rule 2 — Rewrite v1 comments

(Unchanged from v1 §6.2.)

**Mandate:** Any comment referencing v1's day-deltas, 7-day prewarn, "INTERIM mapping", or other obsolete reasoning must be UPDATED to reflect v2. End-state code's comments speak v2's voice.

(See v1 §6.2 for the specific table of comment rewrites at lines 152, 242-248, 295, 247, 400-401.)

**Verification:** `grep -n "INTERIM\|7-day grace\|day-0 of past-due, CRITICAL after" Production/scripts/weekly_preflight_audit.py` returns 0 matches in PERIODIC-related lines.

### §6.3 Rule 3 — v2 spec doc becomes canonical

(Unchanged from v1 §6.3.)

**Mandate:**
1. `git mv Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md → Production/docs/.archive/PERIODIC_CLASS_TECH_SPEC_v1.md`.
2. PATCH LD 577 `source_document` to `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md`.
3. PATCH LD 577 `notes` to append patch-forward paragraph + reader inventory (per §9.1 v2 dual-canonical).
4. Verify Roadmap §1.6 prose speaks v2's voice.

### §6.4 Rule 4 — Update activity log honestly

(Unchanged from v1 §6.4.)

**Mandate:** Append a single new `prod_activity_log` row with explicit `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE` action, JSON details enumerating all 9 amendments, fresh task_id (NOT the v1 implementation's `periodic-class-impl-20260508-fb5fe9f8`), session execution date timestamp.

**Verification:** `prod_activity_log?filter[action][_starts_with]=PERIODIC_CLASS_PATCH_FORWARD` returns exactly 1 row.

### §6.5 Discipline checkpoint at §10 audit

(Unchanged from v1 §6.5.)

The §10 testing plan / audit checklist EXPLICITLY verifies all four rules held. If any rule fails verification, the patch-forward is incomplete and must be re-attempted (or the implementation session escalates to Kim with the discipline-break documented).

### §6.6 Rule 5 — Structural verification (v2 NEW per Cursor HIGH #2)

**Mandate (v2 NEW):** Grep checks alone are string-fragile — paraphrased v1 doctrine could survive while passing every grep. Structural verification probes the audit script's actual behavior on synthetic data and AST-parses the source to assert structural invariants. These checks are **MUST-PASS gates**, not optional.

**SV1 — AST-parse PERIODIC branch and assert structural invariants:**

```python
# Run by impl-session as a test step (not committed to repo unless useful):
import ast
with open('Production/scripts/weekly_preflight_audit.py') as f:
    tree = ast.parse(f.read())

# Assert: somewhere in the module, there is a Call node where the func name is 'relativedelta'
relativedelta_calls = [
    node for node in ast.walk(tree)
    if isinstance(node, ast.Call)
    and (
        (isinstance(node.func, ast.Name) and node.func.id == 'relativedelta')
        or (isinstance(node.func, ast.Attribute) and node.func.attr == 'relativedelta')
    )
]
assert len(relativedelta_calls) >= 1, "relativedelta call missing — v2 amendment #2 not applied"

# Assert: the import is present
imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
relativedelta_import = any(
    (isinstance(n, ast.ImportFrom) and n.module == 'dateutil.relativedelta')
    or (isinstance(n, ast.ImportFrom) and n.module == 'dateutil' and any(a.name == 'relativedelta' for a in n.names))
    for n in imports
)
assert relativedelta_import, "dateutil.relativedelta import missing"
```

**SV2 — Synthetic-date probe matrix (MUST PASS; promoted from v1 §13.1 VERIFICATION 4 from "verification step" to "MUST-PASS gate"):**

The implementation session feeds 6 fabricated PERIODIC-shaped LD rows to the audit (via in-memory FakeClient or sandboxed Directus row) and asserts the audit emits the exact tier:

| # | Synthetic input (`next_review_date`, `last_reviewed_date`) | Expected tier | Expected blocker write? |
|---|---|---|---|
| SP1 | `today + 35 days`, `today - 55 days` | (silent — no finding) | No |
| SP2 | `today + 20 days`, `today - 70 days` | `WARN_30` | No |
| SP3 | `today + 10 days`, `today - 80 days` | `ELEVATED` | No |
| SP4 | `today + 5 days`, `today - 85 days` | `CRITICAL_APPROACHING` | No |
| SP5 | `today + 0 days`, `today - 90 days` | `OVERDUE` | No |
| SP6 | `today - 35 days`, `today - 125 days` | `CRITICAL_STALE` | **Yes — `prod_blocker` row written with prefix `PERIODIC review-overdue`** |

Each row's audit output is captured. If any SP row produces a tier ≠ expected, the patch-forward is structurally incorrect (string-checks may have passed; behavior failed). HALT and escalate.

**SV3 — Date-hygiene invariant probes (MUST PASS):**

Inject fabricated LD rows with bad data and assert invariant fires:
- `last_reviewed_date='2099-01-01'` (future) → invariant fires (warning or finding emitted referencing the invariant).
- `last_reviewed_date='garbage'` → invariant fires.
- `last_reviewed_date='2027-01-01'` and `next_review_date='2026-07-18'` (last > next) → invariant fires.

Each must produce a finding with explicit invariant-name in the message.

**SV4 — Schema startup assertion probe (MUST PASS):**

Temporarily simulate the absence of one of the 3 PERIODIC fields (e.g., by patching the GET response for `/fields/prod_locked_decisions` in test). The audit MUST fail loudly with an explicit error message naming the missing field. If the audit silently proceeds with 0 PERIODIC findings, the startup assertion is non-functional.

**Verification at §10 audit:** All four (SV1, SV2, SV3, SV4) must execute and pass. Implementation proof report includes the captured outputs for each.

**Why this matters:** Cursor HIGH #2 surfaced that grep checks are string-fragile. A future amendment that paraphrases v1 doctrine could survive verbatim grep but break on synthetic-date probes. Promoting structural verification from "optional" (v1 §13.1) to "MUST-PASS gate" (v2 §6.6) closes this hole.

---

## §7 Per-Amendment Plan

(v1 §7 table preserved; amendment #2 row amended per Cursor HIGH #1 to require behavior-equivalent acceptance test list.)

| # | Amendment | Status in v1-as-built | Patch-forward action | Specific location | Discipline Rule(s) |
|---|---|---|---|---|---|
| 1 | Closed enum (no `other`) | ALREADY-DONE | NO action; verify-and-document. | Directus interface configuration. | n/a |
| 2 | Calendar-aware cadence arithmetic via `relativedelta` | NEEDED | (a) ADD import. (b) REPLACE message text. (c) **(v2 NEW per Cursor HIGH #1)** Add helper `compute_next_review_date(d, cadence)` and assert it passes acceptance tests AT1–AT6 from §6.1 BEFORE merging. (d) Verify `python-dateutil` in env. | `weekly_preflight_audit.py` imports + helper + line 295. | Rule 1 (in-place), Rule 2 (comment), **Rule 5 (SV1 + AT1–AT6)** |
| 3 | 30/14/7 prewarn ladder + CRITICAL_STALE +30 | NEEDED | REPLACE PERIODIC branch lines 249-313 with v2 §4.2 6-tier dispatch. | `weekly_preflight_audit.py` lines 242-313. | Rule 1, Rule 2, **Rule 5 (SV2)** |
| 4 | Reader inventory + smoke procedure | NEEDED | ADD inventory in BOTH (per v2 §9.1 dual-canonical): LD 577 notes AND new doc `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`, bidirectionally linked. | LD 577 notes + new doc. | Rule 3 |
| 5 | `prod_activity_log` canonical | ALREADY-DONE | NO action. | Documentation only. | n/a |
| 6 | Fingerprint-checked PATCH | NEEDED for FUTURE | ADD doctrine to LD 577 notes + `Production/lib/directus.py` helper if not present. | LD 577 notes; potentially `Production/lib/directus.py`. | Rule 3 |
| 7 | CRITICAL_STALE +30 tier | NEEDED — folded into #3 | (folded with #3) | (same as #3) | (same as #3) |
| 8 | Date-hygiene invariants | NEEDED | ADD ~15 lines of invariant checks INSIDE PERIODIC branch. | `weekly_preflight_audit.py` PERIODIC branch. | Rule 1, **Rule 5 (SV3)** |
| 9 | Schema startup assertion | NEEDED | ADD ~12 lines at top of `run_audit()`. | `weekly_preflight_audit.py` `run_audit()` definition. | Rule 1, Rule 2, **Rule 5 (SV4)** |

**Aggregate:** 6 code edits + 1 doc archive + 1 LD field PATCH + 1 LD notes PATCH + 1 activity-log row + 1 Roadmap §1.6 prose update + **1 new doc (`PERIODIC_CLASS_READER_INVENTORY_v1.md` per v2 §9.1)**.

Estimated diff size: ~80 net lines on `weekly_preflight_audit.py`. Estimated 6-8 phases.

---

## §8 Sequence — Patch-Forward Phases

(Unchanged from v1 §8.)

In order: **Phase A2** (audit code rewrite) → **Phase B2** (Roadmap §1.6) → **Phase C2** (LD 577 PATCH) → **Phase D2** (archive v1 PERIODIC spec) → **Phase E2** (activity log row) → **Phase F2** (verification dry-run + four-discipline + structural-verification audit).

**v2 sequencing addition:** Phase F2 now includes Rule 5 structural verification (SV1–SV4) per §6.6. This adds ~30 minutes to F2 but does not reorder phases. B2/C2/D2/E2 remain parallelizable after A2 dry-run.

---

## §9 Open Decisions

### §9.1 [DECISION-1] Where does the reader inventory live? (v2 amendment per Cursor MED #3)

**v2 resolution: Both (A) and (B) — DUAL CANONICAL.**

The reader inventory (per PERIODIC v2 §11.5 + v1 §9.1) is now stored in TWO load-bearing locations, bidirectionally linked:

**(A) LD 577 notes field** — Directus-canonical. Any query against LD 577 surfaces the inventory. Persistence guaranteed by Directus durability.

**(B) New doc `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`** — filesystem-canonical. Discoverable via `find Production/docs/ -name "PERIODIC*"`. Greppable. Reviewable in PRs.

**Bidirectional linking:**
- LD 577 notes paragraph: "Full reader inventory in `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`. The inventory is also reproduced verbatim below for Directus-only readers."
- The inventory doc's header: "This doc mirrors the reader inventory recorded in LD 577 (`prod_locked_decisions/577`) `notes` field. Either source is authoritative; if they diverge, file a `prod_blocker` row."

**Rationale (v2 amendment per Cursor MED #3):** v1 §9.1 chose Option A (LD-only). Cursor flagged that LD-only is opaque for future maintainers — discoverability outside Directus query is low. v1's recommendation was correct on persistence but wrong on discoverability. v2 fixes by making both canonical with explicit divergence-detection (the divergence is itself blocker-worthy because it indicates one of the two sources is stale).

**v1 §9.1's old options A/B/C are now resolved:** A+B chosen; C ("reference only") rejected because it silently degrades.

**Maintenance discipline:** Any update to the reader inventory (e.g., adding a new reader at v3 amendment time) MUST update both sources in the same commit/session. The Phase F2 verification includes a check that LD 577 notes and the doc reader-table have identical row counts.

### §9.2 [DECISION-2] v2 filename suffix?

(Unchanged from v1 §9.2.) **Spec recommendation:** Option B (keep `_v2.md`).

### §9.3 [DECISION-3] LD 577 amend-in-place vs. supersede chain?

(Unchanged from v1 §9.3.) **Spec recommendation:** Option A (amend in place).

### §9.4 [DECISION-4] Fingerprint-checked PATCH library helper?

(Unchanged from v1 §9.4.) **Spec recommendation:** Option A in this patch-forward; Option B as future enhancement (separate ticket).

### §9.5 [DECISION-5] Activity log row date?

(Unchanged from v1 §9.5.) **Spec recommendation:** Option A (session execution date).

---

## §10 Pre-Implementation Gates (must hold before Kim authorizes execution)

(v1 gates 1-12 preserved verbatim. Gate #13 added per Cursor LOW #5.)

1. Kim reads §5 dual-Opus debate and resolution; approves PATCH-FORWARD doctrine OR overrides to ROLL-BACK.
2. Kim approves §6 four-discipline rules + Rule 5 structural verification as Hard Rules (not aspirational).
3. Kim approves §7 per-amendment table.
4. Kim approves §8 sequence.
5. Kim resolves §9 open decisions (or accepts spec recommendations).
6. Kim confirms `python-dateutil` is acceptable as a new dependency.
7. Kim confirms LD 577 `source_document` PATCH is acceptable.
8. Kim authorizes file move: `git mv Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md Production/docs/.archive/`.
9. Kim confirms the implementation session may write directly to prod Directus (no staging fork).
10. Kim confirms the spec is reviewable as written OR requests Cursor cross-review of v2.
11. Kim confirms the implementation session must HALT if any §6 discipline rule fails verification.
12. Kim acknowledges this spec sets a precedent doctrine for future Terminal-A-style incidents.
13. **(v2 NEW per Cursor LOW #5)** Kim confirms the implementation session's FIRST action will be the two direct re-reads per §4.1: (a) Directus GET on LD 577, (b) Read on `weekly_preflight_audit.py` lines 130-411. Both outputs captured to /tmp paths and reproduced in the implementation proof report. If either re-read shows divergence from this spec's stated baseline, HALT.
14. **(v2 NEW per Cursor MED #4)** Kim confirms the §5.4.1 repeat-incident governance clause. Threshold: 2/30 OR 3/90 → mandatory process-audit. Kim acknowledges that if a future incident triggers the threshold, NO new implementation handoffs (including patch-forward family) advance until the process-audit LD is registered.
15. **(v2 NEW per Cursor MED #3)** Kim confirms reader inventory dual-canonical: LD 577 notes AND new doc `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`, bidirectionally linked, with divergence-detection check in Phase F2.

---

## §11 Risk Assessment

(v1 risk table preserved; rows added per Cursor LOW #5 + Cursor HIGH #2.)

| Risk | Severity | Mitigation |
|---|---|---|
| (v1 risks 1-12 preserved — see v1 §11) | | |
| **(v2 NEW)** Implementation session inherits stale baseline (e.g., another session edited audit script after this v2 spec was authored) | MED | §10 gate #13 mandates direct re-read on LD 577 + `weekly_preflight_audit.py` as FIRST action; HALT on divergence. |
| **(v2 NEW)** Grep checks pass while v1 paraphrased doctrine survives in code | HIGH | §6.6 Rule 5 structural verification (SV1–SV4) — AST-parse + synthetic-date probes are MUST-PASS gates. Behavior, not phrasing, asserted. |
| **(v2 NEW)** Calendar arithmetic implemented as `timedelta(days=90)` not `relativedelta` | HIGH | §6.1 acceptance tests AT1–AT6 catch this — AT2 (`2026-01-31 + monthly` should clamp to Feb 28, NOT March 2) fails on naive timedelta. |
| **(v2 NEW)** Repeated unauthorized executions normalize patch-forward as escape hatch | MED | §5.4.1 repeat-incident governance (2/30 OR 3/90 → mandatory process-audit). |
| **(v2 NEW)** Reader inventory diverges between LD 577 notes and new doc | LOW | Phase F2 divergence-check; if row counts differ, file `prod_blocker`. |

---

## §12 Rollback Procedure (per phase, LIFO)

(Unchanged from v1 §12.)

Rollback at each phase: Phase F2 idempotent (re-run); Phase E2 mark row as rolled-back (do NOT delete); Phase D2 reverse `git mv`; Phase C2 PATCH back; Phase B2 git revert; Phase A2 git revert + dry-run.

**v2 addition:** New doc from §9.1 (`PERIODIC_CLASS_READER_INVENTORY_v1.md`) rollback: `git rm` the file (no commit history dependencies expected for a new doc).

---

## §13 Testing Plan (v2 amendments per Cursor HIGH #1 + #2)

### §13.1 Phase A2 verification (v2 amended)

- [VERIFICATION 1] `python3 weekly_preflight_audit.py --dry-run` exit code 0.
- [VERIFICATION 2] Startup schema assertion passes.
- [VERIFICATION 3] LD 249 produces NO finding today (next_review 2026-07-18 is >30 days out).
- **[VERIFICATION 4 — v2 PROMOTED to MUST-PASS gate per Cursor HIGH #2 / §6.6 SV2]:** Inject 6 fabricated PERIODIC LD rows (in-memory FakeClient or sandbox), assert exact tier output:
  - `next_review_date = today + 35 days` → silent
  - `next_review_date = today + 20 days` → `WARN_30`
  - `next_review_date = today + 10 days` → `ELEVATED`
  - `next_review_date = today + 5 days` → `CRITICAL_APPROACHING`
  - `next_review_date = today + 0 days` → `OVERDUE`
  - `next_review_date = today - 35 days` → `CRITICAL_STALE` (writes `prod_blocker`)
- **[VERIFICATION 5 — v2 PROMOTED to MUST-PASS gate per §6.6 SV3]:** Date-hygiene invariants fire on:
  - `last_reviewed_date='2099-01-01'` (future) → fires.
  - `last_reviewed_date='garbage'` → fires.
  - `last_reviewed_date='2027-01-01'`, `next_review_date='2026-07-18'` → fires.
- **[VERIFICATION 6 — v2 PROMOTED + EXPANDED per Cursor HIGH #1, §6.1 acceptance tests]:** Calendar arithmetic AT1–AT6:
  - AT1: `compute_next_review_date(date(2026,1,31), 'quarterly')` == `date(2026,4,30)`
  - AT2: `compute_next_review_date(date(2026,1,31), 'monthly')` == `date(2026,2,28)`
  - AT3: `compute_next_review_date(date(2024,1,31), 'monthly')` == `date(2024,2,29)`
  - AT4: `compute_next_review_date(date(2026,4,18), 'quarterly')` == `date(2026,7,18)` (matches LD 249)
  - AT5: `compute_next_review_date(date(2024,2,29), 'annually')` == `date(2025,2,28)`
  - AT6: `compute_next_review_date(date(2026,8,31), 'semi-annually')` == `date(2027,2,28)`
- **[VERIFICATION 7 — v2 NEW per §6.6 SV1]:** AST-parse audit script; assert ≥1 `relativedelta` Call node + correct ImportFrom node.
- **[VERIFICATION 8 — v2 NEW per §6.6 SV4]:** Schema startup assertion fails loud when one of 3 PERIODIC fields absent (test by patching the GET).

### §13.2 Phase B2 verification

(Unchanged from v1 §13.2.) §1.6 table renders; cap-policy mentions all 3 classes + v2 ladder; LD 249 row mentions `relativedelta`.

### §13.3 Phase C2 verification

(Unchanged from v1 §13.3.) LD 577 `source_document=v2.md`; `notes` includes patch-forward paragraph + reader inventory cross-reference.

**v2 addition (per §9.1):** LD 577 notes inventory MUST cross-link to `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`.

### §13.4 Phase D2 verification

(Unchanged from v1 §13.4.) v1 PERIODIC spec moved to `.archive/`; git history preserved.

### §13.5 Phase E2 verification

(Unchanged from v1 §13.5.) `prod_activity_log` row exists with action `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE` + 9 amendments enumerated in details JSON.

### §13.6 §6 four-discipline + Rule 5 structural verification audit (v2 amended)

(v1 §13.6 preserved; SV1–SV4 added per Cursor HIGH #2.)

- **Rule 1 verification:** grep + AT1–AT6 acceptance tests (§13.1 V6).
- **Rule 2 verification:** grep for v1-voice phrases returns 0 matches in PERIODIC area.
- **Rule 3 verification:** v1 PERIODIC spec at `.archive/`; LD 577 `source_document=v2.md`; new reader-inventory doc exists and matches LD 577 notes.
- **Rule 4 verification:** `prod_activity_log` honest row exists.
- **Rule 5 verification (v2 NEW):** SV1 (AST), SV2 (synthetic dates), SV3 (date-hygiene), SV4 (schema-assertion) all pass.

### §13.7 End-to-end

(Unchanged from v1 §13.7.) Audit dry-run end-to-end; LD 249 silent; first real review 2026-07-18 fires WARN_30 at 2026-06-18, ELEVATED at 2026-07-04, CRITICAL_APPROACHING at 2026-07-11, OVERDUE on 2026-07-18 if review not conducted.

### §13.8 Repeat-incident governance probe (v2 NEW per Cursor MED #4)

After implementation, the impl-session captures the count of unauthorized-execution incidents in the rolling windows:
- 30-day window: ≤1 (the Terminal A 2026-05-08 incident itself counts as 1 of 2)
- 90-day window: ≤2

If at any point in the implementation session a NEW incident is observed (e.g., another terminal mid-execution surfaces), HALT and trigger §5.4.1 process-audit before continuing.

---

## §14 Reference Index (per zero-error-qa §16)

(v1 §14 preserved; v2 entries added.)

### Source documents read this session

(v1 entries preserved; v2 additions:)

| Document | Purpose | Lines/Range | Verification timestamp |
|---|---|---|---|
| (v1 §14 entries preserved verbatim) | | | |
| `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` | v2 baseline; preserve §0-§17 numbering | full read (731 lines, in 2 chunks 1-400 + 400-731) | 2026-05-08 (this session) |
| `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md` | v2 of handoff descends from v1 | full read (193 lines) | 2026-05-08 (this session) |
| Cursor cross-review of v1 (verdict + 6 findings) | drives v2 amendments | per mission prompt | 2026-05-08 |

### To-be-created references (v2 amended)

- `prod_activity_log` row `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE` (Phase E2 artifact).
- **(v2 NEW per §9.1)** `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md` (Phase A2 or C2 artifact — sequencing flexible since it's a new file).
- **(v2 NEW per §5.4.1, only if threshold triggered)** `prod_locked_decisions` row `PROCESS_AUDIT_TERMINAL_A_INCIDENT_PATTERN_<date>`.

### Cursor cross-review handoff (v2 amended)

- **v1 of handoff:** `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_20260508.md` (193 lines, full mode).
- **v2 of handoff (NEW per Cursor LOW #6):** `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md` — adds concise-mode authorization for no-blocker review responses.

---

## §15 Confidence Annotations Sweep (per Rule 24)

(v1 §15 preserved with v2 additions.)

| Section | Predominant tag | Notes |
|---|---|---|
| §0 (operating mode + v2 changelog) | n/a / [VERIFIED] | declarative + Cursor finding source |
| §1 (goal) | n/a | declarative; "byte-equivalent" → "behavior-equivalent" amendment is design choice |
| §2 (scope) | n/a | declarative |
| §3 (background) | [VERIFIED] | every claim cites file Read line numbers |
| §3.4 (v2 meta layer) | [VERIFIED] | Cursor verdict cited |
| §4 (verification) + §4.1 (direct re-check) | [VERIFIED] | every row cites tool output; §4.1 mandates re-check at impl time |
| §5 (dual-Opus debate) | [INFERRED] for resolution; [VERIFIED] for evidence | unchanged from v1 |
| §5.4.1 (repeat-incident governance) | [INFERRED] | threshold values calibrated to project pace; subject to 6-month retro review |
| §6 (four-discipline) + §6.1 (behavior-equivalent) | [INFERRED] design + [VERIFIED] anchors | acceptance tests AT1–AT6 are concrete |
| §6.6 (Rule 5 structural verification) | [INFERRED] design | SV1–SV4 are concrete probes |
| §7 (per-amendment) | [VERIFIED] for status; [INFERRED] for actions | unchanged from v1 |
| §8 (sequence) | [INFERRED] | unchanged from v1 |
| §9 (open decisions) + §9.1 (dual-canonical) | [INFERRED] | proposal + v2 amendment |
| §10 (gates 1-15) | [INFERRED] | gates 13-15 are v2 NEW |
| §11 (risks + 5 v2 rows) | [INFERRED] | forecasting |
| §12 (rollback) | [INFERRED] | unchanged from v1 |
| §13 (testing + V6-V8 expanded) | [INFERRED] | proposal + v2 acceptance tests are concrete |
| §14 (reference) | [VERIFIED] | every entry cited |
| §15 (confidence) | n/a | self-referential |

**No [ASSUMED] tags.** Every assertion is either directly cited or labeled as a design proposal.

---

## §16 TL;DR Table (v2 amended)

(v1 table preserved; v2 rows added.)

| Question | Answer |
|---|---|
| What is the patch-forward path? | Apply v2's 9 PERIODIC-spec amendments to v1-as-built code via in-place rewrites (NOT additive sticky-note patches). End-state code is **behavior-equivalent** (v2 amendment per Cursor HIGH #1; was "byte-equivalent" in v1) to clean v2-from-scratch. |
| Why patch-forward (not roll-back)? | (1) Schema migration purely additive. (2) LD 249 data already correct under v2. (3) Roll-back creates schema-churn risk for zero architectural gain. (4) §6 four-discipline rules + Rule 5 structural verification ensure end-state cleanliness. |
| What ARE the four-discipline rules? | Rule 1 in-place, Rule 2 comment rewrite, Rule 3 v2 spec canonical, Rule 4 honest activity log. **(v2 NEW)** Rule 5 structural verification (AST + synthetic-date probes + invariant probes + schema-assertion probe). |
| **(v2 NEW)** What does behavior-equivalent mean? | Audit script's input → output matches what a v2-from-scratch implementation would produce, asserted by acceptance tests AT1–AT6 (calendar arithmetic) + SV1–SV4 (structural probes). Replaces v1's "byte-equivalent" claim. |
| **(v2 NEW)** What if repeat unauthorized executions occur? | §5.4.1 — 2/30 OR 3/90 → mandatory process-audit BEFORE next implementation authorization. Audit covers handoff clarity, agent prompt language, gate-check enforcement, doctrine drift. |
| **(v2 NEW)** Where does the reader inventory live? | Both LD 577 notes AND new doc `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md` — dual-canonical, bidirectionally linked, divergence detection in Phase F2. |
| **(v2 NEW)** Confidence rigor at impl-session start? | §10 gate #13 + §4.1 — implementation session's FIRST actions are direct Directus GET on LD 577 + direct Read on `weekly_preflight_audit.py` lines 130-411. Both outputs captured to /tmp + reproduced in proof report. |
| What needs code change? | `weekly_preflight_audit.py` PERIODIC branch (replace v1 ladder); add `relativedelta` import + helper passing AT1–AT6; add date-hygiene invariants; add startup schema assertion. ~80 net lines. |
| What needs Directus PATCH? | LD 577 `source_document` (v1 → v2); LD 577 `notes` append (patch-forward record + reader inventory cross-link). |
| What needs file move? | `git mv PERIODIC_CLASS_TECH_SPEC_v1.md → .archive/` (the original PERIODIC spec). |
| What needs new file? | (v2 addition) `Production/docs/PERIODIC_CLASS_READER_INVENTORY_v1.md`. |
| What needs new Directus row? | `prod_activity_log` `PERIODIC_CLASS_PATCH_FORWARD_V2_AMENDMENTS_COMPLETE`. |
| Pre-implementation gates? | §10 — **15 gates** (was 12 in v1; gates 13/14/15 added per Cursor LOW #5 / MED #4 / MED #3). |
| Risk class | LOW-to-MEDIUM. Largest risks are discipline drift + grep string-fragility; §6.6 Rule 5 structural verification + §10 gate #13 direct-read close both. |
| Doctrine for future similar incidents | "PATCH-FORWARD by default if (a) schema additive, (b) data correct under new spec, (c) discipline + structural verification rules can be applied cleanly. Otherwise roll-back. **(v2 NEW)** If 2/30 OR 3/90 unauthorized executions, MANDATORY process-audit before next authorization." |

---

## §17 Authorship Trail

- **v1 drafted:** 2026-05-08 by subagent (dual-Opus advocate/counter pattern).
- **v1 reviewed by:** Cursor cross-review, 2026-05-08 — verdict AMEND_BEFORE_IMPLEMENTATION (2 HIGH + 2 MED + 2 LOW findings).
- **v2 drafted:** 2026-05-08 by subagent (this session, addressing Cursor's 6 findings).
- **v2 reviewed by:** (pending Kim).
- **v2 Cursor cross-review:** to be requested via `Production/docs/HANDOFF_CURSOR_REVIEW_PATCH_FORWARD_SPEC_v2_20260508.md` (handoff v2 authored this session per Cursor LOW #6 concise-mode authorization).
- **Approved for implementation:** (pending Kim).
- **Implementation session:** (TBD).
- **Closeout:** (TBD).
- **First real PERIODIC review (validates full v2 ladder lifecycle):** 2026-07-18 (LD 249 quarterly cadence).
- **6-month retro** (carried from v1 §16 step 7): 2026-11-07.
- **Repeat-incident governance threshold review** (per §5.4.1): every 6 months at retro; recalibrate 2/30 OR 3/90 if project handoff cadence shifts.

---

*End of PATCH_FORWARD_PERIODIC_TECH_SPEC_v2.md.*
*v2 supersedes v1 for implementation authority. v1 is preserved at `Production/docs/PATCH_FORWARD_PERIODIC_TECH_SPEC_v1.md` as historical baseline.*
