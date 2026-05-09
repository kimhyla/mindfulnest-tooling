# Handoff — Cursor Cross-Review of Directus Payload Validator Tech Spec v1

**For:** Cursor (Composer or chat) — independent reviewer
**From:** Claude Code session `gallant-bouman-804b4f`, 2026-05-08
**Spec under review:** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1; **spec under review**); 60,533 bytes; 449 lines; sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`.

**Spec scope:** DESIGN-ONLY proposal for a generic schema-aware payload validator across ALL `prod_*` Directus collections. Generalizes the v6 narrow validator pattern (`validate_prod_blockers_payload`, prod_blockers-only) one architectural layer up to cover all 30 live `prod_*` collections via live-schema probe + per-collection cache + override file + phased rollout. This handoff is the §10 Cursor cross-review companion called out in the spec itself; spec §6 Gate 10 makes Cursor cross-review a REQUIRED pre-condition for Phase 1 implementation.

**Authority:** LD-599 `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` (filed 2026-05-08; status=active; severity=SOFT; scope_domain=infra) — confirmed live via `DirectusAdminClient` probe at handoff authoring time.

**Motivation:** DESIGN-ONLY spec for generic schema-aware payload validator across all prod_* collections; this handoff is the §10 Cursor cross-review companion. Independent architectural review of 7 design decisions + 6-phase plan + 10-risk table + spec §0 Operating Mode + §14 Pre-execution checklist + §15 Audit + §16 Reference index. Cursor has NOT previously seen this spec — this is the FIRST review (not a fix-set verification like v6/v7 of the schema migration chain).

---

## §0.1 — Why this review exists (full architectural review, NOT surgical fix-set verification)

The spec under review is a **NEW DESIGN** — it proposes a generic payload validator that runs on every Directus write across the codebase (21 active write-call files in spec §0.1; 30 prod_* collections in spec §1). The blast radius is broad enough that spec §6 Gate 10 makes Cursor cross-review a required gate before implementation.

This is unlike the recent v6/v7 schema-migration review handoffs (which were surgical fix-set verifications of specific Cursor AMEND verdicts). Here Cursor reviews the **entire** spec surface:
- 7 design-decision verdicts (§3 dual-Opus debate)
- 6-phase rollout plan (§5)
- 10-risk table (§7)
- Performance + scaling claims (§5.0 caching invariants, §7 risk #3)
- Failure-mode coverage (§7 risk #4, #5, #8)
- Dog-fooding recursion (§9.3 + §7 risk #8)
- Backward-compat for the 21 existing write-call files

The structural template is `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` (the prior architectural-review handoff Cursor produced AMEND_V2 on; closest precedent in this codebase for a DESIGN review handoff). v2 of the handoff template (`Production/docs/HANDOFF_TEMPLATE_v2.md`) governs structure: anchored citations, concise→full escalation rule, numeric AMEND_V2 thresholds, dual-canonical absolute paths, companion-files with canonical-root tags, HALT gates section, autonomous-mode reminder.

---

## §0.2 — What you DON'T need to do

- Do NOT have Cursor edit the spec. Verdict-only review.
- Do NOT have Cursor implement the validator. Implementation is gated on Kim approving each of spec §6's 10 gates AFTER this Cursor review returns.
- Do NOT have Cursor probe live Directus state — Cursor's environment may not have credentials. Live-schema probes were performed at spec authoring time (see spec §1 + §0.1).
- Do NOT re-debate whether a runtime payload validator is the right pattern — the v6 narrow validator (`validate_prod_blockers_payload`) is already in production for `prod_blockers` and validated the pattern at the narrow scope. Cursor should accept the **generalization premise** as design-sound (already proven at narrow scope) but rigorously review the spec's design decisions.
- Do NOT touch any other spec, handoff, schema-ref doc, hook script, migration script, or LD record — this is review-only on `DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md`.

---

## Companion files (absolute paths per HANDOFF_TEMPLATE_v2 §0.3 dual-canonical)

- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md` — Dropbox-rooted (canonical root #1; **spec under review**); sha256 `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`; 60,533 bytes; 449 lines.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/lib/directus.py` — Dropbox-rooted (canonical root #1; **wire-up integration target**); spec §5 Phase 2 adds one import + one validator call inside `try_post_or_queue` here; existing `_validate_json_columns` + `JSON_COLUMN_INVENTORY` + `post_item_verified` live here.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — Dropbox-rooted (canonical root #1; **live schema authority**); enumerates per-collection field names — Phase 5 cross-reference target. Contains the 11-field `prod_activity_log` and 12-field `prod_preflight_reviews` enumerations from LD-597.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — Dropbox-rooted (canonical root #1; **v6 narrow validator authority**); §6 Gate 11.2 + §9.4 are the precedent the v1 spec generalizes. The v6 narrow validator pattern (`validate_prod_blockers_payload` + `ALLOWED_PROD_BLOCKERS_KEYS`) is already in production.
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — Dropbox-rooted (canonical root #1; v7 spec — JSON-string-aware extractor; LD-598 reference for context only).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — Dropbox-rooted (canonical root #1; **structural template** for THIS handoff; v6 review returned AMEND_V2 with surgical-fix scope; THIS handoff adopts the same Step 0 / Step 1 / Step 2 / Step 3 structure but broadens scope to full architectural review).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v7.md` — Dropbox-rooted (canonical root #1; v7 review handoff for context; same structural lineage).
- `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/HANDOFF_TEMPLATE_v2.md` — Dropbox-rooted (canonical root #1; **template-compliance reference**); this handoff conforms to v2 — anchored citations, concise→full escalation, numeric AMEND_V2 thresholds, dual-canonical absolute paths, companion path discipline, HALT gates section.

**Cross-references — LDs:**
- **LD-590** (`SCHEMA_VOCAB_MIGRATION_V3_LOCKED`) — v3 design surface authorization (context).
- **LD-595** (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1`) — v5 field-name fix authority (driving incident #2 in spec §2.1).
- **LD-596** (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1`) — v6 narrow validator authority (the pattern this spec generalizes).
- **LD-597** (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — anti-confusion guards (driving incident #1 in spec §2.1).
- **LD-598** (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR`) — v7 spec extractor (context).
- **LD-599** (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1`) — **spec authority for THIS review**; status=active, severity=SOFT, scope_domain=infra (live-probed 2026-05-08).

---

## HALT gates

**Autonomous mode does not bypass HALT gates per DS-26.** If the gate-check fails, HALT and write a "halted, awaiting authorization" report. Do NOT interpret blanket autonomous-mode authorization as override.

Autonomous mode (LD-232) authorizes execution of documented work without per-step confirmation. HALT gates ARE part of the documented work. Skipping a gate is skipping the procedure, not "trusting the autonomous-mode authorization."

### Gates (must all be MET before Step 2 prompt is paste-able to Cursor)

| # | Gate | Evidence source | Pass criterion | Fail action |
|---|------|-----------------|----------------|-------------|
| 1 | Has spec sha256 been confirmed match `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75`? | `shasum -a 256` of spec absolute path | Hash matches verbatim | HALT — author drift; surface to Kim |
| 2 | Has the first non-blank line of the spec been confirmed to read `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1`? | First-20-lines verbatim quote during Step 0 preflight | First non-blank line MUST match | HALT — stale-cache or wrong file; surface to Kim |
| 3 | Have ALL 7 companion-file anchors been verified? | Per-companion `ls -la <absolute-path>` returns existing file | All 7 paths resolve under canonical root #1 | HALT and report which anchor failed |
| 4 | Does spec §0 Operating Mode read "DESIGN ONLY"? | Anchor: locate `## §0 — Operating Mode` heading; capture verbatim text | Substring "DESIGN ONLY" present in §0 body | HALT — spec scope misclassification; surface to Kim |
| 5 | Has LD-599 been confirmed `decision_key=DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1` AND `status=active`? | Live Directus probe via `DirectusAdminClient` (handoff author performed at authoring time) | Both fields match exactly | HALT — LD authority drift; surface to Kim |

---

## Step 0 — Preflight (do FIRST, before any analysis) — anchored discipline

Mandatory actions, emit inline:

1. **`ls -la` spec absolute path:**
   ```sh
   ls -la "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md"
   ```
   Expected: file exists, size 60,533 bytes, mtime 2026-05-08.

2. **`shasum -a 256` spec:**
   ```sh
   shasum -a 256 "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md"
   ```
   Expected output: `14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75  <path>`. **HALT if hash differs — author drift detected; surface to Kim before proceeding.**

3. **Quote first 20 lines of spec verbatim** (stale-cache detector). The first non-blank line MUST be `# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1`. Capture lines 1-20 with line numbers.

4. **Companion-file integrity (anchored — header/snippet ONLY, NOT line-number):**
   - (a) `Production/lib/directus.py` — anchor: locate `def try_post_or_queue` function definition; capture line range; quote the function signature line + the first 5 lines of the body to confirm the spec's Phase 2 wire-up target exists.
   - (b) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor: locate the heading containing `prod_activity_log` AND the heading containing `prod_preflight_reviews`; capture each heading's line range + the field-enumeration list under each (LD-597 anti-confusion guards).
   - (c) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — anchor: locate `### §6 Gate 11.2` row OR `validate_prod_blockers_payload` function reference; capture line range + the validator function body to confirm the v6 narrow validator pattern that v1 generalizes.
   - (d) `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — anchor: `# Handoff v6 — Cursor Cross-Review of Schema Vocab Migration Tech Spec v6` (first line); confirm prior-review structural template lineage.
   - (e) `Production/docs/HANDOFF_TEMPLATE_v2.md` — anchor: `# Handoff Template v2` (first line); confirm template version compliance.

5. **Spec-specific anchor capture (REQUIRED for review):**
   - (i) Locate `## §0 — Operating Mode` heading; capture verbatim DESIGN-ONLY paragraph.
   - (ii) Locate `## §3 — Dual-Opus debate (REQUIRED)` heading; capture each of the 7 sub-headings (`### Decision 1` through `### Decision 7`) + the synthesis-verdict sentence at the end of each.
   - (iii) Locate `## §4 — Per-decision action table` heading; capture the 7-row verdict table verbatim.
   - (iv) Locate `## §5 — Implementation sequence (phased rollout)` heading; capture the 6 phase headings (`**Phase 0`, `**Phase 1`, `**Phase 2`, `**Phase 3`, `**Phase 4`, `**Phase 5`) + the dependency-order CONFIRMED note at the end.
   - (v) Locate `## §6 — Pre-implementation gates Kim must approve` heading; capture the 10-gate table verbatim.
   - (vi) Locate `## §7 — Risk assessment` heading; capture the 10-risk table verbatim + the "Top 3 risks" summary.
   - (vii) Locate `## §9.3 — Logging strategy (dog-fooding the validator)` heading; capture the `_VALIDATOR_INTERNAL_BYPASS` thread-local design verbatim (recursion-guard target for Task F).

If preflight 1-3 fails, HALT and report. If 4 or 5 fails for any anchor, document inline; if all anchors fail, HALT.

---

## Step 1 — Open the project in Cursor

Project root: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`. Open `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md`.

---

## Step 2 — Paste this prompt into Cursor

```
I have a tech spec at Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v1.md. This is a NEW DESIGN spec — the FIRST Cursor review of it (not a fix-set verification like v6/v7 of the schema migration chain). Spec proposes a generic schema-aware payload validator across all 30 prod_* Directus collections; generalizes the v6 narrow validator pattern (validate_prod_blockers_payload, prod_blockers-only) one architectural layer up.

Background context (informational only — do NOT re-debate):
- v6 narrow validator (`validate_prod_blockers_payload` + `ALLOWED_PROD_BLOCKERS_KEYS`) is already in production for prod_blockers and proved the runtime-validator pattern at narrow scope. Accept the generalization premise as design-sound (already in production) but rigorously review the spec's design decisions.
- The spec drives off two silent_write_failure incidents on 2026-05-08: (1) `task_description` mistakenly POSTed to `prod_activity_log` (which has 11 fields, none of which is `task_description`; the field lives on `prod_preflight_reviews`); (2) `details` and `resolution_notes` POSTed to `prod_blockers` (which has 8 fields, none of which match; structured payloads must encode in `description` as embedded JSON anchored on `STRUCTURED_DETAILS_JSON:`).
- Authority: LD-599 DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1 (filed 2026-05-08; status=active; severity=SOFT; scope_domain=infra).

The 7 decisions and v1 verdicts (per spec §3 dual-Opus debate + §4 action table):
1. Strict vs permissive default — HYBRID (strict end-state via Phase 3 warn-mode sweep)
2. Schema cache TTL — HYBRID (15-min default + invalidate hook)
3. Validator location — Counter wins (separate `lib/payload_validator.py`)
4. Probe-failure mode — Advocate wins (fail-closed + queue-on-fail)
5. Opt-in vs opt-out — Advocate wins (opt-out always-on + override file)
6. Auto-field handling — Counter wins (strip + warn + audit row + flag)
7. Retired-field grace — HYBRID (14-day grace for registered + immediate-reject for unregistered)

6-phase rollout: Phase 0 snapshot writes → Phase 1 author module + tests → Phase 2 wire into try_post_or_queue → Phase 3 ≥1 week warn-mode sweep → Phase 4 flip strict (gated on Phase 3 zero-warning) → Phase 5 docs hardening.

Apply your full independent scrutiny on the entire design surface. The runtime-validator-pattern question is locked (v6 already proves it); EVERYTHING ELSE is in scope.

PREFLIGHT (do first, emit inline) — anchored discipline:
1. Confirm spec file exists; capture size + mtime + shasum.
   Expected sha256: 14ae4e22b653f8e9fa0809048d3f308d277d29459910b0172efdd9e6670fab75
   HALT if mismatch — author drift.
2. Quote the first 20 lines of the spec verbatim with capture-line-range.
   First non-blank line MUST be: "# DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC v1"
3. Companion-file integrity (anchored header/snippet only):
   (a) `Production/lib/directus.py` — anchor `def try_post_or_queue`; capture line range + signature + first 5 body lines.
   (b) `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — anchor headings for `prod_activity_log` AND `prod_preflight_reviews`; capture both field-enumeration lists.
   (c) `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — anchor `validate_prod_blockers_payload` reference; capture validator function body.
4. Spec-specific anchor capture:
   (i) `## §0 — Operating Mode` — quote DESIGN-ONLY paragraph.
   (ii) `## §3 — Dual-Opus debate (REQUIRED)` — quote each of the 7 synthesis-verdict sentences.
   (iii) `## §4 — Per-decision action table` — quote the 7-row verdict table verbatim.
   (iv) `## §5 — Implementation sequence (phased rollout)` — quote each of the 6 phase headings + dependency-order CONFIRMED note.
   (v) `## §6 — Pre-implementation gates Kim must approve` — quote the 10-gate table verbatim.
   (vi) `## §7 — Risk assessment` — quote the 10-risk table verbatim + Top 3 summary.
   (vii) `## §9.3 — Logging strategy (dog-fooding the validator)` — quote `_VALIDATOR_INTERNAL_BYPASS` thread-local design.
If preflight 1-3 fails, HALT and report.

CONCISE→FULL ESCALATION RULE (mandatory verbatim per HANDOFF_TEMPLATE_v2):
> If any required section cannot be evidenced, full mode is mandatory.

Operational definition of "cannot be evidenced": could not read the spec; could not reproduce a §3 / §4 / §5 / §6 / §7 / §9.3 anchor (header/snippet match in actual file content); the spec section the question targets is missing or ambiguous; the reviewer's evidence is "I think" or "probably" rather than a quoted citation; the reviewer skipped a question to save tokens. Document WHICH area was under-evidenced in full-mode output.

ANALYSIS REQUIREMENTS (citation table format):
| # | Concern | Severity (CRITICAL/HIGH/MED/LOW) | Evidence (anchored citation: section header + snippet match, NOT line numbers alone) | Suggested mitigation | Blocker (Y/N) |

REQUIRED ANALYSIS TASKS — full architectural review (7 tasks, A-G):

A. DECISION VERDICTS REVIEW (7 sub-tasks, one per spec §3 decision)
   For EACH of the 7 decisions in §3 (Decision 1 through Decision 7), independently evaluate:
   (a) Is the verdict (Advocate / Counter / Hybrid) well-supported by the synthesis paragraph?
   (b) Are the tradeoffs honestly represented in BOTH the Advocate and Counter paragraphs (no straw-man positions)?
   (c) Are there decision-relevant facts missing from the debate (e.g., performance benchmarks, race conditions, security implications, operational complexity)?

   Per-decision edge cases to flag (independent scrutiny):
   - Decision 1 (strict vs permissive): is the Phase 3 warn-mode sweep duration (≥1 week) defensible? What if real-world write volume is below the threshold needed to exercise every collection's caller class within 1 week?
   - Decision 2 (cache TTL): is 15 minutes truly the right balance? What if migration scripts forget to call `invalidate_schema_cache()` at phase boundaries?
   - Decision 3 (separate module): does separating `lib/payload_validator.py` from `lib/directus.py` create a circular-import risk if the validator needs `try_post_or_queue` for its own audit-log writes?
   - Decision 4 (fail-closed + queue-on-fail): what if Directus is partially up (POST endpoint working, /fields endpoint failing)? Does the queue-on-fail wrapper handle this asymmetric outage gracefully?
   - Decision 5 (opt-out always-on): does the override file's syntax (`{collection: {mode: ..., extra_allowed_keys: [...]}}`) handle inheritance / wildcard / negation cases?
   - Decision 6 (strip-with-audit auto-fields): does the `_AUTO_FIELDS` set match the actual auto-fields on EVERY one of the 30 collections (or only on a subset)?
   - Decision 7 (14-day grace + RETIRED_FIELDS_REGISTRY): how is the registry kept in sync with actual schema migrations? What if a migration retires a field but the author forgets to add it to the registry?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 decision verdict where the synthesis IS demonstrably wrong (counter-example exists OR the dominant tradeoff was missed in the synthesis paragraph), verdict MUST be AMEND_V2 on Task A. Show the specific decision number + the missed tradeoff or counter-example.

B. PHASE PLAN REVIEW
   Confirm:
   (a) The 6 phases are dependency-ordered correctly per spec §5 dependency-order CONFIRMED note.
   (b) Phase 3 warn-mode sweep duration (≥1 week) is defensible.
   (c) Phase 4 flip-to-strict gate (zero warnings in last 7 days) is achievable.
   (d) Phase 0 inventory output format (`<file>:<line>:<collection>` flat file) is sufficient input for Phase 1 + Phase 3 sweep target list.
   (e) Phase 5 doc-hardening covers all the necessary artifacts (CLAUDE.md Rule 35 sub-section + schema-ref doc + memory file).

   Edge cases to flag (independent scrutiny):
   - **Hidden phase dependency** — does Phase 3 actually require Phase 1 + Phase 2 to be complete? Could Phase 3 start with Phase 1 ONLY (validator function exists but is not yet wired)? Spec says Phase 3 needs Phase 2 wire-up. Confirm.
   - **Phase 4 strict-promotion concurrency** — what if Phase 4 fires DURING a normal Kim work session and a script halts on `UnknownPayloadKeyError` mid-execution? Is the rollback path (edit `_resolve_mode` default from `'strict'` back to `'warn'`) fast enough?
   - **Phase 6 missing?** — is there a "Phase 6 final audit" step that's missing from the spec (the schema-migration spec chain has a Phase 6 final audit)? Or is Phase 5 doc-hardening actually combining doc + final audit?
   - **Phase that's actually 2+ phases conflated** — is Phase 1 actually Phase 1A (author module) + Phase 1B (author tests)? Should they be separate phases for testability?

   NUMERIC THRESHOLD: if Cursor identifies (i) a phase where reordering would meaningfully reduce risk OR (ii) a missing phase OR (iii) a phase that is actually ≥2 phases conflated AND would benefit from explicit decomposition, verdict MUST be AMEND_V2 on Task B. Show the specific phase + the proposed reordering or split.

C. RISK TABLE REVIEW
   Confirm:
   (a) The 10 risks in §7 cover the major failure modes (existing-script breakage, cache staleness, performance, probe failure, race conditions, auto-field stripping, opt-out over-broad, dog-fooding recursion, registry drift, per-process cache inconsistency).
   (b) Likelihood (LOW/MED/HIGH) and Severity (LOW/MED/HIGH) calibrations are defensible per risk.
   (c) Mitigations link back to specific §3 decisions or §5 phases.
   (d) Top-3 summary correctly identifies the highest severity-x-likelihood risks.

   Edge cases to flag (independent scrutiny):
   - **Schema-divergence risk** — what if Directus's `/fields/<collection>` endpoint returns different field types vs the canonical schema (e.g., a JSON column appearing as `string` in one Directus version vs `json` in another)? Does the validator's `{ff['field'] for ff in data}` set comprehension correctly handle all field types?
   - **Override-file race** — what if two Python processes are running concurrently, one editing the override file (admin-UI flow), the other reading it (production write)? Is there a file-lock pattern documented?
   - **Schema probe-cache poisoning** — what if Directus briefly returns a corrupted /fields response (truncated JSON, wrong collection name, etc.)? The cache stores the corrupted set for 15 min. Is there a sanity check (minimum field count, presence of `id`, etc.)?
   - **Activity-log saturation** — what if a buggy script fires 1000 `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN` rows in a tight loop? Does the activity-log have rate-limiting or dedup?
   - **Test-only collection bypass** — are there test/sandbox collections that should never be validated (e.g., `prod_test_*`)? The spec says default opt-out always-on; does that include test collections?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 risk that is MISSING from the table AND would be HIGH severity (severity=HIGH per the spec's likelihood-severity rubric), verdict MUST be AMEND_V2 on Task C. Show the specific missing risk + the severity rationale.

D. PERFORMANCE + SCALING REVIEW
   The spec proposes a runtime validator at every POST/PATCH. With ~21 active write-call files + 30 prod_* collections + cache TTL 15 min, estimate:
   (a) Per-write overhead in steady state (cache hit): under 5ms expected (set-difference computation, no I/O).
   (b) Per-write overhead on cache miss: 100-300ms (one HTTP round-trip to Directus `/fields/<collection>`).
   (c) Steady-state probe count per hour: ≤ (30 collections × 1 probe per 15-min TTL × 4 windows/hour) = 120 probes/hour upper bound; but realistically far fewer because most processes are short-lived (< 15 min) and only probe-on-first-write per collection.
   (d) Hot-path concern: what about bulk imports (e.g., a migration script PATCHing 110 prod_locked_decisions rows in a tight loop)? With cache hit, each PATCH adds ~5ms validator overhead → 110 × 5ms = 550ms total — acceptable. With cache miss on EACH PATCH (cache TTL expires mid-loop), worst case 110 × 300ms = 33sec — unacceptable. Mitigation: cache TTL refresh-on-access or cache warming at script start.
   (e) Cache miss rate at TTL 15 min in normal operation: most callers run < 15 min so each pays at most 1 probe → cache miss rate per write is dominated by the FIRST write per collection per process → effectively 1 / N where N is writes-per-process-per-collection.

   Edge cases to flag (independent scrutiny):
   - **Long-running daemon scripts** — if a script runs for hours (e.g., a watcher script), the cache will refresh ~4x/hour per collection. Is the steady-state cost acceptable?
   - **Multi-process parallel writes** — if Kim runs 4 scripts in parallel, each with its own process, each will probe each collection once. 4 × 30 = 120 probes at script start. Is this a concern for Directus rate-limiting?
   - **Probe latency variance** — Directus latency p99 may exceed 1sec under load. Is there a probe timeout? What's the failure mode if probe times out?

   NUMERIC THRESHOLD: if Cursor's independently estimated steady-state overhead per write > 50ms (cache hit) OR if estimated cache-miss-rate exceeds 10% in normal operation (defining "normal" as Kim's typical mix of short-lived scripts), verdict MUST be AMEND_V2 on Task D. Show the computation: assumed write rate, assumed cache TTL, assumed cache hit rate, assumed probe latency, assumed concurrency.

E. FAILURE-MODE REVIEW
   Independent scrutiny of failure modes the spec MAY not cover:
   (a) Directus is briefly down at validator probe time → spec §3 Decision 4 verdict says fail-closed at validator + queue-on-fail at wrapper. Confirm: does `try_post_or_queue` already have a queue-on-POST-failure path that this extends cleanly? What's the fail-mode if BOTH the schema probe AND the offline queue write fail (disk full, permission denied)?
   (b) Schema cache is stale and live schema removed a field → spec says 15-min TTL bounds drift. Confirm: between cache load (T=0) and cache expiry (T=15min), if a migration PATCHes the schema at T=10min, writes at T=11min would PASS the validator (cache says field exists) but FAIL at Directus (real schema says field doesn't). Is this gap acceptable, or does it warrant a per-write-on-PATCH validate-after-success-confirmation step?
   (c) Validator itself has a bug that rejects valid payloads → what's the rollback path? Spec §8 Phase 4 row says edit `_resolve_mode` default from `'strict'` back to `'warn'`. Confirm this rollback works for the validator-bug case (vs the caller-bug case the §8 row describes).
   (d) Override file is malformed (invalid JSON, wrong schema) → spec §9.2 says "missing file = default mode for all collections". What if file is PRESENT but malformed? Does the validator HALT, fall back to default, or continue with partial-parse?
   (e) Concurrent migration + production-write — what if a migration script invalidates the cache at T=0, then between T=0 and T=1ms a production-write fires? Does the production write pay a cache miss (one probe, fresh schema) or hit a transient empty-cache state?

   NUMERIC THRESHOLD: if Cursor identifies ≥1 failure mode that v1 does NOT handle gracefully (handle = explicit code path documented in spec §3/§4/§5/§7, NOT inferred from "the existing infrastructure handles it"), verdict MUST be AMEND_V2 on Task E. Show the specific failure mode + the missing handler.

F. DOG-FOODING RECURSION REVIEW
   The validator's own activity-log writes (e.g., `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN`, `PAYLOAD_VALIDATOR_AUTO_FIELD_STRIPPED`, `STALE_MUTEX_PARSE_FAILURE`-style rows) go through `try_post_or_queue` → which goes through the validator → which would re-enter the validator → infinite recursion.

   Spec §9.3 + §7 risk #8 mitigates via `_VALIDATOR_INTERNAL_BYPASS` thread-local flag. Confirm:
   (a) The thread-local pattern is correctly described — `_VALIDATOR_INTERNAL_BYPASS = threading.local()`; set to `True` before validator's own log-write; `try_post_or_queue` calls validator's entry-guard; entry-guard checks `getattr(_VALIDATOR_INTERNAL_BYPASS, 'active', False)` and bypasses; sets back to False in `finally`.
   (b) The pattern handles thread-safety correctly — each thread has its own local; concurrent validator calls in different threads do not interfere.
   (c) Phase 1 unit test verifies recursion-guard correctness (spec §15.6 "Dog-fooding recursion smoke test").

   Edge cases to flag (independent scrutiny):
   - **async/await context** — if the codebase uses asyncio, `threading.local()` does NOT track async context vars. Does the codebase use async Directus calls? Is `contextvars.ContextVar` needed instead?
   - **Exception during validator log-write** — if the validator's audit-log write itself raises (e.g., Directus down + offline queue write fails), does the `finally` block still reset `_VALIDATOR_INTERNAL_BYPASS.active = False`? Spec says yes ("Sets back to False in a `finally`") — confirm the code structure makes this guaranteed.
   - **Reentrant call from a non-validator path** — e.g., if `try_post_or_queue` is called during validator initialization (module-import-time side effect), the entry-guard might not be installed yet. Is module-import-time-write a concern? (Probably not — but worth flagging.)
   - **Testing the bypass** — does the Phase 1 unit test verify (a) recursion does NOT occur, AND (b) the bypass is properly set/reset? Or only one of the two?

   NUMERIC THRESHOLD: if Cursor identifies a recursion path that v1 does NOT guard (e.g., async context-var path; double-fault during exception in `finally`; uncaptured nested call), verdict MUST be AMEND_V2 on Task F. Show the specific recursion path.

G. BACKWARD-COMPAT REVIEW
   21 active write-call files in scope (spec §0.1 Wave A inventory). Phase 3 warn-mode sweep is supposed to surface unknown fields without breaking writes. Confirm:
   (a) The warn-mode logic flows: validator detects unknown keys → logs `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN` activity-log row → DOES NOT raise → write proceeds via `try_post_or_queue` → existing pipeline writes succeed (or silently drop the unknown key as before).
   (b) The Phase 3 exit criterion (zero `PAYLOAD_VALIDATOR_UNKNOWN_FIELD_WARN` rows in last 7 days) is achievable WITHOUT requiring every caller to be re-run by Kim manually.
   (c) The optional `Production/scripts/payload_validator_phase3_sweep.py` (Phase 3 deliverable) iterates every active write-call file's known invocation pattern — is this script actually feasible (i.e., do all 21 callers have known invocation patterns that a sweep script can mechanically exercise)?

   Edge cases to flag (independent scrutiny):
   - **Conditional write paths** — does any caller have write paths that only fire under specific conditions (e.g., error-handling paths, error-recovery PATCHes)? The Phase 3 sweep may miss these unless the sweep deliberately triggers each error condition.
   - **Computed field-name patterns** — does any caller build payloads via `{**base, "computed_" + name: value}` patterns? The validator catches these at write-time (because `payload.keys()` at write-time is the dict's actual keys), but the Phase 3 sweep may only exercise the ASSUMED happy-path keys.
   - **External contributors / Cursor-edited code** — if Cursor edits a script post-Phase-4 and adds a new field, does the validator catch this immediately on first invocation (yes — strict mode enforces on every write), OR is there a dev-time-only pre-flight option (e.g., a CLI command `python -m payload_validator dry-run <script>` that exercises a script's writes against the validator)?
   - **Migration-window transient writes** — during a schema migration's interim states (e.g., between Phase 3 enum-add and Phase 4 PATCHes in the schema-vocab migration), some writes may transiently pass an "old" field that's about to be retired. Does Phase 3 sweep window respect ongoing migrations?

   NUMERIC THRESHOLD: if Cursor identifies an existing write-call pattern (in the 21-file inventory) that the Phase 3 warn-mode logic would silently MISS (i.e., still suffer silent_write_failure even with the validator running), verdict MUST be AMEND_V2 on Task G. Show the specific caller pattern + why warn-mode wouldn't catch it.

VERDICT FORMAT (mandatory, pick exactly ONE):
- AUTHORIZE_IMPLEMENTATION — spec is sound; Phase 0 (snapshot) may proceed; subsequent phases gated on §6 Kim approvals.
- AUTHORIZE_PHASE_0_ONLY — spec is sound BUT Cursor cannot verify live Directus state; mirror prior schema-migration v3 verdict scope (Phase 0 dry-run only, with risk acceptance for Phases 1+ post-Phase 0 artifact review). NOTE: Phase 0 is non-mutating (just inventory), so equivalent to AUTHORIZE_IMPLEMENTATION for Phase 0.
- AMEND_V2 — spec has a defect; specify the defect + required v2 fix in concrete numeric terms (which Decision number, which phase, which risk row, which performance threshold, which failure mode, which recursion path, which caller pattern). NOTE: this is the FIRST Cursor review of this spec; AMEND_V2 means "v1 is the current; emit v2".
- PAUSE_FOR_REDEBATE — fundamental issue; recommend dual-Opus or expanded review (e.g., new debate on the architectural premise, OR a missing decision that requires independent debate).

Required output:
1. Preflight evidence (sha256 + first 20 lines verbatim + 5 anchored companion-file quotes + 7 spec-anchor captures).
2. Analysis table (per task A, B, C, D, E, F, G) with severity, evidence (anchored citation), mitigation, blocker Y/N.
3. Verdict (one of the four above).
4. Limitations + cross-skill drift if any.
```

---

## Step 3 — After Cursor responds

Save Cursor's verbatim response to `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_20260508.md`.

Verdict-driven next steps:

- **`AUTHORIZE_IMPLEMENTATION`** → author the implementation handoff for Phase 0 dispatch (Kim authorizes when ready). Phase 0 is non-mutating reconnaissance; subsequent phases gated on spec §6 Kim approvals (Gates 1-10).
- **`AUTHORIZE_PHASE_0_ONLY`** → equivalent to AUTHORIZE_IMPLEMENTATION since Phase 0 is non-mutating; author Phase 0 implementation handoff.
- **`AMEND_V2`** → author `Production/docs/DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_v2.md` addressing the defect(s); preserve v1 as historical baseline; re-run THIS handoff against v2 (rename + bump version refs + re-anchor sha256).
- **`PAUSE_FOR_REDEBATE`** → halt; bring findings back to Claude Code; spawn fresh dual-Opus debate on the flagged decision; do NOT proceed to implementation.

---

## Hard rules

- **Per Rule 35:** read-back-after-write for every Directus PATCH/POST (applies to handoff author logging this handoff to `prod_activity_log`; applies to Cursor reviewer if they touch Directus during analysis — they should not).
- **Multipass:** re-Read v1 spec after this handoff is authored (handoff author discipline; Cursor reviewer also re-reads if a HALT gate fires).
- **Rule 24:** confidence tags throughout (CONFIRMED / INFERRED / GUESSED).
- **DS-19 + DS-26:** always active; fire on any trigger condition. Autonomous mode does not bypass HALT gates.
- **DS-13 Layer 6:** input variation (read v6 review handoff as template + v1 payload-validator spec) → output variation (this handoff differs structurally to broaden scope from v6's surgical 5-element fix-set to a full 7-task architectural review of v1's 7 decisions + 6 phases + 10 risks).
- **DS-26 explicit:** "Autonomous mode does not bypass HALT gates. If a HALT gate fires mid-execution (e.g., gate evidence found inconsistent), STOP and surface."
- **DS-27 (absolute paths, dual-canonical):** all filesystem-touching commands MUST use absolute paths anchored to one of the two canonical roots: (1) `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/` (primary — Mindfulnest project) OR (2) `/Users/kimberlysmith/Projects/` (secondary — tooling repos, MindfulNest RN app, related repos). Do NOT operate inside `.claude/worktrees/` subdirectories under either root unless explicitly authorized. Verify paths with `ls -la <absolute-path>` before edits. All paths in this handoff are anchored to canonical root #1 (Dropbox-rooted).
- **Companion path discipline (HANDOFF_TEMPLATE_v2 §0.3):** every companion file in this handoff is listed with absolute path + canonical-root tag. All 7 companion files were probed via `ls -la` at authoring time and confirmed present under canonical root #1.
- **DS-28 dependency-order:** Wave A research (read spec + template + prior review handoff) before Wave B execution (author handoff); preflight steps 1-5 verified before Step 1; Step 1 before Step 2; Step 2 before Step 3.
- **DS-29 verification-source discipline:** every claim in the final report tagged explicitly `(my probe)` / `(agent claim)` / `(unverified)`.
- **JSON-column gotcha:** the activity-log POST below uses `details` as a dict (live `prod_activity_log.details` IS a JSON column); LD-597 anti-confusion guards: do NOT include `task_description` in the activity-log payload.
- **Anchored citation:** every preflight evidence requirement uses anchored section/header + snippet match, not absolute line number alone.
- **Concise→full escalation (mandatory):** "If any required section cannot be evidenced, full mode is mandatory." (Verbatim in Step 2 prompt.)
- **Numeric AMEND_V2 thresholds (mandatory):** Tasks A, B, C, D, E, F, G all have explicit numeric triggers tied to AMEND_V2 verdicts.
- **Multipass-Read after authoring:** handoff author re-reads this handoff post-authoring to confirm structural integrity.
- **Halt-and-surface if spec sha256 has changed since session-record:** preflight Gate 1 catches this.

---

## Final report — required structure

Path: `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/docs/CURSOR_REVIEW_PAYLOAD_VALIDATOR_SPEC_REPORT_20260508.md`

Required sections:

1. **HALT gate scan results** — 5 gates (sha256 match, first-line verbatim, companion-anchor verification, §0 Operating Mode "DESIGN ONLY" confirmed, LD-599 active confirmed).
2. **Cursor verdict verbatim** — exact pasted Cursor response.
3. **Per-task summary** — A, B, C, D, E, F, G, each with verdict + anchored evidence + numeric-threshold result where applicable.
4. **Confidence tags per Rule 24.**
5. **Self-classification** — REVIEW (Cursor's classification of its own analysis).
6. **Limitations** — what wasn't covered (live Directus state if unreachable from Cursor's environment; the runtime-validator pattern itself excluded from re-debate per spec context).
7. **Cross-skill drift** — does v1's generic-validator pattern require parallel updates to weekly_preflight_audit.py, zero-error-qa SKILL.md, tech-spec SKILL.md, or HANDOFF_TEMPLATE_v2.md?
8. **Next-step recommendation.**

---

## Cross-references

- `LD-590` (`SCHEMA_VOCAB_MIGRATION_V3_LOCKED`) — v3 design surface authorization (context).
- `LD-595` (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1`) — v5 field-name fix (driving incident #2).
- `LD-596` (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1`) — v6 narrow validator authority (the pattern v1 generalizes).
- `LD-597` (`TASK_DESCRIPTION_FIELD_ANTI_CONFUSION_GUARDS_V1`) — anti-confusion guards (driving incident #1).
- `LD-598` (`SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR`) — v7 spec extractor (context).
- `LD-599` (`DIRECTUS_PAYLOAD_VALIDATOR_TECH_SPEC_V1`) — **spec authority for THIS review**.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md` — structural template for THIS handoff; v6 review returned AMEND_V2.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v7.md` — v7 review handoff; same structural lineage.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 narrow validator (the pattern v1 generalizes).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 spec (context).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure mandate (this handoff conforms).
- `Production/lib/directus.py` — Phase 2 wire-up target.
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` — live schema authority.

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Full architectural review (NOT surgical fix-set verification): 7 analysis tasks (A through G) covering spec §3 (7 decisions) + §5 (6 phases) + §7 (10 risks) + performance/scaling + failure modes + dog-fooding recursion + backward-compat. Numeric AMEND_V2 thresholds on ALL 7 tasks. Structural template: `HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v6.md`. Author: Claude Opus 4.7 (1M context), session `gallant-bouman-804b4f`.
