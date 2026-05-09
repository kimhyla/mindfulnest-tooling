# Handoff v2 — Cursor Cross-Review of Schema Vocab Migration Tech Spec

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md`
**Companion docs:**
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates the spec.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive fix that has already shipped (LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1`).
- `Production/scripts/governance_drift_check.py` — Part 1 vocab-tolerant consumer.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms).

This handoff is **v2 format** — incorporates the 4 v2-template hardening rules: anchored citation discipline + concise→full escalation + numeric AMEND_V2 thresholds + absolute-path filesystem discipline.

---

## §0.1 v2 changelog — template-level v2 fixes baked in

This is a NEW handoff (no v1 predecessor), so the "v2 changelog" is template-conformance, not Cursor-amendment-driven:

| # | v2 template rule | How this handoff conforms |
|---|---|---|
| 1 | Anchored citation discipline (no fixed-line-number quotes) | Step 0 cites by anchor (header, decision_key, snippet) + capture-line-range. |
| 2 | Concise→full escalation rule | §"Step 2 prompt block" includes the verbatim mandate. |
| 3 | Numeric AMEND_V2 thresholds for evaluative questions | §"Analysis tasks" each tie verdicts to numeric triggers. |
| 4 | Absolute-path filesystem discipline | §"Hard rules" includes the verbatim DS-27 clause; no `cd` into worktrees. |

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Step 2 begins)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Has the spec file at `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` been authored AND committed to disk? | `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md"` | File exists, size > 10 KB, mtime is today | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; surface to Kim |
| 2 | Has the cleanup report (`SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`) been read into context BEFORE critiquing the spec? | Quote anchor: locate `## 0. Confirmed environment baseline` header in the report; capture line range; quote the severity distribution table | Reviewer emits the table verbatim inline | HALT and report which anchor failed |
| 3 | Has Part 1 (LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1`) actually shipped per the spec's claim? | Directus query: `prod_locked_decisions` row where `decision_key = SCHEMA_VOCAB_TOLERANT_FILTER_V1` AND `status = active` | Row exists, severity=HARD, date_locked=2026-05-08 | Note "LD #586 not found — Part 1 may not have shipped"; AMEND_V2 verdict on §1 |

---

## Step 0 — Preflight (do FIRST, before any analysis)

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** run `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md"` — capture size and mtime.
2. **Spec hash:** run `shasum "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md"` — capture hex digest.
3. **Anchored quote of spec header:** locate the `# Schema Vocab Migration — Tech Spec v1` header anchor and quote the first 25 non-blank lines as proof you read the actual file (not a stale or fabricated copy). Capture the line range these 25 lines occupy.
4. **Companion-file integrity checks (v2 anchored discipline):** for each of the 4 companion files below, run `ls -la` AND `shasum` AND quote the file's first non-blank line verbatim with capture-line-range. Existence-only is no longer sufficient.

   | Companion file | Anchored check |
   |----------------|----------------|
   | `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` | `ls -la` + `shasum` + first non-blank line + line range |
   | `Production/lib/severity_vocab.py` | `ls -la` + `shasum` + first non-blank line + line range |
   | `Production/scripts/governance_drift_check.py` | `ls -la` + `shasum` + locate the `from lib.severity_vocab import` import block (anchor: `lib.severity_vocab`); capture line range; quote verbatim |
   | `Production/docs/HANDOFF_TEMPLATE_v2.md` | `ls -la` + `shasum` + first non-blank line + line range |

   Acceptance criterion: 4 shasum digests + 4 anchored quotes emitted inline. If any digest cannot be computed OR any anchor cannot be located by header/snippet, **HALT and report which companion failed**. Existence-only does NOT pass v2 preflight.

5. **LD #586 row check:** attempt to query Directus `prod_locked_decisions` for the row where `decision_key = SCHEMA_VOCAB_TOLERANT_FILTER_V1`. If Directus is unreachable, record "Directus unreachable — LD #586 verification deferred to Analysis Task F fallback rule" and proceed; do NOT HALT for this single check.

6. **Live data baseline confirmation:** independently verify (via Directus query OR by reading the cleanup report's §0 verbatim) that the dataset still has 11 distinct severity values + 68 task_category values + 17 scope_domain values, OR document the new live counts inline. The migration mappings in the spec assume the report's snapshot baseline.

If any preflight check (1-4) fails, **HALT and report**. Do not proceed to Step 1.

---

## Step 1 — Open the project in Cursor

Project root (absolute path, no `cd` into worktrees):

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md. It proposes a 4-rule mass migration of the prod_locked_decisions Directus collection's severity / task_category / scope_domain columns into canonical state. The spec is DESIGN ONLY; execution is gated on Kim's per-rule approval (8 gates in §6).

Background context (informational only — do NOT let this anchor your scrutiny):
- Part 1 (LD #586 SCHEMA_VOCAB_TOLERANT_FILTER_V1) ALREADY SHIPPED a cheap defensive read-side fix at Production/lib/severity_vocab.py. The migration in this spec is OPTIONAL CANONICALIZATION for clarity, not a correctness fix. The system already works on mixed vocab thanks to Part 1.
- The spec uses a dual-Opus debate format: each rule has Advocate vs Counter, with explicit resolution criteria and a verdict.
- Rule 1 (severity HIGH/CRITICAL → HARD, 320 rows) has Verdict: DEFER, lean Counter — execution NOT recommended unless Kim explicitly authorizes.

Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline) — v2 hardened anchored citations:
1. Confirm spec file exists; capture size + mtime.
2. shasum the spec file; capture digest.
3. Quote the first 25 non-blank lines of the spec verbatim with capture-line-range.
4. v2 ANCHORED COMPANION INTEGRITY: for each of (a) the cleanup report, (b) Production/lib/severity_vocab.py, (c) Production/scripts/governance_drift_check.py — locating the `from lib.severity_vocab import` block anchor, (d) HANDOFF_TEMPLATE_v2.md — capture mtime AND shasum AND quote the anchor's surrounding line block verbatim. 4 digests + 4 anchored quotes inline.
5. LD #586 row check: attempt Directus query for SCHEMA_VOCAB_TOLERANT_FILTER_V1. If unreachable, log "Directus unreachable — LD #586 verification deferred to Task F fallback rule".
6. Live-data sanity: confirm or refute the cleanup report's distinct-value counts (11 severity / 68 task_category / 17 scope_domain). If counts differ, emit the new counts inline.
If preflight 1-4 fails, HALT and report.

CONCISE→FULL ESCALATION RULE — v2 amendment (mandatory):

If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced":
- Could not read a referenced file (path missing, permission denied, mtime suggests stale cache).
- Could not reproduce an anchor (no header/snippet match in the actual file content).
- The spec section the question targets is missing or ambiguous.
- Your evidence is "I think" or "probably" rather than a quoted citation.
- You skipped the question to save tokens.

Documenting WHICH area was under-evidenced is REQUIRED in the full-mode output.

ANALYSIS REQUIREMENTS:

Every concern you raise MUST be in this format:
| # | Concern (one sentence) | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (file + anchored snippet quoted) | Suggested mitigation | Blocker (Y/N) |

"Severity" rubric:
- CRITICAL = ship-blocker; spec must not advance to any execution phase
- HIGH = revise spec before any phase runs
- MED = address in v2 amendment OR document as known-deferred
- LOW = nice-to-have, optional

"Blocker" rubric:
- Y = Kim should NOT authorize Phase 0 (dry-run) until this is resolved
- N = informational; documented and proceed acceptable

REQUIRED ANALYSIS TASKS:

A. RULE 1 RESOLUTION CRITERIA SOUNDNESS — v2 NUMERIC THRESHOLD
   - The spec verdict is "DEFER, lean Counter" because Part 1 already solved correctness. Independently verify by querying or grepping: does ANY tool, dashboard, query, or SQL pattern in the codebase actually require severity == "HARD" string match (not rank-based, not is_high_severity()-based)?
   - **NUMERIC THRESHOLD (v2):** if you find 2 or more code paths that depend on canonical-only severity values (e.g. SQL `WHERE severity = 'HARD'` strings, dashboard filter strings, tool config files), verdict MUST be AMEND_V2 — Rule 1's Counter verdict is wrong because correctness DOES depend on canonicalization. Show the 2+ paths with file + anchored quote.
   - If you find 0 or 1 such paths, the spec's Counter-leaning verdict is defensible.

B. LOSSY-COLLAPSE SAFETY (Rule 1) — v2 NUMERIC THRESHOLD
   - The spec claims "every CRITICAL row functionally is a HARD row" based on a 30-LD sample. Independently spot-check: pull 5 random CRITICAL rows from Directus (decision_key + decision_text). Are they functionally HARD-equivalent? Or do any preserve a "this is a strict prohibition, not a standard hard rule" semantic that would be lost?
   - **NUMERIC THRESHOLD (v2):** if 2 or more of your 5 sampled CRITICAL rows preserve a meaningful CRITICAL-vs-HARD distinction (e.g., refuse-to-execute semantics, system-shutdown triggers, billing-impact rules), verdict MUST be AMEND_V2 — collapse is too lossy. If 0-1 do, the spec's collapse-is-safe claim is defensible.
   - Document each sampled row by id + decision_key + verdict (preserved-distinction vs functionally-HARD).

C. SCHEMA EXTENSION RISK (Rule 3a) — descriptive, no threshold
   - The spec proposes adding 7 task_category values: app_architecture, infrastructure, security, governance, production_tool_ui, data_model, visual_production. Are any of these (a) confusable with each other, (b) confusable with existing canonical values, (c) too narrow to deserve their own bucket?
   - Specifically flag: `infrastructure` (task_category) collides namewise with `infra` (scope_domain). The spec's mitigation is "keep names distinct" but acknowledges the collision risk.

D. ROLLBACK PATH COMPLETENESS — v2 NUMERIC THRESHOLD
   - §8 lists per-phase rollback. Walk Phase 5 (severity HARD migration) rollback specifically: if Phase 5 PATCHes 320 rows and is then rolled back, can the rollback restore the EXACT pre-migration state including the CRITICAL vs HIGH distinction?
   - **NUMERIC THRESHOLD (v2):** if the rollback path's data source (snapshot file, activity-log per-row entries, or Directus revision history) cannot reconstruct the original CRITICAL/HIGH split for ≥95% of touched rows, verdict MUST be AMEND_V2 on §8 — Phase 5 should not run without bulletproof rollback.
   - If the snapshot mechanism described in §6 Gate 7 is enabled (recommended), is it sufficient? Does it capture every column that might be referenced post-rollback?

E. CONCURRENCY / ATOMICITY — descriptive
   - §9 mentions a lockfile to prevent concurrent runs. Is the lockfile location (~/.claude/mindfulnest-cache/) appropriate for a migration that affects shared Directus state? What happens if the migration script crashes mid-batch?
   - Is the per-row PATCH+read-back pattern atomic with respect to concurrent reads (e.g., a dashboard refreshing during migration)?

F. DIRECTUS UNREACHABLE FALLBACK — descriptive (per Step 0 #5)
   - The spec assumes Directus is reachable throughout. If Directus is unreachable mid-migration, what is the recovery path? Does the script log the last-confirmed row id so a resume can pick up where it left off?

G. PER-ROW APPROVAL OVERHEAD — v2 NUMERIC THRESHOLD
   - §6 Gate 5 requires Kim approval after the first 5 PATCHes per phase. With 5 phases (1+2+3+4+5), that's at least 5 Kim-approval-points spread across the session — likely a multi-day cadence.
   - **NUMERIC THRESHOLD (v2):** if your estimate of total Kim attention required across all 5 phases (including dry-run review + per-phase first-5 review + final audit review) exceeds 4 hours of focused time, verdict MUST be AMEND_V2 on §5 — the migration is too operationally expensive vs the cleanup-report's "10 hours focused work" estimate.
   - If your estimate is ≤4 hours, the multi-session cadence is defensible.

H. RISKS NOT IN §7
   - §7 lists 8 risks. Find at least 2 risks not enumerated. Examples to seed (not exhaustive — find your own): downstream consumer (e.g., a Kim-authored dashboard or external Directus integration) that pins to legacy severity values and would silently break post-migration; activity-log table volume blowup affecting other queries; script timeout on a large batch when Doppler refreshes mid-PATCH.

I. INTEGRATION WITH PART 1 (LD #586)
   - LD #586's helper module is the canonical read-side filter today. Post-migration, is the helper still needed? Or can it be deprecated once all rows are canonical?
   - **NUMERIC THRESHOLD (v2):** if the helper would still be needed post-migration (e.g., because some rows MUST stay legacy per Kim's Rule-1 DEFER decision), verdict MUST INCLUDE a note that LD #586 is permanent, not transitional. If the helper is purely transitional (all rows would go canonical), the spec should say so explicitly.

VERDICT FORMAT (mandatory):

Emit a single line at the end of your response:

VERDICT: [AUTHORIZE_PHASE_0 | AMEND_V2 | BLOCK]

- AUTHORIZE_PHASE_0 — spec is sound; Kim can authorize the dry-run phase.
- AMEND_V2 — spec needs a v2 revision before Phase 0; specify exactly which sections need amendment.
- BLOCK — spec is fundamentally flawed; do not advance.

Then a one-paragraph rationale citing the analysis tasks that drove the verdict.
```

---

## Step 3 — Capture Cursor's response

After Cursor returns its analysis, save the verbatim response to:

`Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md`

If verdict is `AUTHORIZE_PHASE_0`, proceed to scheduling the migration session.

If verdict is `AMEND_V2`, author `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` addressing each Cursor finding; preserve v1 as historical baseline.

If verdict is `BLOCK`, surface to Kim for re-scoping.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST.
- **Multipass:** re-Read every file after edit.
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) are always active — fire on any of their trigger conditions.
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior (input variation → output variation).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 explicit (HARD rule, v2):** "All filesystem-touching commands MUST use absolute paths anchored to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Do NOT operate inside `.claude/worktrees/` subdirectories. Verify paths with `ls -la <absolute-path>` before edits."
- **Anchored citation (v2):** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (v2, applicable):** "If any required section cannot be evidenced, full mode is mandatory." (Cursor review handoff supports concise mode if no blockers; full mode mandatory under any of the 5 trigger conditions.)
- **Numeric AMEND_V2 thresholds (v2, applicable):** every analysis task asking "is X acceptable?" includes "if X > Y, verdict MUST be AMEND_V2." (Tasks A/B/D/G/I have explicit numeric thresholds; Tasks C/E/F/H are descriptive-only and document N/A.)

---

## Final report — required structure

Path: `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_REPORT_20260508.md`

Required sections:

1. **HALT gate scan results** — per-gate state at session start (MET / NOT MET / N/A) with evidence cited.
2. **Cursor verdict verbatim** — Cursor's full response copy-pasted.
3. **Per-task summary** — A through I, each with verdict + key evidence.
4. **Confidence tags per Rule 24.**
5. **Self-classification** — REVIEW (this is a review session, not implementation).
6. **Limitations** — what Cursor couldn't review (e.g., Directus offline → Task F fallback fired).
7. **Cross-skill drift** — does Cursor's verdict require updates to mn-context, dashboard-gate, tech-spec, etc.?
8. **Next-step recommendation** — schedule Phase 0 / author v2 / surface to Kim.

---

## Cross-references

- `.claude/skills/zero-error-qa/SKILL.md` DS-26 + DS-27 — agent-side enforcement of HALT-gate + absolute-path discipline.
- LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` — locked-decision authority for v1 HALT gates.
- LD `WORKTREE_CONFUSION_PREVENTION_V1` — locked-decision authority for v2 absolute-path discipline.
- LD `SCHEMA_VOCAB_TOLERANT_FILTER_V1` (#586) — Part 1 standing rule.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate.
- LD-232 (autonomous-mode pattern) — boundary this template names.
- CLAUDE.md Rule 35 — read-back-after-write.
