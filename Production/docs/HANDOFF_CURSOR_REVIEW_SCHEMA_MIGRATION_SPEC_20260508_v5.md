# Handoff v5 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v5

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` (38,742 bytes; sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`).

**Supersedes:** `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` (preserved as historical baseline; do NOT edit in place). v3 handoff covered v3 spec; that review returned `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` earlier today. v5 is a SURGICAL 2-defect correction over v4 (which itself was a surgical 1-defect correction over v3). v3 design surface remains authorized; this handoff narrows Cursor's scope to v5's surgical changes ONLY.

**v3 → v4 → v5 driver:**
- **v4 (LD-593):** v3 §9.4 mandated `severity=CRITICAL` (uppercase) on the `prod_blockers` mutex POST/PATCH; live `prod_blockers.severity` enum is lowercase-only (`critical`/`high`/`medium`/`low`). v4 case-folded severity to lowercase. Returns HTTP 500 if uppercase persists in script.
- **v5 (LD-595):** v3+v4 §9.4 example bodies still referenced fields `details` (acquisition POST + stale-mutex cleanup parsing) and `resolution_notes` (release PATCH) — neither exists on live `prod_blockers` (8 fields total: `id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`; live-probed 2026-05-08). v5 corrects: acquisition POST encodes `host`/`pid`/`started_at`/`script_version` inside `description` as `STRUCTURED_DETAILS_JSON:` + JSON literal; release PATCH appends to `description`; stale-mutex cleanup parses regex on `description`. Returns HTTP 400 unknown-field if non-fields persist. v4 explicitly deferred this fix to "future v5"; v5 is that correction.

**Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — Dropbox-rooted (canonical root #1; spec under review).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — Dropbox-rooted (canonical root #1; v4 historical baseline — v5's direct predecessor).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — Dropbox-rooted (canonical root #1; v3 historical baseline — design surface authorized AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — Dropbox-rooted (canonical root #1; prior review handoff — structural template for THIS handoff).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; §5 = ground truth for v5 fix; 8-field enumeration at lines 311-320, severity enum at 322-331, STRUCTURED_DETAILS_JSON pattern at 362-377).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1; implementation handoff; §6 prod_blockers schema gotchas added v2.1 anticipated v5; potentially needs v2.2 amendment per v5 §12 changelog).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; this handoff conforms to v2 template — anchored citations, concise→full escalation, numeric AMEND_V2 thresholds, dual-canonical absolute paths, companion path discipline).

---

## §0.1 — Why this v5 review exists

v3 spec received `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` from Cursor earlier today. v4 was authored as a self-discovered minimal amendment fixing severity case-fold (LD-593). v5 was authored as a SECOND self-discovered minimal amendment fixing field names (`details` / `resolution_notes` → `description`-embedded patterns) (LD-595). Both v4 and v5 are post-authorization touch-ups, NOT re-reviews.

v5 needs a TIGHT cross-review specifically on the §9.4 changes + §6 Gate 11.2 + §7 risk #14 because:
1. The fix changes runtime POST/PATCH bodies — a defect here re-blocks Phase 1+2+4+5 entry-guards.
2. The fix introduces a regex-based parser for stale-mutex cleanup; regex correctness on nested JSON is a known footgun.
3. The fix introduces a lint pattern (Gate 11.2) intended to catch future regressions; lint pattern soundness needs independent scrutiny.

The v3 design surface (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H lock_decision.py) is OUT OF SCOPE for this v5 review — Cursor already authorized it.

---

## §0.2 — What you DON'T need to do

- Do NOT re-review v3 design surface (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H). Already authorized via prior `AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE` verdict on v3.
- Do NOT review v4's severity case-fold (already locked under LD-593; v5 preserves it verbatim).
- Do NOT have Cursor edit the spec. Verdict-only.
- Do NOT have Cursor implement the migration. Implementation handoff is at `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md`; this handoff is review-only.
- Do NOT have Cursor sample CRITICAL rows from `prod_locked_decisions` (Task B sampling) — that was v3-scope; v5 is operational POST/PATCH body correction, not data sampling.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has spec v5 sha256 been confirmed match `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`? | `shasum -a 256` of v5 spec absolute path | Hash matches verbatim | HALT — author drift; surface to Kim |
| 2 | Has v5 §9.4 v5 callout block been read into context? | Quote anchor: locate `### §9.4 — Concurrency, lockfile, and remote mutex (v5 FIELD-NAME FIX over v4 — self-discovered defect; v4 deferred)` header in v5 spec; capture the `**Field-name fix (v5 NEW correction).**` paragraph inline | Reviewer emits the v5 callout block text (8-field enumeration + STRUCTURED_DETAILS_JSON encoding + LD-595 reference) | HALT and report which anchor failed |
| 3 | Has v5 §6 Gate 11.2 row been read into context? | Quote anchor: locate the row beginning `| 11.2 | **(v5 NEW — self-discovered defect; v4 deferred)** Mutex POST/PATCH field-name compliance:` in v5 §6; capture the gate text + Gate 11.2 verification artifact paragraph | Reviewer emits the Gate 11.2 row text + verification-artifact lint pattern | HALT and report which anchor failed |
| 4 | Has v5 §7 risk #14 row been read into context? | Quote anchor: locate the row beginning `| **(v5 NEW — #14)** Spec author or implementer copy-pastes v3/v4 example body containing a` in v5 §7; capture the full risk row | Reviewer emits the risk #14 row text (5-layer mitigation chain) | HALT and report which anchor failed |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` v5 spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md"
   ```
   Expected: file exists, size 38,742 bytes, mtime 2026-05-08.

2. **`shasum -a 256` v5 spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md"
   ```
   Expected output: `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Quote first 20 lines of v5 spec verbatim** (stale-cache detector). The first non-blank line MUST be `# Schema Vocab Migration — Tech Spec v5`. Capture lines 1-20 with line numbers.

4. **Companion-file integrity (anchored — header/snippet ONLY):**
   - (a) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor `## §5` or `## 5.` heading for `prod_blockers`; capture the 8-field list section.
   - (b) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — anchor `# Schema Vocab Migration — Tech Spec v4` (first line); capture v4 §0.1 changelog v4-A row to confirm v5 deferred-fix continuity.
   - (c) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — anchor `# Handoff v3 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v3` (first line); confirm prior verdict context exists.
   - (d) `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — anchor `## §6` or `prod_blockers schema gotchas` heading; capture the gotchas block to confirm handoff §6 already documents the v5 fix at the implementation level.

If preflight 1-3 fails, HALT and report. If 4 fails for any companion file, document inline; if all 4 fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md`.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md (v5 — supersedes v4 which superseded v3). v5 is a SURGICAL 2-defect correction over v4. v3 design surface received AUTHORIZE_PHASE_0_WITH_RISK_ACCEPTANCE earlier today and is OUT OF SCOPE for this review. Do NOT re-review the v3 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, mutex pattern, Task H). Re-review specifically:
  - §9.4 v5 corrections (acquisition POST + release PATCH + stale-mutex cleanup regex)
  - §6 Gate 11.2 (field-name compliance lint)
  - §7 risk #14 (HTTP 400 on copy-paste)

Background context (informational only):
- v4 corrected severity case (LD-593): CRITICAL → critical (lowercase) — preserved verbatim in v5.
- v5 corrects field names (LD-595): live `prod_blockers` has only 8 fields (`id`, `module_id`, `severity`, `title`, `description`, `is_resolved`, `created_at`, `resolved_at`); v3+v4 example bodies referenced `details` (acquisition POST + stale-mutex cleanup parsing) and `resolution_notes` (release PATCH) — both non-existent → HTTP 400 unknown-field.
- v5 §9.4 replaces those with: acquisition POST encodes `host`/`pid`/`started_at`/`script_version` inside `description` as `STRUCTURED_DETAILS_JSON:` + JSON literal; release PATCH appends `RESOLVED: ...` to existing `description`; stale-mutex cleanup parses PID via `re.search(r"STRUCTURED_DETAILS_JSON:\s*(\{.*?\})\s*$", description, re.DOTALL | re.MULTILINE)` then `json.loads(...)`.
- LD-592 schema-ref doc + LD-595 + handoff §6 prod_blockers gotchas form a five-layer redundancy.

Apply your full independent scrutiny on the v5-scope changes only. The v3 design is locked.

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec v5 file exists; capture size + mtime + shasum.
   Expected sha256: 97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7
   HALT if mismatch — author drift.
2. Quote the first 20 non-blank lines of spec v5 verbatim with capture-line-range.
   First line MUST be: "# Schema Vocab Migration — Tech Spec v5"
3. Companion-file integrity (anchored header/snippet only):
   (a) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor section 5 for `prod_blockers`; quote the 8-field enumeration and the severity enum lines.
   (b) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — anchor `# Schema Vocab Migration — Tech Spec v4`; quote v4 §0.1 v4-A row trailing paragraph that explicitly defers the field-name fix to v5.
   (c) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — anchor `# Handoff v3 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v3`; confirm prior review context.
   (d) `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — anchor `prod_blockers schema gotchas` heading in §6; quote the gotchas block to confirm v2.1 of the implementation handoff already encodes the v5 pattern at implementation level.
4. v5-specific anchor capture:
   (i) Locate `### §9.4 — Concurrency, lockfile, and remote mutex (v5 FIELD-NAME FIX over v4 — self-discovered defect; v4 deferred)` header; quote the v5 callout paragraph + the 3 corrected code blocks (acquisition / release / stale-mutex cleanup) verbatim with line-range.
   (ii) Locate v5 §6 Gate 11.2 row + Gate 11.2 verification-artifact paragraph; quote both verbatim.
   (iii) Locate v5 §7 risk #14 row; quote verbatim.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read v5 spec; could not reproduce a v5-scope anchor (header/snippet match in actual file content); the v5 §9.4 / §6 / §7 / §11 surface is missing or ambiguous; reviewer's evidence is "I think" or "probably" rather than a quoted citation; reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS TASKS (v5-scope only):

A. §9.4 V5 CORRECTIONS REVIEW
   For each of the three corrected code blocks, confirm correctness given live `prod_blockers` has exactly 8 fields and no `details`/`resolution_notes`:
   (a) Acquisition POST: `description` = plain prose + `STRUCTURED_DETAILS_JSON:` + `json.dumps({host, pid, started_at, script_version})`. Confirm: does this satisfy the canonical pattern in `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 lines 362-377? Does it use ONLY the 8 live fields as POST keys (`title`, `severity`, `is_resolved`, `description`)?
   (b) Release PATCH: appends `f"<existing> | RESOLVED: <resolution_text> (see Phase 6 final-audit report at <path>)"` to existing `description`; sets `is_resolved=true`. Confirm: does this preserve the audit trail without losing acquisition-time context? Edge case: what if `existing_description` is None or empty (`existing_blocker.get("description", "") or ""` handles None/empty — verify)?
   (c) Stale-mutex cleanup regex: `re.search(r"STRUCTURED_DETAILS_JSON:\s*(\{.*?\})\s*$", description, re.DOTALL | re.MULTILINE)`. Confirm: is non-greedy `\{.*?\}` correct for nested JSON (e.g., if `started_at` ISO timestamp contains nothing nested, but future payload might)? Does the `$` anchor with `re.MULTILINE` match end-of-line OR end-of-string correctly? Edge case: a release PATCH appended `| RESOLVED: ...` AFTER the STRUCTURED_DETAILS_JSON block — does the regex still find the JSON before the appended content?

   Edge cases to flag (independent scrutiny):
   - JSON parse failure handling: if `json.loads(match.group(1))` raises `json.JSONDecodeError`, what happens? v5 code only handles the no-match case (sets pid=None); it does NOT wrap json.loads in try/except.
   - Postgres TEXT field length: live `prod_blockers.description` is text type. With long hostname + JSON payload + multi-cycle release-PATCH appends (e.g., release-then-reopen-then-release) over time, could it exceed practical usage limits? Postgres TEXT is unbounded but UI displays + indexed queries may degrade.

   NUMERIC THRESHOLD: if Cursor independently identifies a NEW HTTP 400 / 500 failure path that v5 does NOT address (e.g., a third missing-field collision; a regex pattern that fails on the canonical example; a JSON parse failure that crashes the cleanup helper), verdict MUST be AMEND_V2 on Task A.

B. §6 GATE 11.2 LINT REVIEW
   The lint pattern is:
   ```
   grep -n '"details"\|"resolution_notes"' Production/scripts/migrate_schema_vocab_v1.py | grep -v "prod_activity_log\|prod_locked_decisions"
   ```
   Carve-outs:
   - `prod_activity_log.details` — IS a real JSON column; legitimate.
   - `prod_locked_decisions.details` — IS a real text column; legitimate.
   - Comments quoting v3/v4 historical defects — FINE.
   Confirm: is the grep + grep -v chain sufficient? Could a malicious or careless author bypass with a string-literal evasion (e.g., `key_name = "deta" + "ils"; payload[key_name] = ...`; or a key constructed via f-string from a variable; or `payload.update({"details": ...})`; or `setattr(payload_obj, "details", ...)` if payload_obj is a class)?

   Edge case: the carve-out grep `grep -v "prod_activity_log\|prod_locked_decisions"` is line-based. If a single line contains both a `prod_blockers` POST dict literal AND a comment mentioning `prod_activity_log`, the grep -v would suppress the violation incorrectly.

   NUMERIC THRESHOLD: if Cursor identifies a string-literal evasion path that bypasses the lint with ≤ 3 lines of code (e.g., the f-string-key bypass + a payload.update() bypass + a setattr bypass), verdict MUST be AMEND_V2 on Task B with a recommended hardening (e.g., AST-based lint instead of grep, or runtime POST-time field validator).

C. §7 RISK #14 REVIEW
   Risk #14 likelihood = LOW; severity = HIGH. Mitigation chain has 5 layers:
   (1) v5 §9.4 callout enumerates 8 fields prominently;
   (2) LD-592 + LD-595 schema-ref doc gotchas;
   (3) §6 Gate 11.2 lint;
   (4) handoff §6 prod_blockers gotchas (already documented at implementation handoff);
   (5) runtime HTTP 400 → activity-log row `MUTEX_POST_HTTP_400_UNKNOWN_FIELD` pointing to v5 callout.

   Confirm or challenge:
   - Is "LOW" correct? If the v5 callout, LD-595, Gate 11.2 lint, handoff §6 gotchas, AND runtime detector all fail, what's the residual risk? Could an implementer who copy-pastes from v3 without reading v5 still trigger the defect?
   - Is "HIGH" correct? Phase 1+2+4+5 entry guards depend on mutex acquisition. If acquisition halts → all mutating phases halt mid-migration. Confirm severity HIGH.
   - Is the 5-layer chain redundant ENOUGH? Or is one layer load-bearing?

D. COMPATIBILITY WITH V3+V4 PRESERVATION
   v5 §0.1 + §3 + §4 + §5 + §8 + §9.1-§9.3 are stated to preserve v3+v4 verbatim. v5 §5 NOTE flags that v3 §5 / v4 §5 Phase 1 entry-guard code blocks are preserved verbatim there but the migration SCRIPT must use v5 §9.4. Confirm: are v3+v4 example bodies anywhere ELSE in v5 (e.g., Phase 0 dry-run scaffolding, §10 Cursor review companion, §11 reference index) that might still be load-bearing for an implementer? Could a script-author writing from v5 accidentally re-introduce the v3 pattern by reading §5 instead of §9.4?

E. FIELD-LENGTH / POSTGRES PROBE
   `prod_blockers.description` is text type (live-probed). v5 example acquisition POST writes:
   `description = "Schema vocab migration in progress on host <HOST>; PID=<PID>.\n\nSTRUCTURED_DETAILS_JSON: " + json.dumps(payload)`
   With a long FQDN (e.g., 60-char hostname) + JSON payload (~200 bytes) + future append on release (~200 bytes) over multiple migration cycles, could it exceed practical TEXT limits? Postgres TEXT is theoretically unlimited, but: any `btree`/`gist` index on `description`? Any UI display truncation that would lose audit trail? Confirm or surface.

F. STALE-MUTEX REGEX CORRECTNESS
   Regex: `r"STRUCTURED_DETAILS_JSON:\s*(\{.*?\})\s*$"` with flags `re.DOTALL | re.MULTILINE`.
   Confirm correctness:
   - Non-greedy `\{.*?\}`: matches the SHORTEST `{...}` after `STRUCTURED_DETAILS_JSON:`. If the JSON payload contains nested objects (e.g., future schema adds `extra: {sub_field: value}`), non-greedy would match the FIRST closing `}` and miss the outer. Edge case: even current payload might have nested timestamp objects in future versions.
   - `$` anchor with `re.MULTILINE`: `$` matches end-of-line, not end-of-string. If release-PATCH appends `| RESOLVED: ...` on a new line after the STRUCTURED_DETAILS_JSON block, the JSON's closing `}` is still on its own line — the regex would still match. But if appended on the SAME line, the regex's `\s*$` would fail.
   - The trailing `\s*$` may be too restrictive. Consider: should the regex be `r"STRUCTURED_DETAILS_JSON:\s*(\{.*?\})(?:\s|$)"` instead?

   NUMERIC THRESHOLD: if Cursor identifies ≥ 1 plausible payload variation (current or v6+ future) that would cause the regex to extract incorrect JSON or fail to match, verdict MUST be AMEND_V2 on Task F.

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — v5 is sound; Phases 0+1+2+4+6 may proceed; Phase 5 stays self-gated per v3 PHASE_5_ENABLED feature flag; Cursor's prior PHASE_0_WITH_RISK_ACCEPTANCE verdict is upgraded.
- AUTHORIZE_PHASE_0_ONLY — v5 is sound BUT live Directus state cannot be verified by Cursor from its environment; mirror prior v3 verdict scope (Phase 0 dry-run only, with risk acceptance for Phases 1+2+4+5+6 review post-Phase 0 artifacts).
- AMEND_V2 — v5 has a defect; specify the defect AND the required fix in concrete numeric terms (which §9.4 example body line, which Gate 11.2 carve-out, which risk-row mitigation layer).
- PAUSE_FOR_REDEBATE — v5 has a fundamental issue requiring dual-Opus or expanded review.

Required output:
1. Preflight evidence (sha256 + first 20 lines verbatim + 4 anchored companion-file quotes + 3 v5-anchor captures).
2. Analysis table (per task A-F) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Verdict (one of the four above).
4. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v5.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → dispatch implementation via terminal CLI per `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` (post-v2.2 amendment if landed). Phase 5 stays self-gated per v3 PHASE_5_ENABLED feature flag; Phases 0+1+2+4+6 may proceed.
- **`AUTHORIZE_PHASE_0_ONLY`** → dispatch Phase 0 dry-run only with risk acceptance; Phases 1+2+4+6 follow after Phase 0 artifact review (mirrors prior v3 verdict scope).
- **`AMEND_V2`** → author `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` addressing the blocker(s); preserve v5 as historical baseline; re-run THIS handoff against v6.
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate; do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v5 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-13 Layer 6:** input variation (read v3 handoff vs v4 spec vs v5 spec) → output variation (this handoff differs structurally to focus only on v5's surgical scope, not the full v3 task surface).
- **DS-27 (absolute paths, dual-canonical):** all filesystem-touching commands MUST use absolute paths anchored to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (canonical root #1) OR `/Users/kimberlysmith/Projects/` (canonical root #2). Do NOT operate inside `.claude/worktrees/` subdirectories. All paths in this handoff are anchored to canonical root #1 (Dropbox-rooted).
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag.
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V2 thresholds (mandatory):** every analysis section asking "is X acceptable?" includes "if X > Y, verdict MUST be AMEND_V2." Tasks A, B, F have explicit numeric triggers; Tasks C, D, E are descriptive evaluations escalating per the standard rule.

---

## Final report — required structure

Path: `Production/docs/CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_REPORT_20260508_v5.md`

Required sections:

1. HALT gate scan results — 4 gates (sha256 match, §9.4 v5 callout anchor, §6 Gate 11.2 anchor, §7 risk #14 anchor).
2. Cursor verdict verbatim.
3. Per-task summary — A through F, each with verdict + anchored evidence + numeric-threshold result where applicable.
4. Confidence tags per Rule 24.
5. Self-classification — REVIEW (v5-scope tight; Cursor's classification of its own analysis).
6. Limitations — what wasn't covered (v3 design surface intentionally excluded; live Directus state if unreachable).
7. Cross-skill drift — does v5's lint pattern require parallel update to weekly_preflight_audit.py or zero-error-qa SKILL.md?
8. Next-step recommendation.

---

## Cross-references

- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround).
- `LD-593` — v4 §9.4 severity case-fold authority.
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — prior review handoff (structural template for THIS handoff).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference (8-field enumeration + severity enum + STRUCTURED_DETAILS_JSON pattern).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (§6 prod_blockers schema gotchas added v2.1 anticipates v5 fix; potentially needs v2.2 amendment per v5 §12 changelog note).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms).

---

## §12 — Change log

- **v5** — 2026-05-08 — initial draft for v5 spec cross-review. Surgically narrowed scope: v3 design out-of-scope (already authorized); v4 case-fold out-of-scope (already locked under LD-593); review focuses on v5 §9.4 corrections + §6 Gate 11.2 + §7 risk #14 + §11 reference index. Six analysis tasks (A-F) with numeric AMEND_V2 thresholds on tasks A, B, F. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.
