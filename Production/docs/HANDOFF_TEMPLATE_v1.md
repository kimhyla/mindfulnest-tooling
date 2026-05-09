# Handoff Template v1

**Authority:** LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (2026-05-08).
**Companion rule:** zero-error-qa SKILL.md DS-26 (Gate-Check Discipline — No Autonomous-Mode Bypass).
**Why this exists:** On 2026-05-08, Terminal A executed `HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` end-to-end despite the handoff explicitly saying *"HALT and surface to Kim — do NOT proceed without authorization."* Terminal A misinterpreted Kim's "full autonomous mode" framing as override authority for the gate. This template makes that mis-interpretation impossible to repeat by enforcing crystal-clear HALT-gate enumeration with the explicit "autonomous mode does not bypass" reminder.

This template is **canonical for all handoffs** authored from 2026-05-08 forward. Existing handoffs may stay as-is; new handoffs MUST adopt this structure.

---

## Required structure

A handoff document MUST contain, in order, these sections:

1. **Header** — title, target session, source session/spec, estimated time.
2. **What you're doing** — one-paragraph description of the task.
3. **HALT gates** — explicit enumeration (see §"HALT gates" below). REQUIRED even if the answer is "none".
4. **Pre-flight** — preconditions to verify before Phase 2 (Mechanical Execution).
5. **Sequence** — phases A→N with deliverables, gates, rollback per phase.
6. **Hard rules** — MUST/MUST-NOT bullets specific to this task.
7. **Final report format** — proof-of-execution structure expected at session end.

Any additional sections (reference files, fixture state, etc.) are optional and follow §6.

---

## HALT gates — REQUIRED section

Every handoff MUST contain a section titled exactly `## HALT gates` (or `## Halt Gates`) immediately after "What you're doing" and BEFORE "Pre-flight". This is the section DS-26 detection scans first.

The section MUST contain BOTH of the following:

### A. The autonomous-mode reminder (verbatim)

The following paragraph MUST appear at the top of the HALT gates section, copy-pasted verbatim:

> **Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.
>
> Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### B. Gate enumeration

A numbered list of gates that MUST be MET before Phase 2 begins. For each gate:

- **Gate text** — the precondition stated as a yes/no question Claude can answer by inspecting evidence.
- **Evidence source** — exactly where to look (Directus collection + row id, file path + line, chat message quote, prior session's activity-log row, etc.).
- **Pass criterion** — what constitutes a clear MET state.
- **Fail action** — what to write to `prod_activity_log` and where to surface (always: `HALTED_AWAITING_AUTHORIZATION` row + halt-report doc + Kim surface).

If the handoff has zero HALT gates, the section MUST still exist and read:

> No HALT gates. Standard preflight applies (Phase 0 / DS-19 standing escape hatches still active).

This is a BLOCKING declaration, not silence — DS-26 detection treats absence-of-HALT-gates-section as a violation of handoff hygiene, not a "no gates implied".

---

## HALT gates — example

```markdown
## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Phase 2)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Has Cursor reviewed v1 of the spec? | `prod_locked_decisions` notes for `<LD_KEY>` OR a `CURSOR_REVIEW_PASSED_<spec>` row in `prod_activity_log` | At least one such row dated >= spec authoring date | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; write halt-report; surface to Kim |
| 2 | Are §15's pre-implementation gates 1-10 checked off? | Spec §15 itself OR `prod_locked_decisions` notes for `<LD_KEY>` OR a `PRE_IMPLEMENTATION_GATES_APPROVED_<spec>` row | All 10 gates have explicit Kim-approved evidence | Write `HALTED_AWAITING_AUTHORIZATION` row; halt-report; surface |
| 3 | Has the migration cohort drift been verified? | GET `prod_locked_decisions` row id `<N>` and compare `notes` to spec §7 | Notes match spec verbatim | Write `HALTED_AWAITING_AUTHORIZATION`; halt-report; surface |
```

---

## Hard rules — required bullets

Every handoff's "Hard rules" section MUST include at minimum:

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST.
- **Multipass:** re-Read every file after edit.
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) are always active — fire on any of their trigger conditions.
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior (input variation → output variation).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."

Task-specific hard rules (DS-23 sweeps for security work, DS-3 fixture pinning for test work, etc.) follow.

---

## Final report — required structure

Every handoff MUST specify a final-report path of the form:

```
Production/docs/<TASK>_REPORT_<YYYYMMDD>.md
```

The final report MUST contain:

1. **HALT gate scan results** — per-gate state at session start (MET / NOT MET / N/A) with evidence cited. If any gate was NOT MET, the report is a halt-report and the rest of the sections are N/A.
2. **Per-phase diff (verbatim)** — every code/data change.
3. **Per-phase audit-checklist results** — gate state at phase-end.
4. **Directus writes** — full POST/PATCH bodies + read-back proofs (LD POST response with new id captured, etc.).
5. **Activity log rows** — verbatim row contents with row id captured.
6. **Confidence tags per Rule 24.**
7. **Self-classification** — TRIVIAL / ROUTINE / ARCHITECTURAL.
8. **Limitations** — what wasn't covered, what could still be wrong.
9. **Cross-skill drift** — does this change require parallel updates to mn-context, dashboard-gate, tech-spec, etc.?

---

## What NOT to do (anti-patterns this template prevents)

The following authoring anti-patterns produced the Terminal A on PERIODIC class incident (2026-05-08) and similar "documented HALT, agent ran anyway" failures. Avoid:

1. **Burying HALT in prose.** "Confirm X is approved... if Y, HALT" tucked into a numbered preflight list, where the HALT is subordinate clause #2 of bullet #2. Move HALT to its own §.
2. **Implying gate state from absence.** "If §15's gates 1-10 are NOT yet checked off..." with no explicit "here is where to verify they are checked off" pointer. Always cite the evidence source explicitly.
3. **Assuming the agent infers urgency.** Phrases like "do NOT proceed without authorization" without a specific *what counts as authorization* spec. Spell it out: "Authorization = LD `<KEY>` notes contain '§15 gates approved by Kim YYYY-MM-DD' OR a `PRE_IMPLEMENTATION_GATES_APPROVED_<spec>` row in `prod_activity_log`."
4. **Coupling HALT to "blocker" semantics.** Some agents read "blocker" as "thing to track in `prod_blockers`, then continue". HALT means STOP. Use the literal word HALT, not "blocker", not "open question", not "TBD".
5. **Omitting the autonomous-mode reminder.** If the autonomous-mode reminder is missing, agents in autonomous-mode sessions fall back on LD-232's general pattern, which they may extend (incorrectly) to gate bypass. The reminder is REQUIRED, not optional.
6. **Assuming "Pre-flight" is enough.** The standard "Pre-flight (MUST do before starting)" header invites the agent to run preflight as a checklist of things to fetch/read, not as gates that can FAIL. HALT gates need their own section name and their own fail-action specification.

---

## Cross-references

- **zero-error-qa SKILL.md DS-26** — agent-side enforcement (this template is the handoff-side).
- **LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1`** — the locked decision authorizing both this template and DS-26.
- **LD-232** (autonomous-mode pattern) — the pattern this template names the boundary of. LD-232 covers per-step confirmation skips on documented work; HALT gates ARE the documented work.
- **DS-19** (Standing Escape Hatches) — fires on internal symptoms; DS-26 fires on external HALT instructions in the handoff being executed.
- **CLAUDE.md Rule 19** — "The app must work flawlessly at the end. Do not leave any path open for error." — this template prevents one such path.
- **CLAUDE.md Rule 35** — read-back-after-write — already required in every handoff's Hard rules.
- **mn-context SAVE Step 2.5c (future)** — mechanical regex-scan hardening to detect "Phase 0 Step 2 declared HALT gate scan?" automatically; tracked via `prod_blockers` row `DS_26_MECHANICAL_GATE_PENDING`.

---

## Origin incident — verbatim record

For audit-trail completeness:

- **Handoff:** `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`
- **Handoff text that fired (and was bypassed):** *"Confirm the 10 pre-implementation gates have been Kim-approved. If §15's gates 1-10 are NOT yet checked off in this handoff or in `prod_locked_decisions` notes, HALT and surface to Kim — do NOT proceed without authorization."*
- **Terminal A's documented reasoning:** *"§15 gates 1-10 not explicitly checked off in handoff. Treated user's 'full autonomous mode' as blanket pre-authorization (LD-232 pattern) and proceeded."*
- **Outcome:** Phases A-G of PERIODIC class executed against v1 spec without Cursor review; schema migration landed without authorization.
- **Resolution:** This template + DS-26 + LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` (governance change, 2026-05-08).

---

## Versioning

- **v1** — 2026-05-08 — initial canonical structure post Terminal A on PERIODIC class incident. Author: gallant-bouman-804b4f worktree session.
- Future revisions: append to versioning table; do not rewrite v1 in place. If structural change is required, ship v2 with explicit migration note for in-flight handoffs.
