# Handoff v3 — Cursor Cross-Review of PERIODIC Class Tech Spec v1

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1); 867 lines, 59,541 bytes; sha256 `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f`.

**Supersedes:**
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508.md` — v1 handoff (preserved as historical baseline; do NOT edit in place).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md` — v2 handoff (preserved as historical baseline; sha256 `f705718d371c3cc261468e07ca29f0dabf7e261a76986c0af89eaa1c15df0130`; 7,304 bytes; 143 lines; mtime 2026-05-08 01:23).

**v2 → v3 driver:** v2 handoff was authored 2026-05-08 01:23; HANDOFF_TEMPLATE_v2 was extended at 2026-05-08 11:43 with §0.3 companion-path discipline + concise→full escalation clause + numeric AMEND_V2 thresholds + autonomous-mode HALT-gates verbatim reminder. Per audit (`prod_activity_log` row id=1817, agent `a1a4400ea2bdc691c`), v2 fails HANDOFF_TEMPLATE_v2 compliance on 7 categories: concise→full clause MISSING, numeric AMEND_V2 thresholds MISSING, companion paths with canonical-root tags MISSING, HALT gates section + autonomous-mode reminder MISSING, Hard rules + Final report sections MISSING, absolute paths dual-canonical PARTIAL, anchored citation discipline PARTIAL. v3 reauthored fresh under current template.

**Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical):**

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1; **spec under review**); sha256 `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f`; 867 lines.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508.md` — Dropbox-rooted (canonical root #1; v1 handoff historical baseline).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md` — Dropbox-rooted (canonical root #1; v2 handoff historical baseline; sha256 `f705718d371c3cc261468e07ca29f0dabf7e261a76986c0af89eaa1c15df0130`).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — Dropbox-rooted (canonical root #1; **structural template precedent**; HANDOFF_TEMPLATE_v2-conformant cross-review handoff).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; **template authority**; this handoff conforms to v2 template — anchored citations, concise→full escalation, numeric AMEND_V2 thresholds, dual-canonical absolute paths, companion path discipline, HALT gates with autonomous-mode reminder, Hard rules + Final report sections).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; §1 = ground truth for `prod_locked_decisions` field set; 22 live fields; relevant for verifying the 3 new field type/nullability proposals in spec §4.1).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` — Dropbox-rooted (canonical root #1; implementation handoff; reviewer should NOT execute it; named here so reviewer can cite when emitting AUTHORIZE_IMPLEMENTATION verdict).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.claude/skills/zero-error-qa/SKILL.md` — Dropbox-rooted (canonical root #1; **DS-29 source-tagging mandate** + DS-13 Six-Layer + DS-26 HALT-gate discipline + DS-27 absolute-path discipline cited in this handoff's Hard rules).

---

## §0.1 — Why this v3 review exists

The PERIODIC class tech spec v1 (`Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md`) proposes:

1. A third SHORTCUT LD classification class `PERIODIC` (alongside existing `EVENT_DRIVEN` + `RARE_NEVER`).
2. **Three new fields on `prod_locked_decisions`:** `review_cadence` (string enum: monthly / quarterly / semi-annually / annually / event-driven / none), `next_review_date` (date), `last_reviewed_date` (date).
3. A new branch in `check_shortcut_ld_closure_dates()` in `weekly_preflight_audit.py` that warns at past-due day-0 + escalates CRITICAL after 7-day grace.
4. A roadmap §1.6 column update + tight migration cohort (1 LD: 249).

This is a NEW design with NO prior authorized review. v1 handoff was authored 2026-05-08 01:23. v2 handoff was Cursor's own meta-review feedback re-authored, but pre-dates HANDOFF_TEMPLATE_v2's 11:43 extension (companion-path §0.3 + autonomous-mode reminder + Hard rules + Final report mandates). Per `prod_activity_log` row 1817, v2 fails 7 template-compliance categories.

v3 (this handoff) is the canonical paste-into-Cursor entry point. v1 + v2 are preserved as historical record. Since this is a NEW spec for an UNREVIEWED design (NOT a surgical fix-set over a prior-authorized design), Cursor's full architectural review applies — six analysis tasks (A through F) covering schema/architectural, classification system, audit logic, deferred decisions, risks, and sequencing.

---

## §0.2 — What you DON'T need to do

- Do NOT edit the PERIODIC spec. Verdict-only.
- Do NOT implement the migration. Implementation handoff is at `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`; this handoff is review-only.
- Do NOT probe Directus directly (Cursor's environment lacks creds per prior session conventions). Reviewer relies on quoted spec content + the schema-ref doc + the live LD probes performed by THIS handoff's author (LDs 200/249/561 confirmed `status=active` 2026-05-08).
- Do NOT re-review the v1 + v2 handoff structure as standalone artifacts — they are superseded by v3 (this doc) per HANDOFF_TEMPLATE_v2 §0.3 compliance audit.

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has spec v1 sha256 been confirmed match `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f`? | `shasum -a 256` of the absolute path `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` | Hash matches verbatim | HALT — author drift; surface to Kim before any analysis |
| 2 | Has stale-cache check passed? First non-blank line of spec MUST read `# PERIODIC Class — SHORTCUT LD Classification System Tech Spec v1` | First 20 lines of spec captured verbatim with line numbers | First line matches verbatim; lines 1-20 are quotable as proof of fresh read | HALT — surface stale-cache or wrong-file evidence to Kim |
| 3 | Have companion anchors been verified? | (a) Spec §4.1 anchor `### §4.1 Schema migration (3 new fields on \`prod_locked_decisions\`)`; (b) spec §5 anchor `## §5 Open Decisions — Dual-Opus Debate`; (c) spec §7 anchor `## §7 Migration Cohort`; (d) spec §16 anchor `## §16 Recommended Sequence to Implementation`; (e) schema-ref doc anchor `## 1. \`prod_locked_decisions\`` | All 5 anchors located by header/snippet match (NOT line number) | HALT and report which anchor failed |
| 4 | Does spec §0 Operating Mode declaration confirm `Status: DESIGN-ONLY`? | Spec line 3 anchor `**Status:** DESIGN-ONLY — awaiting Kim authorization` | Status reads exactly DESIGN-ONLY | HALT — spec may have advanced beyond design without authorization; surface to Kim |
| 5 | Are LDs cited in spec §14 Reference Index still active? | Spec §14 cites LDs 199, 200, 201, 249, 263, 561, 566, 568. Author's 2026-05-08 live probe confirmed: 200=active, 249=active, 561=active. Reviewer takes author's probe as evidence; need not re-probe. | Probed LDs 200, 249, 561 all `status=active` per author's probe captured in this handoff | HALT only if reviewer has independent contradicting evidence (e.g., a quoted Directus row showing `status=closed`) |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md"
   ```
   Expected: file exists, size 59,541 bytes, mtime 2026-05-08.

2. **`shasum -a 256` spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md"
   ```
   Expected: `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Quote first 20 lines of spec verbatim** (stale-cache detector). The first non-blank line MUST be `# PERIODIC Class — SHORTCUT LD Classification System Tech Spec v1`. Capture lines 1-20 with line numbers.

4. **Companion-file integrity (anchored — header/snippet ONLY):**
   - (a) `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — anchor `### §4.1 Schema migration (3 new fields on \`prod_locked_decisions\`)`; capture the 3-row table proposing `review_cadence` + `next_review_date` + `last_reviewed_date` field types.
   - (b) Same spec — anchor `## §5 Open Decisions — Dual-Opus Debate`; capture the §5.1 enum-vs-free-text resolution paragraph (`Resolution:` + the 6-value enum table).
   - (c) Same spec — anchor `## §7 Migration Cohort`; capture the LD 249 row + the LD 200 stay-EVENT_DRIVEN row.
   - (d) Same spec — anchor `## §16 Recommended Sequence to Implementation`; capture the 7-step sequence paragraph.
   - (e) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor `## 1. \`prod_locked_decisions\``; capture the live 22-field enumeration to ground-truth the spec's claim of 22 existing fields + 3 new = 25 post-migration.

If preflight 1-3 fails, HALT and report. If 4 fails for any companion file, document inline; if all 5 fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` in the editor. Open Cursor Composer or chat.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md (867 lines, 59,541 bytes). It proposes adding a third "PERIODIC" class to a SHORTCUT LD classification system (alongside existing EVENT_DRIVEN and RARE_NEVER). The spec adds 3 new fields to the prod_locked_decisions Directus table (review_cadence enum, next_review_date date, last_reviewed_date date) and a new branch in our weekly audit logic at weekly_preflight_audit.py.

This is a NEW spec for an UNREVIEWED design — full architectural review applies. NOT a surgical fix-set over a prior-authorized design. Apply your full independent scrutiny.

Background context (informational only — do NOT let this anchor your scrutiny):
The spec was authored via dual-Opus debate (one advocate position, one counter position per §5 + §6). The debate concluded with per-decision resolutions. Treat this as background, not as a judgment. Apply your full independent scrutiny regardless of the prior debate outcome.

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec file exists; capture size + mtime + shasum.
   Expected sha256: 387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f
   HALT if mismatch — author drift.
2. Quote the first 20 lines of the spec verbatim with capture-line-range.
   First non-blank line MUST be: "# PERIODIC Class — SHORTCUT LD Classification System Tech Spec v1"
3. Companion-file integrity (anchored header/snippet only):
   (a) `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — anchor `### §4.1 Schema migration (3 new fields on \`prod_locked_decisions\`)`; capture the 3-row field-proposal table verbatim.
   (b) Same spec — anchor `## §5 Open Decisions — Dual-Opus Debate`; capture the §5.1 Resolution paragraph + 6-value enum table.
   (c) Same spec — anchor `## §7 Migration Cohort`; capture the LD 249 row + the LD 200 "stay EVENT_DRIVEN" row.
   (d) Same spec — anchor `## §16 Recommended Sequence to Implementation`; capture the 7-step sequence paragraph.
   (e) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor `## 1. \`prod_locked_decisions\``; capture the 22-field enumeration verbatim.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read spec; could not reproduce an anchor (header/snippet match in actual file content); a required §4.1 / §5 / §7 / §9 / §16 surface is missing or ambiguous; reviewer's evidence is "I think" or "probably" rather than a quoted citation; reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

"Severity" rubric:
- CRITICAL = ship-blocker; spec must not advance to implementation.
- HIGH = revise spec before implementation.
- MED = address in v2 amendment OR document as known-deferred.
- LOW = nice-to-have, optional.

"Blocker" rubric:
- Y = Kim should NOT authorize implementation until this is resolved.
- N = informational; documented and proceed acceptable.

REQUIRED ANALYSIS TASKS (full architectural — 6 tasks A-F):

A. ARCHITECTURAL & SCHEMA REVIEW
   The spec proposes 3 new fields on `prod_locked_decisions` (§4.1):
   - `review_cadence` — string (enum), nullable, with 6 values: monthly/quarterly/semi-annually/annually/event-driven/none.
   - `next_review_date` — date, nullable.
   - `last_reviewed_date` — date, nullable.

   Cross-reference live schema at `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §1 — confirms 22 active fields. The new fields take the count to 25.

   Confirm:
   (a) Field types are correct for use case. `review_cadence` as string-with-interface-enum (Directus pattern) vs native enum vs string-only. `next_review_date` + `last_reviewed_date` as date (not datetime, not string).
   (b) Indexed appropriately. The new audit branch (§4.2) queries on `next_review_date` for PERIODIC LDs. Without an index, that scan is O(N_active_LDs) per audit run. Is the spec's omission of indexing strategy a defect?
   (c) Migration plan defensible. Spec §8 Phase A says "PATCH /fields/prod_locked_decisions to add 3 fields" — additive only, no backfill. Does this break any existing reader of `prod_locked_decisions` (e.g., a SELECT that presumed 22 fields exactly)?
   (d) The cap-selection refactor in §4.3 (replacing the `else` branch with explicit `if/elif/else: raise`) introduces a runtime-fail if a future classification value isn't recognized. Is this discipline-loud-fail correct, or does it create a fragile single-point-of-failure?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 schema design defect (wrong type, missing index that breaks audit query patterns at any active-LD population, migration gap that breaks an existing reader of prod_locked_decisions, or cap-selection refactor introducing a regression), verdict MUST be AMEND_V2 on Task A.

B. CLASSIFICATION SYSTEM REVIEW
   The spec adds a third class `PERIODIC`. Name + 6 cadence enum values + migration cohort assessment.

   Confirm:
   (a) PERIODIC name choice. Other ecosystems use "scheduled review" or "recurring decision." Is "PERIODIC" the clearest name for the semantic the spec describes (deliberate calibrations with scheduled re-evaluation cadence)?
   (b) 6 cadence enum values. Spec §5.1 lists `monthly` (30 days), `quarterly` (90), `semi-annually` (180), `annually` (365), `event-driven` (irregular, manual updates), `none` (sentinel for non-PERIODIC LDs). Are any missing or redundant? Common case "bi-monthly" or "every-fiscal-quarter" are not represented — is that a real gap or a stretch case?
   (c) Migration cohort. Spec §7 proposes only LD 249 → PERIODIC. Spec discusses LD 200 staying EVENT_DRIVEN with rationale (quarterly cadence is administrative confirm-no-change, not a calibration). Independently assess: is LD 200's cadence really administrative? Are there other current LDs (e.g., LDs 263, 566, 568, 346, 231, 325 listed in §7 as discussed-but-not-migrating) that should ACTUALLY migrate but the spec wrongly excludes?
   (d) The `event-driven` enum value within review_cadence is semantically overloaded — a PERIODIC class LD with `review_cadence=event-driven` reads as a contradiction (the LD is EVENT_DRIVEN-ish but classified PERIODIC). Is this the right escape hatch or does it dilute the class semantics?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 LD that should migrate but isn't in the spec's cohort (out of LDs 200, 263, 566, 568 that the spec explicitly considered) OR ≥1 cadence enum that's structurally wrong (overlapping semantics like `event-driven` overloading the PERIODIC class boundary; missing dominant-case cadence that affects the foreseen population in §2.3 + §7 future-PERIODIC candidates list), verdict MUST be AMEND_V2 on Task B.

C. AUDIT LOGIC REVIEW
   Spec §4.2 + §5.3 propose: WARN at past-due day-0 + CRITICAL after 7-day grace. Approach window: 7 days before next_review_date.

   Confirm:
   (a) Industry norm is to warn 30+ days before due date (vendor renewal evaluations, compliance audits, license cycles). Spec's 7-day approach is much tighter. Defensible? §5.3 cites the existing two-tier `warn=30, critical=7` pattern but inverts it. Is the inversion well-justified?
   (b) Should there be a missed-review auto-escalation (e.g., if next_review_date is past by 30 days with no last_reviewed_date update, escalate further beyond CRITICAL)?
   (c) The spec's §4.2 pseudocode emits the past-due finding with `critical=True` unconditionally on day-0; §5.3 amends to `is_critical = days_overdue >= 7`. Confirm that the pseudocode in §4.2 is consistent with §5.3 resolution OR that the spec flags the inconsistency.

   NUMERIC THRESHOLD: if Cursor's recommended advance-warn lead time differs from spec's 7-day choice by > 30 days (i.e., ≥ 37 days advance warn) AND the spec doesn't justify the tightness with citation to the existing two-tier `warn=30, critical=7` pattern (lines 198-199 of audit script per §3.2), verdict MUST be AMEND_V2 on Task C.

D. DEFERRED DECISIONS REVIEW
   Spec §5.4 defers `last_reviewed_date` cadence-consistency check to v2. Spec §5.5 reuses `severity: critical` with a distinct title prefix rather than introducing `severity: review_overdue`.

   Confirm:
   (a) Is the §5.4 deferral the right call or v1 must-have? §5.4 cites signal-to-noise concern (false-positive rate ~50% for cadence inconsistency). Is that estimate defensible?
   (b) Is reusing `severity: critical` with title prefix the right call, or does it dilute the dashboard-gate triage (mixing genuine RARE_NEVER cap-expired escalations with PERIODIC review-cadence slips)? §5.5 cites `filter[title][_starts_with]` discipline at audit script line 422 — verify this filter pattern is actually used, not just claimed.
   (c) Spec §1.2 lists out-of-scope items including "review history / audit-trail columns" + "auto-creation of review-due LDs" + "backfill last_reviewed_date for non-SHORTCUT LDs" + "multi-cadence LDs". Are any of these out-of-scope items HIGH-severity gaps that v1 cannot ship without?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 deferral that creates a HIGH-severity gap (defined as: a failure mode where v1 ships AND a real PERIODIC review is missed AND no surfacing fires within 30 days of the missed review date), verdict MUST be AMEND_V2 on Task D.

E. RISK ASSESSMENT REVIEW
   Spec §9 enumerates 9 risks with severity tags (HIGH/MEDIUM/LOW) + mitigations.

   Confirm:
   (a) Risk completeness — are there HIGH-severity risks NOT in §9? Suggested categories to check:
       - Silent data loss of `next_review_date` (e.g., a Directus PATCH clears the field due to operator error — does the audit detect a transition from non-NULL → NULL?)
       - Audit running BEFORE schema migration completes (race: §8 Phase A lands schema, weekly cron fires before Phase B's audit-logic update lands → audit fails on missing dict entry for PERIODIC).
       - Concurrent edit during Phase C migration (LD 249 PATCH interleaves with another session's PATCH on adjacent fields, e.g., `notes` or `status`, producing partial overwrite).
       - Directus enum interface drift (the field is created as string-with-enum-interface, but a future Directus admin UI session edits the enum values list, silently invalidating an existing row's `review_cadence` value).
       - Cron + grace-period interaction (a PERIODIC LD's `next_review_date` lands on a Sunday; the weekly cron runs Tuesday; effective grace is now 9 days not 7 — does the spec acknowledge this?).
   (b) Risk severity calibration — are any of the §9 LOW risks actually MEDIUM or HIGH given the spec's design choices? E.g., risk "LD 249's next_review_date = 2026-07-18 is wrong" tagged LOW, but if Kim disagrees and needs to amend, the rollback path through Phase C requires git revert + Directus PATCH — is LOW the right tag?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 missing HIGH-severity risk (a risk that, if it materialized, would cause silent missed reviews AND has likelihood > 1-in-100 PERIODIC LD lifecycles), verdict MUST be AMEND_V2 on Task E.

F. SEQUENCING REVIEW
   Spec §8 Phases A→G + §16 Recommended Sequence (7 numbered steps from Kim review window through 6-month retro).

   Confirm:
   (a) Build a dependency graph: which phase produces prerequisites for which? Write the graph inline.
   (b) Phase ordering risk: identify any phase where the spec's ordering creates implementation risk if reversed. E.g., does Phase B (audit) MUST come after Phase A (schema), or could they parallelize?
   (c) Parallelization opportunities: identify any phases that could parallelize without breaking dependencies.
   (d) Rollback ordering (§11 LIFO Phase D → C → B → A): is the LIFO discipline correct? Does it handle the case where Phase A succeeded but Phase B failed? (Schema lands but audit doesn't update → audit fails on next cron.)

   NUMERIC THRESHOLD: if Cursor identifies a phase ordering that creates implementation risk if reversed (e.g., B before A → audit references missing schema fields and crashes on first run; C before B → migration cohort PATCHed but audit can't process the new classification yet), AND the spec doesn't surface this risk explicitly, verdict MUST be AMEND_V2 on Task F.

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — spec is sound; Phases A-G per §8 may proceed via the implementation handoff at `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`.
- AUTHORIZE_PHASE_0_ONLY — spec is sound BUT live Directus state cannot be verified by Cursor from its environment; mirror prior schema-migration v3 verdict scope (Phase 0 = non-mutating dry-run only; Phases A-G review post-Phase 0 artifacts).
- AMEND_V2 — spec has a defect; specify the defect AND the required v2 fix in concrete numeric terms (which §4.1 field, which §5 resolution, which §9 risk row, which §8 phase ordering).
- PAUSE_FOR_REDEBATE — spec has a fundamental issue; recommend dual-Opus or expanded review.

Required output:
1. Preflight evidence (sha256 + first 20 lines verbatim + 5 anchored companion-file quotes).
2. Reader-impact enumeration table — every reader of `prod_locked_decisions` in the codebase across .py / .md / .ts / .tsx / .yml; for each reader, classify break-risk (none/low/med/high) given the 3 new fields.
3. Concerns table (mandatory citation format above) — across all 6 tasks A, B, C, D, E, F.
4. Phase dependency graph (inline ASCII or table).
5. Verdict (one of the four above).
6. If AMEND_V2 or PAUSE: provide the specific blocker list with concrete §-references.
7. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PERIODIC_SPEC_20260508_v3.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → dispatch implementation via Terminal CLI per `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md`. Phases A-G per spec §8 may proceed.
- **`AUTHORIZE_PHASE_0_ONLY`** → dispatch Phase 0 dry-run only (read spec end-to-end + read `weekly_preflight_audit.py` + verify Directus credentials, no PATCH/POST). Phases A-G follow after Phase 0 artifact review.
- **`AMEND_V2`** → bring the blocker list back to Claude Code; author `Production/docs/PERIODIC_CLASS_TECH_SPEC_v2.md` addressing each blocker with concrete §-references; preserve v1 spec as historical baseline; re-run THIS handoff against v2 (rename + bump version refs + re-anchor).
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate or expanded review session; do NOT advance to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST. Applies to handoff author logging this handoff to `prod_activity_log`. Applies to Cursor reviewer if they touch Directus during analysis — they should not (review-only, no Directus mutation).
- **Multipass:** re-Read the spec after this handoff is authored (handoff author discipline; Cursor reviewer re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-13 Layer 6:** end-to-end smoke test for every new behavior — input variation (read v6 schema-migration handoff template + PERIODIC v1 spec) → output variation (this handoff differs structurally to cover full architectural review of a NEW design, not surgical fix-set over prior-authorized design).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 explicit (refactored 2026-05-08 v2 dual-canonical):** "All filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root. Verify paths with `ls -la <absolute-path>` before edits. Paths outside both canonical roots require explicit Kim authorization." All paths in this handoff are anchored to canonical root #1 (Dropbox).
- **DS-28 dependency-order:** preflight steps 1-4 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **DS-29 (source tagging mandate):** apply (my probe) / (agent claim) / (unverified) tags throughout the handoff author's final report. The Cursor reviewer applies the same discipline.
- **JSON-column gotcha:** the activity-log POST below uses `details` as a dict (live `prod_activity_log.details` IS a JSON column).
- **LD-597 anti-confusion:** NO `task_description` field anywhere in the activity-log payload. The live `prod_activity_log` schema uses `action` + `details` only; an extra `task_description` key creates schema drift confusion. Per audit history, this rule is explicitly the trigger for v3 (vs v2's omission).
- **HANDOFF_TEMPLATE_v2 compliance — all 7 mandates:** anchored citation discipline, concise→full escalation clause, numeric AMEND_V2 thresholds, absolute paths dual-canonical, companion paths with canonical-root tags, HALT gates section + autonomous-mode reminder verbatim, Hard rules + Final report sections.
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag.
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V2 thresholds (mandatory):** Tasks A-F all have explicit numeric triggers tied to verdict.
- **Halt-and-surface if PERIODIC spec sha256 has changed since session record (`387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f`).**

---

## Final report — required structure

Path: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PERIODIC_SPEC_REPORT_20260508_v3.md`

Required sections:

1. HALT gate scan results — 5 gates (sha256 match, stale-cache first-line check, companion anchors verified, spec §0 status reads DESIGN-ONLY, LDs cited still active per author's probe).
2. Cursor verdict verbatim.
3. Per-task summary — A, B, C, D, E, F, each with verdict + anchored evidence + numeric-threshold result where applicable.
4. Reader-impact enumeration table per `prod_locked_decisions` codebase scan.
5. Phase dependency graph.
6. Confidence tags per Rule 24.
7. DS-29 source tagging — (my probe) / (agent claim) / (unverified) tags throughout.
8. Self-classification — REVIEW (full architectural; Cursor's classification of its own analysis).
9. Limitations — what wasn't covered (live Directus state if unreachable; reader-impact scan completeness).
10. Cross-skill drift — does the PERIODIC class addition require parallel update to `weekly_preflight_audit.py`, `zero-error-qa SKILL.md`, `dashboard-gate SKILL.md`, or roadmap §1.6?
11. Next-step recommendation.

---

## Cross-references

- `Production/docs/PERIODIC_CLASS_TECH_SPEC_v1.md` — spec under review (sha256 `387874ac8d0ea9028c0935f8303434b7a5d9f9a72fc7084e30bbbdaa3746955f`).
- `Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508.md` — v1 handoff (historical baseline).
- `Production/docs/HANDOFF_CURSOR_REVIEW_PERIODIC_SPEC_20260508_v2.md` — v2 handoff (historical baseline; sha256 `f705718d371c3cc261468e07ca29f0dabf7e261a76986c0af89eaa1c15df0130`; failed HANDOFF_TEMPLATE_v2 compliance per `prod_activity_log` row 1817).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — structural-template precedent (HANDOFF_TEMPLATE_v2-conformant).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms; 2026-05-08 11:43 §0.3 extension applied).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — live `prod_locked_decisions` schema reference (22 fields pre-migration).
- `Production/docs/HANDOFF_PERIODIC_CLASS_IMPLEMENTATION_20260508.md` — implementation handoff (do NOT execute from review session).
- `.claude/skills/zero-error-qa/SKILL.md` — DS-13 / DS-19 / DS-26 / DS-27 / DS-29 mandates.
- LD probes (2026-05-08 author): id=200 active, id=249 active, id=561 active.
- LD `MASTER_ROADMAP_LIVING_DOC_V1` (id=561) — mandates §1.6 closure surfacing for SHORTCUT LDs (cited in spec §14).

---

## §12 — Change log

- **v3** — 2026-05-08 — initial draft for v3 cross-review handoff. Replaces v2 handoff which failed HANDOFF_TEMPLATE_v2 compliance on 7 categories (per `prod_activity_log` row 1817): concise→full clause MISSING, numeric AMEND_V2 thresholds MISSING, companion paths with canonical-root tags MISSING, HALT gates section + autonomous-mode reminder MISSING, Hard rules + Final report sections MISSING, absolute paths dual-canonical PARTIAL, anchored citation discipline PARTIAL. v3 mirrors the structural template at `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` adapted for full architectural review of a NEW spec (NOT surgical fix-set). Six analysis tasks (A-F) covering schema/architectural, classification system, audit logic, deferred decisions, risks, sequencing — all with numeric AMEND_V2 thresholds. v1 + v2 preserved as historical record. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.
