# Handoff v2 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v2

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md`

**Supersedes:** `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` (preserved as historical baseline; do NOT edit in place).

**v1 → v2 driver:** Cursor returned AMEND_V2 verdicts on the v1 spec AND v1 handoff. The spec v2 (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md`) addresses 4 amendments to the spec itself; THIS handoff v2 addresses 3 amendments to the handoff. See §0.1 changelog for verbatim resolution per amendment.

**Companion docs:**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — spec v2 (under review).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — spec v1 historical baseline (cited in the changelog only).
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates the spec.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive fix that has already shipped (LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1`).
- `Production/scripts/governance_drift_check.py` — Part 1 vocab-tolerant consumer.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical) — handoff structure mandate (this handoff conforms).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in Hard rules.

This handoff is **v2 format** — incorporates the 4 v2-template hardening rules (anchored citation discipline + concise→full escalation + numeric AMEND_V2 thresholds + dual-canonical-roots filesystem discipline) PLUS the 3 handoff-side amendments Cursor returned on the v1 review handoff.

---

## §0.1 — v2 Changelog (verbatim resolution per Cursor handoff amendment)

Cursor's AMEND_V2 verdict on the v1 handoff returned 3 amendments (2 HIGH, 1 MED). Each is reproduced verbatim with the resolution. v1 sections that needed material change are listed under "Sections changed".

| # | Severity | Cursor amendment (verbatim) | Resolution applied in v2 | Sections changed |
|---|---|---|---|---|
| 1 | HIGH | Line-anchoring inconsistency: keep first-25-line quote (good stale check) BUT make all companion requirements anchor-by-header/snippet only (no fixed line numbers). | Step 0 preflight #3 retains the spec's first-25-line quote (good stale-cache detector) but every COMPANION-file integrity check switches to anchor-by-header/snippet only — no "quote line N" requirements. The companion-file table column "Anchored check" replaces any line-number requirements with header/snippet anchors. Step 2 prompt block aligned. | Step 0, Step 2 prompt |
| 2 | HIGH | Absolute-path mismatch: update hard rule from "Dropbox-root-only" to "canonical roots {Dropbox, Projects}; no worktrees unless explicitly authorized." | Hard rules section updated to dual-canonical-roots wording verbatim from `HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2). DS-27 reference updated to v2 refactor. Project-root naming in Step 1 updated. Step 2 prompt's hard-rule restatement updated. | Hard rules, Step 1, Step 2 prompt |
| 3 | MED | Descriptive-task escalation: Tasks C/E/F/H are descriptive-only; add clause: "unresolved descriptive risks at MED+ force full mode and explicit 'authorize with risk acceptance' statement." | Step 2 prompt's CONCISE→FULL ESCALATION RULE block expanded with a 6th trigger clause naming descriptive Tasks C/E/F/H: any unresolved descriptive risk at MED severity or higher forces full mode AND requires the reviewer to emit a verbatim "authorize with risk acceptance" statement before any AUTHORIZE_PHASE_0 verdict. | Step 2 prompt CONCISE→FULL ESCALATION block, Step 2 prompt VERDICT FORMAT block, Hard rules |

**v1 vs v2 surface area:** v2 adds ~120 lines (changelog + restated path-discipline blocks + new descriptive-task escalation clause). All v1 content preserved (no deletions); v2 additions are clearly labeled `(v2)` or `(NEW v2)` inline.

---

## HALT gates (v1 preserved verbatim)

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Step 2 begins)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|------------------|-----------------|-------------|
| 1 | Has the spec file at `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` been authored AND committed to disk? | `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md"` | File exists, size > 30 KB (v2 is larger than v1), mtime is today | Write `HALTED_AWAITING_AUTHORIZATION` row citing this gate; surface to Kim |
| 2 | Has the cleanup report (`SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`) been read into context BEFORE critiquing the spec? | Quote anchor: locate `## 0. Confirmed environment baseline` header in the report; capture line range; quote the severity distribution table | Reviewer emits the table verbatim inline | HALT and report which anchor failed |
| 3 | Has Part 1 (LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1`) actually shipped per the spec's claim? | Directus query: `prod_locked_decisions` row where `decision_key = SCHEMA_VOCAB_TOLERANT_FILTER_V1` AND `status = active` | Row exists, severity=HARD, date_locked=2026-05-08 | Note "LD #586 not found — Part 1 may not have shipped"; AMEND_V2 verdict on §1 |
| 4 | (v2 NEW) Has spec v2's path discipline §3.0 been read into context? | Quote anchor: locate `### §3.0 — Path discipline (v2 dual-canonical, NEW)` header in the v2 spec; capture surrounding paragraph verbatim. | Reviewer emits the dual-canonical-roots paragraph inline | HALT and report which anchor failed |
| 5 | (v2 NEW) Has spec v2's `PHASE_5_ENABLED` feature flag (§3.1 v2 amendment) been read into context? | Quote anchor: locate `#### Rule 1 v2 amendment — PHASE_5_ENABLED feature flag` header in the v2 spec; capture the Layer-1 / Layer-2 / Layer-3 narrative inline | Reviewer emits the three-layer block | HALT and report which anchor failed |

---

## Step 0 — Preflight (do FIRST, before any analysis) — v2 anchor-by-header/snippet only

**v2 amendment #1 (HIGH) applied:** the spec file's first-25-line stale-cache check is preserved. Every COMPANION file's integrity check now uses anchor-by-header/snippet ONLY — no fixed line numbers anywhere in this preflight.

Before reading or critiquing the spec, run these checks and emit the results inline at the top of your response:

1. **Spec file exists:** run `ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md"` — capture size and mtime.
2. **Spec hash:** run `shasum "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md"` — capture hex digest.
3. **Anchored quote of spec header (PRESERVED v1):** locate the `# Schema Vocab Migration — Tech Spec v2` header anchor and quote the first 25 non-blank lines as proof you read the actual file (not a stale or fabricated copy). Capture the line range these 25 lines occupy. (This first-25-line quote is the ONLY line-number-aware preflight step in v2; it's preserved as a stale-cache detector. All other anchored checks below use header/snippet only.)
4. **Companion-file integrity checks (v2 anchored discipline — header/snippet ONLY, no line numbers):** for each of the 5 companion files below, run `ls -la` AND `shasum` AND quote the named anchor by HEADER or SNIPPET ONLY. Existence-only is no longer sufficient. Line-number-based quotes are FORBIDDEN at this step.

   | Companion file | Anchored check (header/snippet only — no line numbers) |
   |----------------|--------------------------------------------------------|
   | `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` | `ls -la` + `shasum` + locate header anchor `## 0. Confirmed environment baseline` and quote the surrounding paragraph verbatim |
   | `Production/lib/severity_vocab.py` | `ls -la` + `shasum` + locate the `def severity_rank(` function anchor and quote its docstring verbatim |
   | `Production/scripts/governance_drift_check.py` | `ls -la` + `shasum` + locate the `from lib.severity_vocab import` import block by snippet anchor; quote the surrounding import block verbatim |
   | `Production/docs/HANDOFF_TEMPLATE_v2.md` | `ls -la` + `shasum` + locate header anchor `## v2 NEW — Absolute-path filesystem discipline (HARD rule, all handoffs) — refactored 2026-05-08 v2 dual-canonical` and quote the dual-canonical mandate paragraph verbatim |
   | `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` (historical baseline) | `ls -la` + `shasum` + locate header anchor `# Schema Vocab Migration — Tech Spec v1` and confirm it differs from v2's header — proof that v1 is preserved separately |

   Acceptance criterion: 5 shasum digests + 5 anchored quotes (header/snippet) emitted inline. If any digest cannot be computed OR any anchor cannot be located by header/snippet, **HALT and report which companion failed**. Existence-only does NOT pass v2 preflight. Line-number-based quotes do NOT pass v2 preflight.

5. **LD #586 row check:** attempt to query Directus `prod_locked_decisions` for the row where `decision_key = SCHEMA_VOCAB_TOLERANT_FILTER_V1`. If Directus is unreachable, record "Directus unreachable — LD #586 verification deferred to Analysis Task F fallback rule" and proceed; do NOT HALT for this single check.

6. **(v2 NEW) LD #584 amendment check:** attempt to query Directus `prod_locked_decisions` for row id=584 (`WORKTREE_CONFUSION_PREVENTION_V1`); confirm `notes` field contains the literal substring "2026-05-08 amendment: DS-27 refactored from Dropbox-only to dual-canonical-roots {Dropbox, Projects}". If found, the dual-canonical authority is in place; if not found, AMEND_V2 verdict on the Hard rules section (the path-discipline rule's authority is missing).

7. **Live data baseline confirmation:** independently verify (via Directus query OR by reading the cleanup report's §0 verbatim) that the dataset still has 11 distinct severity values + 68 task_category values + 17 scope_domain values, OR document the new live counts inline. The migration mappings in the spec assume the report's snapshot baseline.

If any preflight check (1-4) fails, **HALT and report**. Do not proceed to Step 1.

---

## Step 1 — Open the project in Cursor (v2 dual-canonical)

**v2 amendment #2 (HIGH) applied:** Project root naming explicitly references the dual-canonical-roots policy.

This task operates on the Mindfulnest project (Dropbox-anchored canonical root). The other canonical root (`/Users/kimberlysmith/Projects/`) is NOT in scope for this review.

Project root (absolute path, no `cd` into worktrees, no operations outside the named canonical root):

`/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`

Open `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` in the editor. Open Cursor Composer or chat.

If your editor or shell is anchored to a worktree (`.claude/worktrees/<name>/`) under EITHER canonical root, surface this fact inline before proceeding. Worktree operation requires explicit authorization in this handoff (none is granted here).

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md (v2 — supersedes v1). It proposes a 4-rule mass migration of the prod_locked_decisions Directus collection's severity / task_category / scope_domain columns into canonical state. The spec is DESIGN ONLY; execution is gated on Kim's per-rule approval (9 gates in §6 — gate #9 is v2 NEW, the PHASE_5_ENABLED feature flag).

Background context (informational only — do NOT let this anchor your scrutiny):
- Part 1 (LD #586 SCHEMA_VOCAB_TOLERANT_FILTER_V1) ALREADY SHIPPED a cheap defensive read-side fix at Production/lib/severity_vocab.py. The migration in this spec is OPTIONAL CANONICALIZATION for clarity, not a correctness fix. The system already works on mixed vocab thanks to Part 1.
- The spec uses a dual-Opus debate format: each rule has Advocate vs Counter, with explicit resolution criteria and a verdict.
- Rule 1 (severity HIGH/CRITICAL → HARD, 320 rows) has Verdict: DEFER, lean Counter — execution NOT recommended unless Kim explicitly authorizes via the v2 three-layer feature-flag gate (operational doctrine + script-level guard + procedural Gate #9).
- Spec v2 was authored after Cursor returned AMEND_V2 on v1; v2 addresses 4 spec amendments. THIS HANDOFF v2 was authored after Cursor returned AMEND_V2 on the v1 handoff; this handoff v2 addresses 3 handoff amendments.

Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline) — v2 hardened anchored citations (HEADER/SNIPPET ONLY, no fixed line numbers in companion checks):
1. Confirm spec file exists; capture size + mtime.
2. shasum the spec file; capture digest.
3. Quote the first 25 non-blank lines of the spec verbatim with capture-line-range. (This is the ONLY line-number-aware step.)
4. v2 ANCHORED COMPANION INTEGRITY (header/snippet ONLY, no line numbers): for each of (a) the cleanup report — anchor `## 0. Confirmed environment baseline`, (b) Production/lib/severity_vocab.py — anchor function `def severity_rank(`, (c) Production/scripts/governance_drift_check.py — anchor `from lib.severity_vocab import` snippet, (d) HANDOFF_TEMPLATE_v2.md — anchor `## v2 NEW — Absolute-path filesystem discipline (HARD rule, all handoffs) — refactored 2026-05-08 v2 dual-canonical`, (e) the v1 spec historical baseline — anchor `# Schema Vocab Migration — Tech Spec v1` — capture mtime AND shasum AND quote the named anchor's surrounding paragraph or block verbatim. 5 digests + 5 anchored quotes inline.
5. LD #586 row check: attempt Directus query for SCHEMA_VOCAB_TOLERANT_FILTER_V1. If unreachable, log "Directus unreachable — LD #586 verification deferred to Task F fallback rule".
6. LD #584 amendment check (v2 NEW): query id=584 WORKTREE_CONFUSION_PREVENTION_V1; confirm `notes` contains "2026-05-08 amendment: DS-27 refactored from Dropbox-only to dual-canonical-roots {Dropbox, Projects}". If absent, AMEND_V2 the Hard rules section.
7. Live-data sanity: confirm or refute the cleanup report's distinct-value counts (11 severity / 68 task_category / 17 scope_domain). If counts differ, emit the new counts inline.
If preflight 1-4 fails, HALT and report.

CONCISE→FULL ESCALATION RULE — v2 amendment (mandatory) + v2 amendment #3 (NEW: descriptive-task escalation):

If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced":
- Could not read a referenced file (path missing, permission denied, mtime suggests stale cache).
- Could not reproduce an anchor (no header/snippet match in the actual file content).
- The spec section the question targets is missing or ambiguous.
- Your evidence is "I think" or "probably" rather than a quoted citation.
- You skipped the question to save tokens.
- (NEW v2 amendment #3 — descriptive-task escalation): ANY descriptive-only Analysis Task (Tasks C, E, F, H) whose finding raises a risk at severity MED or higher forces full mode AND requires the reviewer to emit a verbatim "AUTHORIZE WITH RISK ACCEPTANCE: <one-paragraph statement of which descriptive risk is being accepted, why, and Kim's mitigation responsibility>" statement before any AUTHORIZE_PHASE_0 verdict may be issued. Without this verbatim statement, the verdict CANNOT be AUTHORIZE_PHASE_0; it MUST be AMEND_V2 or BLOCK. This closes the path where Cursor would otherwise have flagged a MED descriptive risk and still authorized.

Documenting WHICH area was under-evidenced is REQUIRED in the full-mode output.

ANALYSIS REQUIREMENTS:

Every concern you raise MUST be in this format:
| # | Concern (one sentence) | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (file + anchored snippet quoted) | Suggested mitigation | Blocker (Y/N) |

"Severity" rubric:
- CRITICAL = ship-blocker; spec must not advance to any execution phase
- HIGH = revise spec before any phase runs
- MED = address in v3 amendment OR document as known-deferred (and triggers descriptive-task escalation if from Tasks C/E/F/H)
- LOW = nice-to-have, optional

"Blocker" rubric:
- Y = Kim should NOT authorize Phase 0 (dry-run) until this is resolved
- N = informational; documented and proceed acceptable

REQUIRED ANALYSIS TASKS:

A. RULE 1 RESOLUTION CRITERIA SOUNDNESS — v2 NUMERIC THRESHOLD
   - The spec verdict is "DEFER, lean Counter" because Part 1 already solved correctness. Spec v2 additionally gates Phase 5 behind a three-layer PHASE_5_ENABLED feature flag (§3.1 v2). Independently verify by querying or grepping: does ANY tool, dashboard, query, or SQL pattern in the codebase actually require severity == "HARD" string match (not rank-based, not is_high_severity()-based)?
   - **NUMERIC THRESHOLD (v2):** if you find 2 or more code paths that depend on canonical-only severity values (e.g. SQL `WHERE severity = 'HARD'` strings, dashboard filter strings, tool config files), verdict MUST be AMEND_V2 — Rule 1's Counter verdict is wrong because correctness DOES depend on canonicalization. Show the 2+ paths with file + anchored quote.
   - If you find 0 or 1 such paths, the spec's Counter-leaning verdict is defensible AND the v2 feature-flag gate is the right mechanical encoding.

B. LOSSY-COLLAPSE SAFETY (Rule 1) — v2 NUMERIC THRESHOLD
   - The spec claims "every CRITICAL row functionally is a HARD row" based on a 30-LD sample. Spec v2 ties Phase 5 rollback to the snapshot's three-field integrity check (§4 Phase 0 v2 + §8 Phase 5 rollback). Independently spot-check: pull 5 random CRITICAL rows from Directus (decision_key + decision_text). Are they functionally HARD-equivalent? Or do any preserve a "this is a strict prohibition, not a standard hard rule" semantic that would be lost?
   - **NUMERIC THRESHOLD (v2):** if 2 or more of your 5 sampled CRITICAL rows preserve a meaningful CRITICAL-vs-HARD distinction (e.g., refuse-to-execute semantics, system-shutdown triggers, billing-impact rules), verdict MUST be AMEND_V2 — collapse is too lossy. If 0-1 do, the spec's collapse-is-safe claim is defensible AND the v2 snapshot+rollback path adequately mitigates the residual risk.
   - Document each sampled row by id + decision_key + verdict (preserved-distinction vs functionally-HARD).

C. SCHEMA EXTENSION RISK (Rule 3a) — descriptive (v2 amendment #3 escalation applies)
   - The spec proposes adding 7 task_category values: app_architecture, infrastructure, security, governance, production_tool_ui, data_model, visual_production. Are any of these (a) confusable with each other, (b) confusable with existing canonical values, (c) too narrow to deserve their own bucket?
   - Specifically flag: `infrastructure` (task_category) collides namewise with `infra` (scope_domain). The spec's mitigation is "keep names distinct" but acknowledges the collision risk.
   - **v2 amendment #3 escalation:** if any of (a)/(b)/(c) yields a MED or higher risk, full-mode + "AUTHORIZE WITH RISK ACCEPTANCE" statement required; AUTHORIZE_PHASE_0 forbidden without it.

D. ROLLBACK PATH COMPLETENESS — v2 NUMERIC THRESHOLD (extended for v2 snapshot schema)
   - §8 lists per-phase rollback. Walk Phase 5 (severity HARD migration) rollback specifically: if Phase 5 PATCHes 320 rows and is then rolled back, can the rollback restore the EXACT pre-migration state including the CRITICAL vs HIGH distinction?
   - **v2 expansion:** spec v2 §4 Phase 0 v2 + §8 Phase 5 rollback tie the rollback to a snapshot file with three required metadata fields (`row_count`, `id_uniqueness`, `all_touched_ids_present`). Independently verify the metadata schema is sufficient: does it cover every column that might be referenced post-rollback?
   - **NUMERIC THRESHOLD (v2):** if the rollback path's data source (snapshot file, activity-log per-row entries, or Directus revision history) cannot reconstruct the original CRITICAL/HIGH split for ≥95% of touched rows, verdict MUST be AMEND_V2 on §8 — Phase 5 should not run without bulletproof rollback.
   - If the snapshot mechanism described in §6 Gate 7 is enabled (REQUIRED in v2 for Phase 5), is it sufficient? Does it capture every column that might be referenced post-rollback?

E. CONCURRENCY / ATOMICITY — descriptive (v2 amendment #3 escalation applies)
   - §9 mentions a lockfile to prevent concurrent runs. Is the lockfile location (~/.claude/mindfulnest-cache/) appropriate for a migration that affects shared Directus state? What happens if the migration script crashes mid-batch?
   - Is the per-row PATCH+read-back pattern atomic with respect to concurrent reads (e.g., a dashboard refreshing during migration)?
   - **v2 amendment #3 escalation:** if any concurrency/atomicity finding reaches MED or higher severity, full-mode + "AUTHORIZE WITH RISK ACCEPTANCE" statement required.

F. DIRECTUS UNREACHABLE FALLBACK — descriptive (per Step 0 #5; v2 amendment #3 escalation applies)
   - The spec assumes Directus is reachable throughout. If Directus is unreachable mid-migration, what is the recovery path? Does the script log the last-confirmed row id so a resume can pick up where it left off?
   - **v2 amendment #3 escalation:** if any unreachable-fallback finding reaches MED or higher severity, full-mode + "AUTHORIZE WITH RISK ACCEPTANCE" statement required.

G. PER-ROW APPROVAL OVERHEAD — v2 NUMERIC THRESHOLD (recalibrated for v2 §9 cost split)
   - §6 Gate 5 requires Kim approval after the first 5 PATCHes per phase. With 5 phases (1+2+3+4+5), that's at least 5 Kim-approval-points spread across the session — likely a multi-day cadence. Spec v2 §9 explicitly splits the cost model into machine time + human review time + combined.
   - **NUMERIC THRESHOLD (v2):** if your estimate of total Kim attention required across all 5 phases (including dry-run review + per-phase first-5 review + final audit review + v2 Gate #9 feature-flag work) exceeds the spec v2 §9.2 figure of ~7.5 hours focused human time by more than 25% (i.e., your estimate exceeds ~9.4 hours), verdict MUST be AMEND_V2 on §9 — the cost model is inaccurate. If your estimate is within 25% of the spec's figure, the v2 cost split is defensible.
   - Reference baseline: spec v2 §9.3 cites ~10 hours combined planning baseline (~7.5 hr human + ~25 min machine + buffer).

H. RISKS NOT IN §7 — descriptive (v2 amendment #3 escalation applies)
   - §7 lists 9 risks (v1 had 8; v2 added the PHASE_5_ENABLED bypass risk). Find at least 2 risks not enumerated. Examples to seed (not exhaustive — find your own): downstream consumer (e.g., a Kim-authored dashboard or external Directus integration) that pins to legacy severity values and would silently break post-migration; activity-log table volume blowup affecting other queries; script timeout on a large batch when Doppler refreshes mid-PATCH.
   - **v2 amendment #3 escalation:** if any newly-found risk reaches MED or higher severity, full-mode + "AUTHORIZE WITH RISK ACCEPTANCE" statement required.

I. INTEGRATION WITH PART 1 (LD #586) — v2 NUMERIC THRESHOLD
   - LD #586's helper module is the canonical read-side filter today. Post-migration, is the helper still needed? Or can it be deprecated once all rows are canonical?
   - **NUMERIC THRESHOLD (v2):** if the helper would still be needed post-migration (e.g., because some rows MUST stay legacy per Kim's Rule-1 DEFER decision), verdict MUST INCLUDE a note that LD #586 is permanent, not transitional. If the helper is purely transitional (all rows would go canonical), the spec should say so explicitly.

VERDICT FORMAT (mandatory) — v2 amendment #3 expanded:

Emit a single line at the end of your response:

VERDICT: [AUTHORIZE_PHASE_0 | AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE | AMEND_V2 | BLOCK]

- AUTHORIZE_PHASE_0 — spec is sound; Kim can authorize the dry-run phase. Permitted ONLY if NO descriptive-task finding (C/E/F/H) reaches MED or higher.
- AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE (v2 NEW) — spec is sound BUT one or more descriptive-task findings reach MED+; reviewer has emitted the verbatim "AUTHORIZE WITH RISK ACCEPTANCE" statement (paragraph in the body of the response) and Kim authorizes Phase 0 with explicit acknowledgment of the named risks.
- AMEND_V2 — spec needs a v3 revision before Phase 0; specify exactly which sections need amendment.
- BLOCK — spec is fundamentally flawed; do not advance.

Then a one-paragraph rationale citing the analysis tasks that drove the verdict. If the verdict is AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE, the rationale MUST quote the verbatim "AUTHORIZE WITH RISK ACCEPTANCE: ..." statement at the top of the rationale paragraph.
```

---

## Step 3 — Capture Cursor's response

After Cursor returns its analysis, save the verbatim response to:

`Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md`

If verdict is `AUTHORIZE_PHASE_0` or `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE`, proceed to scheduling the migration session.

If verdict is `AMEND_V2`, author `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` addressing each Cursor finding; preserve v2 as historical baseline.

If verdict is `BLOCK`, surface to Kim for re-scoping.

---

## Hard rules (v2 dual-canonical refactor)

**v2 amendment #2 (HIGH) applied:** Hard rule path discipline updated from Dropbox-only to dual-canonical-roots, verbatim from `HANDOFF_TEMPLATE_v2.md` refactored block.

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST.
- **Multipass:** re-Read every file after edit.
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19** (Standing Escape Hatches) and **DS-26** (Gate-Check Discipline) are always active — fire on any of their trigger conditions.
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior (input variation → output variation).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 explicit (HARD rule, v2 dual-canonical):** "All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots require explicit Kim authorization." (Authority: LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` amended 2026-05-08 v2 dual-canonical; SKILL.md DS-27 v2 refactor; HANDOFF_TEMPLATE_v2.md v2 refactor.)
- **Anchored citation (v2):** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone. EXCEPTION: the spec's first-25-line quote at Step 0 #3 is preserved as a stale-cache detector and is the only line-number-aware step.
- **Concise→full escalation (v2):** "If any required section cannot be evidenced, full mode is mandatory." (Cursor review handoff supports concise mode if no blockers; full mode mandatory under any of the 6 trigger conditions.)
- **(v2 amendment #3 NEW) Descriptive-task escalation:** "Tasks C, E, F, H are descriptive-only. Any unresolved descriptive risk at MED severity or higher forces full mode AND requires the reviewer to emit a verbatim 'AUTHORIZE WITH RISK ACCEPTANCE: <statement>' before any AUTHORIZE_PHASE_0 verdict may be issued. Without the verbatim statement, the verdict path is AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE (with statement) OR AMEND_V2 OR BLOCK."
- **Numeric AMEND_V2 thresholds (v2):** every analysis task asking "is X acceptable?" includes "if X > Y, verdict MUST be AMEND_V2." (Tasks A/B/D/G/I have explicit numeric thresholds; Tasks C/E/F/H are descriptive-only and route through the descriptive-task escalation clause above.)

---

## Final report — required structure (v2 expanded)

Path: `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_REPORT_20260508_v2.md`

Required sections:

1. **HALT gate scan results** — per-gate state at session start (MET / NOT MET / N/A) with evidence cited. (5 gates in v2; new gates 4-5 cite the v2 spec anchors.)
2. **Cursor verdict verbatim** — Cursor's full response copy-pasted.
3. **Per-task summary** — A through I, each with verdict + key evidence + (NEW v2) "is this a descriptive-task escalation?" flag for tasks C/E/F/H.
4. **(NEW v2) Descriptive-task escalation summary** — for any C/E/F/H task at MED or higher severity, the verbatim "AUTHORIZE WITH RISK ACCEPTANCE" statement OR a note that the verdict was AMEND_V2/BLOCK instead.
5. **Confidence tags per Rule 24.**
6. **Self-classification** — REVIEW (this is a review session, not implementation).
7. **Limitations** — what Cursor couldn't review (e.g., Directus offline → Task F fallback fired).
8. **Cross-skill drift** — does Cursor's verdict require updates to mn-context, dashboard-gate, tech-spec, etc.? (NEW v2: also note whether DS-27 or HANDOFF_TEMPLATE_v2 require further amendments.)
9. **Next-step recommendation** — schedule Phase 0 / author v3 / surface to Kim.

---

## Cross-references

- `.claude/skills/zero-error-qa/SKILL.md` DS-26 + DS-27 (v2 refactor 2026-05-08 dual-canonical) — agent-side enforcement of HALT-gate + dual-canonical absolute-path discipline.
- LD `GATE_CHECK_DISCIPLINE_NO_AUTONOMOUS_BYPASS_V1` — locked-decision authority for v1 HALT gates.
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — locked-decision authority for v2 dual-canonical absolute-path discipline.
- LD `SCHEMA_VOCAB_TOLERANT_FILTER_V1` (#586) — Part 1 standing rule.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical) — handoff structure mandate.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` — v1 historical baseline (preserved, not edited in place).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — spec v2 (under review).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — spec v1 historical baseline.
- `Production/docs/DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_REPORT_20260508.md` — final proof report for the bundled DS-27 dual-path refactor + spec v2 + this handoff v2.
- LD-232 (autonomous-mode pattern) — boundary this template names.
- CLAUDE.md Rule 35 — read-back-after-write.

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft pairing Cursor cross-review to spec v1. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor handoff AMEND_V2 amendments applied: (1) HIGH line-anchoring inconsistency resolved (companion checks anchor-by-header/snippet only; spec's first-25-line quote preserved as stale-cache detector); (2) HIGH absolute-path mismatch resolved (Hard rules + Step 1 + Step 2 prompt updated to dual-canonical-roots); (3) MED descriptive-task escalation added (Tasks C/E/F/H at MED+ force full mode + verbatim "AUTHORIZE WITH RISK ACCEPTANCE" statement gate before AUTHORIZE_PHASE_0). v1 preserved as historical baseline. Author: Claude Opus 4.7 (1M context).
