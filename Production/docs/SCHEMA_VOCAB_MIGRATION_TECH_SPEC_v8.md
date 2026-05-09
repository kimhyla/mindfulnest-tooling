# Schema Vocab Migration — Tech Spec v8

**Authored:** 2026-05-09 (post-CLI-dispatch session that ran Phase A through Phase F clean and HALTed before Phase G rehearsal per Kim's explicit direction).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ROUTINE (documentation amendment over v7; no design change, no script change, no execution-gate change; corrects two documentation defects surfaced by live data during the CLI dispatch session).
**Status:** DESIGN ONLY — execution remains gated on the same Phase 5 PHASE_5_ENABLED feature flag + §6 Gates 1-12 (preserved verbatim from v7) + Phase G rehearsal authorization that v7 mandated.

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` (preserved as historical baseline; do NOT edit in place). v7 in turn supersedes v6; v6 supersedes v5; v5 supersedes v4; v4 supersedes v3; v3 supersedes v2; v2 supersedes v1. v1-v7 all preserved as historical record.

**v7 → v8 driver:** the CLI dispatch session 2026-05-08 / 09 (executed Phase A through Phase F clean, HALTed before Phase G rehearsal per Kim's directive) surfaced **two documentation defects in v7** that did not affect script correctness (`migrate_schema_vocab_v1.py` already partitioned correctly per spec §3.3 verdict + already accepted Kim's Rule 4 spec-extensions live) but DID affect spec readability for any future implementer reading v7 in isolation:

1. **Defect 1 — §4 EXPECTED_ROW_COUNTS Rule 3b conflated mechanical and INVESTIGATE-class rows.** v7 §4 cites `rule_3b_task_category_remap = 110` rows. Live data shows the actual mechanically-eligible count is **56** rows; the other **68 rows** (`production_infrastructure` 35, `production_pipeline` 26, `tools` 6, `feature` 1) are INVESTIGATE-class per spec §3.3 verdict and require per-row Kim triage BEFORE any auto-PATCH. The 110 figure mixed both classes. The CLI script's mechanical-only partition (56 rows) is correct per spec §3.3 verdict; v8 corrects the spec-side EXPECTED_ROW_COUNTS to match.
2. **Defect 2 — §3.4 Rule 4 scope_domain mapping table omitted 3 production-* mappings.** v7 §3.4 enumerated 11 mappings (29 rows). Live data showed 3 additional source values present that the script needed to handle: `production-server` (3 rows; dash variant matching `production_server_infrastructure` semantic per cleanup-report) → `infra`, `production_pipeline` (1 row) → `production`, `audio_production` (1 row) → `production`. These were dispatched live by the CLI script with origin tag "spec-extension (Kim 2026-05-09)" per Kim authorization in chat. v8 codifies them into §3.4 verbatim so the spec is self-consistent with live behavior.

v8 corrects ONLY these two documentation defects. All other v7 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H, severity case-fold, Gate 11.1, runtime validator Gate 11.2, hazard warnings, schema_version, ≤256-char cap, JSON-string-aware state-machine extractor) preserved verbatim. v1-v7 preserved as historical baselines.

**Related artifacts (preserved from v7 + v8 additions):**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — **v7 historical baseline (this spec's predecessor)** (v8 NEW reference); sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`, 498 lines, 59,307 bytes.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline (v7 reference; v8 preserved); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline; sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline; sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline; sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline; sha256 `3d39b7c5ead3c1c0d0f0876a294f16042f3f9c7a72a8b721bb8e148da7f361c9`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `e88e82eaea03e6d4837cc41438361491c00c32155d3d09efcd5353f585e2aa5b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` — **CLI dry-run report** (v8 NEW reference); contains drift table + Rule 4 origin column + INVESTIGATE-class triage queue verbatim from the CLI session.
- `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` — **CLI session report** (v8 NEW reference); records Phase A→F execution, Kim's drift-resolution authorization, mechanical halt #2 fire+resolution, prod_blockers id=103 fire+resolve, prod_activity_log row 1826 audit trail.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl` — snapshot file referenced by the CLI session; snapshot_hash `f5ae2c3a150c45491f215071ce5e4e9ccacb01a20e6f9a98d7e598982925769f` (per dry-run report header).
- `Production/exports/prod_locked_decisions_2026-05-09.jsonl` — cached canonical-export from CLI session (562 rows; supersedes 2026-05-08 export per CLI report §7).
- `Production/scripts/migrate_schema_vocab_v1.py` — **migration script** (1850 lines, py_compile clean per CLI report §3); v8 codifies the partition and Rule 4 extensions the script already implements correctly.
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. Currently at v2.5 (this session: §1-area Header bullet sha256 reference updated from spec v3 stale SHA-1 to spec v8 sha256 + §11 v2.5 versioning entry appended). v2.4 cited v7; v2.5 amends to cite v8.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed.
- `Production/scripts/lock_decision.py` — LD-writer CLI; canonical-aware as of 2026-05-08 per Cursor v3 Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-fix backup.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating helper-import.
- `LD_WRITER_CANONICAL_VOCAB_V1` (LD #588) — LD filed 2026-05-08 documenting the lock_decision.py canonical-aware fix (HARD severity).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section.
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (lowercase severity + STRUCTURED_DETAILS_JSON workaround); v8 §9.4 cross-references this LD via v7's preserved chain.
- `LD-593` — v4 §9.4 severity case-fold authority (preserved through v5 → v6 → v7 → v8).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority (preserved through v8).
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority (preserved through v8).
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — anti-confusion guard for `prod_activity_log.task_description` non-existence; v8 inherits the guidance verbatim (do NOT include `task_description` in any `prod_activity_log` POST; `details` (JSON dict) is the canonical narrative carrier).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — v7 Cursor AMEND_V3 fix authority (preserved through v8 since the state-machine extractor remains in effect).
- `LD-601` — Phase 3 row 101 idempotent resolution authority (referenced by CLI report §3 Phase K row).
- `LD-602` — F3-fix predecessor cleanup LD (referenced by CLI report §1 evidence row 1; the v3 stale-SHA-1 reference in handoff §1-area Header was superseded by handoff v2.4 amendments per LD-602; v8 + handoff v2.5 close out the documentation drift completely).
- `LD-NEW (this session) SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` — **v8 amendment authority** (v8 NEW reference; filed 2026-05-09 same session as v8 spec authoring; LD id captured at file time).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for v7 §9.4 (and now v8 §9.4 via preservation). Schema-ref doc §5 currently cites LD-596 (v6) + LD-598 (v7); LIKELY does NOT need a v8 update because v8 introduces no schema-side change. (v8 does NOT update the schema-ref doc.)
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion (preserved through v7 → v8).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (preserved as v8's review companion since the cumulative review trail remains anchored at the v3 review handoff; v8 is a documentation amendment landing on the v7 surface).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export.
- `prod_activity_log` id=1826 — Kim's drift-resolution authorization marker (CLI session); the auditable trail of the Rule 3b 110→56 amendment + Rule 4 spec-extension origin tags.
- `prod_blockers` id=103 — drift-fire-and-resolve mechanical halt #2 audit row from CLI session (resolved 2026-05-09T02:48:36 per Kim authorization).

---

## §0.1 — v8 Changelog (single-row amendment over v7)

v8 is a documentation amendment over v7 addressing 2 documentation defects surfaced by the CLI dispatch session 2026-05-08 / 09 (Phase A through Phase F clean; HALTed before Phase G rehearsal per Kim's directive). No script change, no design change, no execution-gate change. v7's §0.1 changelog is preserved verbatim immediately below this v8 entry, followed by v6's, v5's, v4's, v3's.

| # | v8 amendment (CLI dispatch session findings) | Resolution applied in v8 | Sections changed |
|---|---|---|---|
| v8-A | **Defect 1 (documentation only) — v7 §4 EXPECTED_ROW_COUNTS conflated mechanical and INVESTIGATE-class rows for Rule 3b.** v7 cited `rule_3b_task_category_remap = 110` rows. Live count of mechanically-eligible rows = 56 (architectural→app_architecture 33, audio_production→audio 4, production_server→infrastructure 2, production_server_infrastructure→infrastructure 14, video_production→video 3). Remaining 68 rows (`production_infrastructure` 35, `production_pipeline` 26, `tools` 6, `feature` 1) are INVESTIGATE-class per spec §3.3 verdict — NOT auto-PATCHed; Kim per-row triage required. CLI script's partition is correct per spec §3.3 verdict; the v7 EXPECTED_ROW_COUNTS figure mixed both classes. | v8 §3.3 ADDS an explicit partition callout stating that the spec's earlier "~110 rows" estimate conflated the two classes. v8 §3.3.1 is a NEW subsection enumerating the 68 INVESTIGATE-class rows in a 4-row triage table. v8 §4 corrects EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"] from 110 to 56. v8 §7 ADDS risk #17 documenting the implementer-drift hazard if a future reader copies the v7 110 figure and auto-PATCHes the 68 INVESTIGATE-class rows. v8 §11 reference index adds CLI dispatch session report path + LD-NEW. v8 §12 changelog appends v8 entry. | §3.3 (NEW partition callout near end), §3.3.1 (NEW subsection — INVESTIGATE-class triage table), §4 (EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"] 110→56 + ["rule_4_scope_domain_remap"] 29→35), §7 risk #17 (NEW), §11 reference index (CLI session report + LD-NEW), §12 changelog |
| v8-B | **Defect 2 (documentation only) — v7 §3.4 Rule 4 scope_domain mapping table omitted 3 production-* mappings.** v7 enumerated 11 mappings (29 rows). Live data showed 3 additional source values: `production-server` (3 rows; dash variant matching `production_server_infrastructure` semantic per cleanup-report) → `infra`; `production_pipeline` (1 row) → `production`; `audio_production` (1 row) → `production`. CLI script dispatched these live with origin tag "spec-extension (Kim 2026-05-09)" per Kim authorization in chat 2026-05-09. | v8 §3.4 ADDS 3 rows to the Rule 4 mapping table at the end, each tagged with origin "spec-extension (Kim 2026-05-09)". v8 §4 EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] updated 29→35. The CLI session's drift table reflects the actual live count of 35 rows touched (vs. v7 expected 29; +6 delta = 20.69% drift, within 25% threshold). | §3.4 (3 NEW rows at end + origin column), §4 (EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35), §11 reference index entries cited by §3.4 (no NEW entries beyond what v8-A adds), §12 changelog |

**v7 vs v8 surface area:** v8 adds ~80 lines net (one §0.1 v8 row above v7's, one §3.3 v8 partition callout block, one §3.3.1 NEW subsection with 4-row triage table, one §3.4 v8 amendment block adding 3 rows + origin column, two §4 EXPECTED_ROW_COUNTS edits, one §7 risk #17 row, ~5 §11 reference-index entries, one §12 changelog entry). v8 deletes nothing structurally — it preserves all v7 content verbatim and adds documentation. The substantive script-affecting change is exactly ZERO: the migration script (`migrate_schema_vocab_v1.py`) already partitions correctly per spec §3.3 verdict and already accepts Kim's Rule 4 spec-extensions live (per CLI report §4.1). v8 codifies live behavior into the spec so any future implementer reading v8 in isolation has self-consistent documentation.

---

## §0.1 (v7, preserved verbatim) — v7 Changelog (Cursor AMEND_V3 fix-set on v6: Blocker F)

(Preserved verbatim from v7 §0.1 v7-A row. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` §0.1 v7-A row for the full Blocker F resolution covering the JSON-string-aware state-machine extractor.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v7 row references the v7 example bodies which include the JSON-string-aware state-machine `extract_structured_payload`. v7 §9.4 IS AUTHORITATIVE for parser implementation. v8 introduces no parser change. See §6 Gate 11.2 (runtime validator, unchanged from v6) for write-time enforcement.

---

## §0.1 (v6, preserved verbatim) — v6 Changelog (Cursor AMEND_V2 fixes)

(Preserved verbatim from v6 §0.1 v6 row. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` §0.1 v6 changelog table for the full row covering Blockers A + B + F + non-blockers D + E.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v6 row references the v6 example bodies which include the brace-counter `extract_structured_payload` that v7 has hardened. §9.4 v7 IS AUTHORITATIVE (preserved through v8). See §6 Gate 11.2 (runtime validator, unchanged from v6) for write-time enforcement.

---

## §0.1 (v5, preserved verbatim) — v5 Changelog (single-row amendment over v4)

(Preserved verbatim from v6 §0.1 v5 section. The v5 row covers the §9.4 field-name fix replacing `details` with `description+STRUCTURED_DETAILS_JSON` and replacing `resolution_notes` with `description` append.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v5 row references example bodies that predate v6's parser hardening AND v7's JSON-string-aware state machine. §9.4 v7 IS AUTHORITATIVE (preserved through v8).

---

## §0.1 (v4, preserved verbatim) — v4 Changelog (single-row amendment over v3)

(Preserved verbatim from v6 §0.1 v4 section. The v4 row covers the §9.4 severity case-fold from `CRITICAL` to lowercase `critical`.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v4 row + the example bodies it points to predate v5's field-name fix, v6's parser/validator/cap/schema_version hardening, and v7's JSON-string-aware state machine. §9.4 v7 IS AUTHORITATIVE (preserved through v8).

---

## §0.1 (v3, preserved verbatim from v4 → v5 → v6 → v7 → v8) — v3 Changelog (Cursor amendment resolution table)

(Preserved verbatim from v6 §0.1 v3 section. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` §0.1 v3 changelog table for the full Tasks B/D/E/F/H rows.)

> **HAZARD WARNING — do not implement from this preserved historical row.** The v3 row + every example body it carries forward predate v4's case-fold, v5's field-name fix, v6's parser/validator hardening, and v7's JSON-string-aware state machine. §9.4 v7 IS AUTHORITATIVE (preserved through v8).

---

## §1 — Goal (preserved verbatim from v1 + v2 + v3 + v4 + v5 + v6 + v7)

(Preserved verbatim from v7 §1. Five-bullet goal statement + non-goals list. v8 introduces no §1-level changes — it is a documentation amendment, not a goal-shifting amendment.)

---

## §2 — Background (preserved verbatim from v1 + v2 + v3 + v4 + v5 + v6 + v7)

(Preserved verbatim from v7 §2. Cleanup-report baseline + v3 ADD on lock_decision.py + v4 ADD on prod_blockers row 101 + v5 §9.4 informational note + v6 ADD on parser/validator/lint hardening + v7 ADD on JSON-string-aware state machine.)

**v8 ADD (informational):** the CLI dispatch session 2026-05-08 / 09 executed Phases A through F clean and HALTed before Phase G rehearsal per Kim's directive. The dry-run drift table was clean (Rule 1 4.38%, Rule 2 2.7%, Rule 3b 0.0%, Rule 4 20.69% — all under the 25% threshold). Two documentation defects surfaced during execution and triggered the v8 amendment: (1) Rule 3b EXPECTED_ROW_COUNTS conflated mechanical and INVESTIGATE-class rows (110 vs. 56-mechanical-only); (2) Rule 4 mapping table omitted 3 production-* sources (`production-server`, `production_pipeline`, `audio_production`). Both defects are documentation-only — the CLI script (`migrate_schema_vocab_v1.py`) partitioned correctly per spec §3.3 verdict and accepted Kim's Rule 4 spec-extensions live with origin tag "spec-extension (Kim 2026-05-09)". No script change, no design change. v8 codifies live behavior into the spec so any future implementer reading v8 in isolation has self-consistent documentation.

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments (preserved in v3 + v4 + v5 + v6 + v7 + v8)

(Preserved verbatim from v7 §3. §3.0 path discipline / §3.1 Rule 1 + PHASE_5_ENABLED / §3.2 Rule 2 — all preserved through v8. v8 amends §3.3 (Rule 3 task_category) with a partition callout and adds §3.3.1 NEW subsection. v8 amends §3.4 (Rule 4 scope_domain) with 3 NEW spec-extension rows + an origin column.)

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` §3.0-§3.4 for the v2-baseline verbatim text. v3 ADD + v4-v7 preserved-narrative live in their respective spec files. v8 amendments below.

### §3.3 v8 amendment (Rule 3 task_category — partition clarification)

(Preserved verbatim from v7 §3.3 / v3 §3.3 dual-Opus debate body + verdict. v8 ADDS the following partition callout near the end of §3.3 verdict, immediately before the §3.3 close.)

> **v8 partition clarification (informational; no design change):** the spec's earlier "~110 rows" estimate for Rule 3b conflated mechanical synonym remaps (56 rows) with INVESTIGATE-class rows (68 rows: `production_infrastructure` 35, `production_pipeline` 26, `tools` 6, `feature` 1). The 68 INVESTIGATE-class rows are NOT auto-remapped; they require per-row Kim triage per the existing §3.3 verdict (SPLIT for `production_infrastructure` — drain → `infrastructure`, widgets → `production_tool_ui`; INVESTIGATE for `production_pipeline` and `tools` — overlap with `production_infrastructure` and `production_tool_ui`; per-row review for the lone `feature` row). v8 §4 EXPECTED_ROW_COUNTS reflects only the 56 mechanical-eligible count for `rule_3b_task_category_remap`. The 68 INVESTIGATE-class rows are documented as a separate triage queue at §3.3.1 below. The CLI dispatch session 2026-05-08 / 09 surfaced the partition during dry-run drift evaluation: the script's mechanical-only count of 56 matched expected after Kim's 2026-05-09 authorization to amend `EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"]` from 110 to 56 (per `prod_activity_log` id=1826 + `prod_blockers` id=103 fire-and-resolve trail).

### §3.3.1 — INVESTIGATE-class triage queue (v8 NEW)

The 68 rows below are NOT auto-PATCHed by Phase 4. They are surfaced for Kim's per-row triage per the §3.3 dual-Opus debate verdict. Disposition column references the existing §3.3 verdict guidance.

| task_category | Row count | Disposition |
|---------------|-----------|-------------|
| `production_infrastructure` | 35 | Per-row Kim triage; cleanup-report §5.X candidates (spec §3.3 verdict: SPLIT — drain → `infrastructure`, widgets → `production_tool_ui`) |
| `production_pipeline` | 26 | Per-row Kim triage (spec §3.3 verdict: INVESTIGATE — overlap with `production_infrastructure`) |
| `tools` | 6 | Per-row Kim triage (spec §3.3 verdict: INVESTIGATE — overlap with `production_tool_ui`) |
| `feature` | 1 | Per-row Kim triage (spec §3.3 verdict: too generic; per-row review) |
| **Total** | **68** | Triage-queue (NOT auto-PATCHed by Phase 4) |

**§3.3.1 cross-references:** CLI dispatch session report `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` §4.2 lists these 68 rows verbatim with the same dispositions. The dry-run report `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` §3 enumerates the same 4 task_category values. Both reports are auditable archives of the live CLI behavior; v8 codifies them into the spec body. LD-NEW (this session) is the LD authority; LD-602 is the F3-fix predecessor cleanup LD that motivated re-reading the spec for partition consistency.

### §3.4 v8 amendment (Rule 4 scope_domain — 3 new spec-extension mappings)

(Preserved verbatim from v7 §3.4 / v3 §3.4 dual-Opus debate body + verdict + 11-row mapping table. v8 ADDS the following 3 rows at the end of the existing 11-row mapping table + adds an Origin column to the table for transparency.)

| Source value | Target | Row count | Origin |
|--------------|--------|-----------|--------|
| `app` | `app-dev` | 13 | spec §3.4 v3 verbatim |
| `audio_pipeline` | `production` | 1 | spec §3.4 v3 verbatim |
| `beat_generator` | `production` | 1 | spec §3.4 v3 verbatim |
| `ci_pipeline` | `infra` | 1 | spec §3.4 v3 verbatim |
| `claude_session_behavior` | `cross-cutting` | 1 | spec §3.4 v3 verbatim |
| `governance` | `cross-cutting` | 2 | spec §3.4 v3 verbatim |
| `image_pipeline` | `production` | 1 | spec §3.4 v3 verbatim |
| `infrastructure` | `infra` | 6 | spec §3.4 v3 verbatim |
| `payments` | `app-dev` | 1 | spec §3.4 v3 verbatim |
| `stillgen` | `production` | 2 | spec §3.4 v3 verbatim |
| `video_pipeline` | `production` | 1 | spec §3.4 v3 verbatim |
| `production-server` (dash variant) | `infra` | 3 | **spec-extension (Kim 2026-05-09);** matches `production_server_infrastructure` semantic per cleanup-report. CLI dry-run report §4 origin column tags the 3 rows verbatim. |
| `production_pipeline` | `production` | 1 | **spec-extension (Kim 2026-05-09);** semantic match to `*_pipeline → production` family. CLI dry-run report §4 origin column tags the row verbatim. |
| `audio_production` | `production` | 1 | **spec-extension (Kim 2026-05-09);** semantic match to `audio_pipeline → production`. CLI dry-run report §4 origin column tags the row verbatim. |
| **Total** | — | **35** | (11 spec-§3.4-verbatim mappings = 29 rows + 3 spec-extension mappings = 6 rows; total 35 rows mapped) |

**§3.4 v8 cross-references:** CLI dispatch session report `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` §4.1 documents Kim's authorization for the 3 spec-extensions verbatim. The dry-run report `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` §4 (Rule 4 table) tags each of the 3 spec-extension rows with origin column "spec-extension (Kim 2026-05-09)". The 20.69% drift between v7-expected (29) and live (35) was within the 25% mechanical-halt threshold; no halt fired. v8 codifies the +6 delta into the spec.

---

## §4 — Per-rule action table (v7 preserved + v8 EXPECTED_ROW_COUNTS corrections)

(Preserved verbatim from v7 §4. Rules 1/2/3a/3b/4 with v3 prerequisite columns + v2 expanded snapshot schema reference. v8 introduces TWO §4-level changes: EXPECTED_ROW_COUNTS dict updates per §3.3.1 partition + §3.4 spec-extensions.)

See v3 §4 / v4 §4 / v5 §4 / v6 §4 / v7 §4 for the verbatim per-rule action narrative.

### §4 v8 — EXPECTED_ROW_COUNTS dict (current authoritative values)

The migration script's `EXPECTED_ROW_COUNTS` dict (referenced in §5 Phase 0 Step 2 dry-run drift evaluation) is now:

```python
EXPECTED_ROW_COUNTS = {
    "rule_1_severity_high_critical_to_hard": 320,        # preserved from v7 (Phase 5 deferred per spec §3.1)
    "rule_2_severity_lowercase_to_upper": 37,            # preserved from v7
    "rule_3b_task_category_remap": 56,                   # v8 CORRECTED — was 110 in v7; partition per §3.3.1 separates 68 INVESTIGATE-class rows
    "rule_4_scope_domain_remap": 35,                     # v8 CORRECTED — was 29 in v7; +6 per §3.4 spec-extensions (Kim 2026-05-09)
}
```

**v8 §4 cross-references:** CLI dispatch session report §4 drift table compares EXPECTED_ROW_COUNTS (v8-corrected values above) against actual touched-row counts: Rule 1 320 expected / 306 actual / 4.38% drift; Rule 2 37 expected / 38 actual / 2.7% drift; Rule 3b 56 expected / 56 actual / 0.0% drift; Rule 4 35 expected / 35 actual / 0.0% drift. All four rules within the 25% mechanical-halt threshold. (Note: prior to v8, the live drift table compared against v7 figures of 110 + 29 — that comparison fired mechanical halt #2 with 49.09% Rule 3b drift on the first run; resolved 2026-05-09T02:48:36 per Kim authorization to amend the EXPECTED_ROW_COUNTS values, and the second-run drift table is the clean one cited above. See CLI report §2 mechanical-halts log + §5.1 prod_activity_log id=1826.)

---

## §5 — Migration sequence (preserved verbatim from v3 + v4 + v5 + v6 + v7)

> **§5-LEVEL HAZARD WARNING (preserved verbatim from v6 with v7 update + v8 informational note):** §5 below preserves v3+v4+v5+v6+v7 example body code blocks BY REFERENCE (not inline). Any reader who follows the v3/v4/v5/v6/v7 reference back WILL find historical POST bodies that include defects v7 has fixed (v3 era: non-existent `details` key, unguarded `json.loads`, brittle regex; v6 era: brace counter that ignores JSON string state). **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** §9.4 v7 IS AUTHORITATIVE (preserved through v8). The migration script's Phase 1 entry-guard (and every other `prod_blockers` POST/PATCH) MUST use the v7 §9.4 patterns: JSON-string-aware state-machine extractor (replaces v6 brace counter) + try/except for parsing, runtime payload-key validator before write, capped resolution-text append, schema_version="v1" on acquisition. See §6 Gate 11.2 for the write-time runtime validator that prevents non-existent-field payloads from reaching Directus regardless of which historical block the implementer copy-pasted from. **v8 informational note:** the migration script's mechanical halts (#1 rehearsal-fail, #2 drift>25%, #3 Directus offline, #4 PATCH+read-back mismatch) are unchanged from v7. v8 adjusts only EXPECTED_ROW_COUNTS values (referenced by mechanical halt #2 evaluator); the halt mechanism itself is preserved verbatim.

(Preserved verbatim from v7 §5. §5.0 checkpoint protocol / Phase 0 Steps 0/1/2/3/0.4/0.5 / Phase 1-6 — all preserved through v8.)

**v4 NOTE preserved through v8:** the Phase 1 entry-guard code block in v3 §5 contains a `severity="CRITICAL"` literal in the mutex POST. Per v4 §9.4 (case-fold), this string MUST be lowercase `"critical"` at script-write time.

**v5 NOTE preserved through v8:** the Phase 1 entry-guard code block in v3 §5 (and v4's narrative carrying it forward) also references a `details` key on the `prod_blockers` POST. Per v5 §9.4 (field-name fix), this key MUST be REMOVED at script-write time and the structured payload (`host`, `pid`, `started_at`, `script_version`) MUST be encoded inside `description` as a `STRUCTURED_DETAILS_JSON:`-anchored JSON literal.

**v6 NOTE preserved through v8:** v5's stale-mutex parser used a brittle regex + raw `json.loads`, and v5's Gate 11.2 was a grep-only lint. Per v6 §9.4 + §6 Gate 11.2, the migration script's Phase 1 entry-guard implementation MUST use: (1) balanced-brace JSON extractor for any `STRUCTURED_DETAILS_JSON:` parsing; (2) `try/except json.JSONDecodeError` with graceful fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log row; (3) runtime `validate_prod_blockers_payload(payload)` invoked immediately before every POST/PATCH to `prod_blockers`; (4) `schema_version: "v1"` in the acquisition payload; (5) ≤256-char cap on resolution-text append.

**v7 NOTE preserved through v8:** v6's balanced-brace extractor uses a raw depth counter that ignores JSON string state (Cursor AMEND_V3 Blocker F). Payloads where a `}` (or `{`) appears inside a JSON string value — e.g. `{"notes":"contains } brace","pid":123,...}` — are mis-sliced at the in-string `}`. Per v7 §9.4, the migration script's stale-mutex parser MUST use the JSON-string-aware state machine: track `in_string` (toggled on UNESCAPED `"`) and `escape` (set on `\\` inside a string; cleared on next char); count `{`/`}` only when `not in_string`. v7 §9.4 callout is the authoritative source. The acquisition POST + release PATCH + Gate 11.2 validator are unchanged from v6.

**v8 NOTE (NEW; informational only):** v8 introduces no §5-level changes beyond the EXPECTED_ROW_COUNTS edits in §4. Phase 0 Step 2 dry-run drift evaluation now compares against v8 figures (Rule 3b=56, Rule 4=35) per §4 v8. The CLI dispatch session 2026-05-08 / 09 ran Phases A through F (mapping to spec §5 Phase 0) clean after Kim's 2026-05-09 authorization to update EXPECTED_ROW_COUNTS. Phases G + 1-6 remain DEFERRED per Kim's "HALT before Phase G" directive; resume requires fresh dispatch.

See v3 §5.0 + Phase 0 + Phase 1-6 for the verbatim text.

---

## §6 — Pre-implementation gates Kim must approve (v7 preserved verbatim through v8)

(Gates 1-9 preserved verbatim from v2. Gates 10/11/12 preserved verbatim from v3. Gate 11.1 preserved verbatim from v4. Gate 11.2 REPLACED in v6; preserved verbatim through v7 → v8.)

> **§6-LEVEL HAZARD WARNING (preserved verbatim from v6 with v7 update + v8 informational note):** every gate row below that points back at a v3/v4/v5/v6/v7 example body is pointing into preserved historical content. **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** §9.4 v7 IS AUTHORITATIVE (preserved through v8). Gate 11.2 v6 is the load-bearing write-time enforcement (runtime validator, not grep) — preserved verbatim through v8.

(Preserved verbatim from v7 §6. Gates 1-9 + 10 + 11 + 11.1 + 11.2 + 12 + verification artifacts. v8 introduces no §6-level changes — gate semantics, validator function, and verification artifacts unchanged.)

See v7 §6 for the full Gates 1-12 + verification artifacts text. v8 amends nothing here.

---

## §7 — Risk assessment (v7 preserved + v8 risk #17 added)

(Rows 1-9 preserved verbatim from v2. Rows 10/11/12 preserved verbatim from v3. Row 13 preserved verbatim from v4. Row 14 preserved verbatim from v5 with v6 likelihood-condition clarification. Row 15 preserved verbatim from v6. Row 16 preserved verbatim from v7. Row 17 NEW in v8.)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| **(v3 — #10)** Rollback rehearsal passes on 5 sampled rows but actual rollback fails on the remaining 315 rows due to row-specific quirks | LOW | HIGH | Preserved verbatim from v7. |
| **(v3 — #11)** Remote mutex acquisition succeeds but mutex is never released due to script crash | LOW | MEDIUM | Preserved verbatim from v7. |
| **(v3 — #12)** Checkpoint file corrupted mid-write causes resume algorithm to crash or skip valid rows | LOW | MEDIUM | Preserved verbatim from v7. |
| **(v4 — #13)** Spec author or implementer copy-pastes uppercase `CRITICAL` from v3 example into mutex POST | LOW | HIGH | Preserved verbatim from v7. |
| **(v5 — #14; v6 likelihood condition clarified; preserved through v8)** Spec author or implementer copy-pastes v3/v4 example body containing a `details` or `resolution_notes` field on a `prod_blockers` POST/PATCH | LOW (with v6 hardened lint) | HIGH | Preserved verbatim from v7. |
| **(v6 — #15; preserved through v8)** Stale-mutex cleanup helper encounters malformed/unparseable `STRUCTURED_DETAILS_JSON:` block | LOW | MEDIUM | Preserved verbatim from v7. |
| **(v7 — #16; preserved through v8)** Migration script implementer copies v6 brace-counter extraction snippet despite v7 amendment; payloads with in-string braces mis-slice | LOW | HIGH | Preserved verbatim from v7. |
| **(v8 NEW — #17)** Spec author or implementer reads v7's `~110` estimate for Rule 3b and partitions wrong (auto-PATCHes the 68 INVESTIGATE-class rows that should be triaged manually). Failure mode: the 68 rows (`production_infrastructure` 35, `production_pipeline` 26, `tools` 6, `feature` 1) get auto-remapped to whatever the implementer's read of "Rule 3b synonym remap" suggests (likely `production_tool_ui` for some, `infrastructure` for drain-class within `production_infrastructure`, `production_tool_ui` for `tools`, etc.) without per-row review. Result: semantically-wrong `task_category` values written across 68 rows; Phase 6 final audit may pass row-count reconciliation (writes did happen) but the values are wrong; rollback requires snapshot-driven row-by-row PATCH-revert. | LOW (with v8 §3.3.1 explicit partition table + §4 EXPECTED_ROW_COUNTS = 56 for Rule 3b + risk row + handoff §6 prod_blockers schema gotchas reference + LD-NEW + CLI dispatch session report §4.2 verbatim INVESTIGATE-class enumeration) | HIGH (auto-PATCHing INVESTIGATE-class rows would write semantically-wrong values that require snapshot-driven rollback to recover) | (1) v8 §3.3.1 explicit 4-row triage table enumerates the 68 rows with their dispositions; (2) v8 §4 EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"] = 56 (mechanical-only) so the dry-run drift evaluator catches any implementer attempt to remap all 124 rows (would show 121% drift, well over 25% threshold); (3) this risk row enumerates the failure mode + recovery path; (4) CLI dispatch session report `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` §4.2 documents the live partition; (5) handoff §6 prod_blockers schema gotchas (v2.5 amendment this session) cites v8 + LD-NEW; (6) LD-NEW records the divergence as a permanent gotcha. Severity HIGH because INVESTIGATE-class rows have semantic ambiguity that requires Kim's per-row judgment; auto-PATCH bypasses this. Likelihood LOW because v8's explicit partition + EXPECTED_ROW_COUNTS = 56 + drift halt + handoff cross-reference + LD form a multi-layer redundancy. |

---

## §8 — Rollback per phase (preserved verbatim from v3 + v4 + v5 + v6 + v7)

(Preserved verbatim from v7 §8. Per-phase rollback narrative + v3 rehearsal-tied addendum. v8 introduces no §8-level changes — rollback mechanism unchanged.)

See v3 §8 / v4 §8 / v5 §8 / v6 §8 / v7 §8 for the verbatim text.

---

## §9 — Operational notes (v7 preserved through v8)

(§9.1, §9.2, §9.3 preserved verbatim from v2 through v3 through v4 through v5 through v6 through v7 through v8. §9.4 preserved verbatim from v7 — JSON-string-aware state-machine extractor + acquisition POST + release PATCH + stale-mutex cleanup; v8 introduces no §9-level changes.)

See v7 §9.4 for the authoritative parser/validator/POST/PATCH implementation patterns. v8 amends nothing here. The migration script (`migrate_schema_vocab_v1.py`) implements v7 §9.4 verbatim per CLI report §3 (1850 lines, py_compile clean) + §6 confidence tags ("[CONFIRMED — spec text] v7 §9.4 state-machine `extract_structured_payload` implemented verbatim").

---

## §10 — Cursor review companion (v3 preserved; v4-v8 unchanged at top level)

This spec v8 is a documentation amendment over v7. v8 introduces no design change, no script change, no execution-gate change — it codifies live CLI behavior into the spec body so any future implementer reading v8 in isolation has self-consistent documentation. The v3 Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` remains the canonical review companion since the cumulative review trail is anchored there. If Kim chooses to send v8 back for a Cursor pass, the v8 file itself + the v8-A + v8-B rows of §0.1 are the review surface; the underlying v7 design (parser, validator, mutex protocol, checkpoint, rehearsal, feature flag) is unchanged and not in scope for v8 review. v2 + v1 handoffs preserved as historical baselines.

---

## §11 — Reference index (v7 preserved + v8 entries added)

(All v2 entries preserved verbatim through v3 → v4 → v5 → v6 → v7 → v8. All v3-NEW entries preserved. All v4-NEW entries preserved. All v5-NEW entries preserved. All v6-NEW entries preserved. All v7-NEW entries preserved.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — **v7 historical baseline (this spec's predecessor)** (v8 NEW reference); sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline (v7 reference; v8 preserved); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline (v6 reference; v7 + v8 preserved); sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline (v5 reference; v6 + v7 + v8 preserved); sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline (v4 reference; v5 + v6 + v7 + v8 preserved); sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline; sha256 `3d39b7c5ead3c1c0d0f0876a294f16042f3f9c7a72a8b721bb8e148da7f361c9`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `e88e82eaea03e6d4837cc41438361491c00c32155d3d09efcd5353f585e2aa5b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` — **CLI dispatch dry-run report** (v8 NEW reference); contains drift table + Rule 4 origin column (3 spec-extension rows tagged) + INVESTIGATE-class triage queue (4 task_category rows).
- `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` — **CLI dispatch session report** (v8 NEW reference); records Phase A→F clean execution + Kim's drift-resolution authorization + mechanical halt #2 fire+resolve + prod_blockers id=103 + prod_activity_log id=1826 + LD-602 cross-reference.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` — **THIS SPEC (v8)** (v8 NEW self-reference).
- `Production/scripts/lock_decision.py` — canonical-aware as of 2026-05-08 per Cursor Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `Production/scripts/migrate_schema_vocab_v1.py` — **migration script** (1850 lines, py_compile clean per CLI report §3); v8 codifies the partition + Rule 4 extensions the script already implements.
- `LD_WRITER_CANONICAL_VOCAB_V1` (LD #588) — LD documenting Task H execution (HARD severity).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (preserved through v8).
- `LD-593` — v4 §9.4 severity case-fold authority (preserved through v8).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority (preserved through v8).
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority (preserved through v8).
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — `prod_activity_log.task_description` non-existence anti-confusion guard (preserved through v8; v8 inherits the guidance and uses `details` (JSON dict) as canonical narrative carrier in this session's activity-log POST).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — v7 Cursor AMEND_V3 fix authority (preserved through v8).
- `LD-601` — Phase 3 row 101 idempotent resolution authority (CLI report §3 Phase K row reference).
- `LD-602` — F3-fix predecessor cleanup LD; the v3 stale-SHA-1 reference in handoff §1-area Header was superseded by handoff v2.4 amendments per LD-602; v8 + handoff v2.5 close out the documentation drift completely (v8 NEW cross-reference).
- `LD-NEW SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` — **v8 amendment authority** (v8 NEW reference; filed 2026-05-09 same session as v8 spec authoring; LD id captured at file time).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for v7 §9.4 (preserved through v8). v8 does NOT update the schema-ref doc since v8 introduces no schema-side change.
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. **v2.5** (this session: §1-area Header bullet sha256 reference updated from spec v3 stale SHA-1 to spec v8 sha256 + §11 v2.5 versioning entry appended). v2.4 cited v7; v2.5 amends to cite v8.
- `Production/exports/prod_locked_decisions_2026-05-09.jsonl` — cached canonical-export from CLI session (562 rows).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl` — snapshot file from CLI session; snapshot_hash `f5ae2c3a150c45491f215071ce5e4e9ccacb01a20e6f9a98d7e598982925769f`.
- `Production/exports/schema_migration_checkpoint_2026-05-09.jsonl` — append-only checkpoint per §5.0 (CLI session resumes from this on Phase G dispatch).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — rehearsal pass/fail report (NOT YET CREATED — Phase G deferred).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; remains canonical for v8's cumulative review trail).
- `prod_activity_log` id=1826 — Kim's drift-resolution authorization marker (CLI session); Rule 3b 110→56 amendment + Rule 4 spec-extension origin tags audit trail.
- `prod_blockers` id=103 — drift-fire-and-resolve mechanical halt #2 audit row from CLI session (resolved 2026-05-09T02:48:36 per Kim authorization).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied: PHASE_5_ENABLED feature flag + dual-canonical paths + snapshot integrity fields + cost split. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied: cached canonical-export + rollback rehearsal + remote mutex §9.4 + checkpoint schema §5.0 + lock_decision.py canonical-aware Task H execution. Status: superseded by v4. Author: Claude Opus 4.7 (1M context).
- **v4** — 2026-05-08 — self-discovered §9.4 severity case-fold (NOT a Cursor amendment). Live `prod_blockers.severity` enum lowercase-only. v4 case-folds severity to lowercase `critical`, adds §6 Gate 11.1, adds §7 risk #13. Status: superseded by v5. Author: Claude Opus 4.7 (1M context).
- **v5** — 2026-05-08 — self-discovered §9.4 field-name fix (NOT a Cursor amendment; corrects what v4 explicitly deferred). v5 corrects acquisition POST + release PATCH + stale-mutex cleanup parsing. Adds §6 Gate 11.2, §7 risk #14, files LD-595. Status: superseded by v6. Author: Claude Opus 4.7 (1M context).
- **v6** — 2026-05-08 — Cursor AMEND_V2 on v5 (3 HIGH/Y blockers + 2 non-blockers) applied. Blocker A: guarded JSON parse + STALE_MUTEX_PARSE_FAILURE. Blocker B: runtime payload-key validator at §6 Gate 11.2. Blocker F: balanced-brace `extract_structured_payload`. Non-blocker D: hazard warnings. Non-blocker E: schema_version + ≤256-char cap. Adds risk #15. Files LD-596. Status: superseded by v7. Author: Claude Opus 4.7 (1M context).
- **v7** — 2026-05-08 — Cursor AMEND_V3 on v6 (1 HIGH/Y blocker, Task F) applied. **Blocker F:** v6's brace-counter `extract_structured_payload` REPLACED with JSON-string-aware parser state machine. Tracks `in_string` (toggled on UNESCAPED `"`) and `escape` (set on `\\` inside a string). Only `{`/`}` outside strings count toward `depth`. Example variation that breaks v6: `{"notes":"contains } brace","pid":123,...}`. v6 graceful `None` fallback + `STALE_MUTEX_PARSE_FAILURE` activity-log row preserved verbatim. Acquisition POST + release PATCH + Gate 11.2 validator stay v6 (already correct). Adds risk #16. All other v6 design preserved verbatim. v1-v6 preserved as historical baselines. Files LD-598. Status: superseded by v8. Author: Claude Opus 4.7 (1M context).
- **v8** — 2026-05-09 — documentation amendment over v7 motivated by CLI dispatch session 2026-05-08 / 09 findings (Phase A through Phase F clean; HALTed before Phase G rehearsal per Kim's directive). **Defect 1 (v8-A):** v7 §4 EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"] = 110 conflated mechanical synonyms (56 rows) with INVESTIGATE-class rows (68 rows: `production_infrastructure` 35, `production_pipeline` 26, `tools` 6, `feature` 1) which spec §3.3 verdict explicitly defers to per-row Kim triage. v8 §3.3 ADDS partition callout, §3.3.1 NEW subsection enumerates 68 INVESTIGATE-class rows in 4-row triage table, §4 EXPECTED_ROW_COUNTS corrected 110→56. **Defect 2 (v8-B):** v7 §3.4 Rule 4 mapping table enumerated 11 mappings (29 rows); live data showed 3 additional source values that the CLI script handled with origin tag "spec-extension (Kim 2026-05-09)" per Kim authorization in chat 2026-05-09. v8 §3.4 ADDS 3 rows + origin column, §4 EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] corrected 29→35. Adds risk #17 (auto-PATCH-INVESTIGATE-class implementer-drift hazard; LOW likelihood with v8 §3.3.1 + §4 + drift halt + handoff cross-reference + LD; HIGH severity due to semantic-ambiguity bypass). All other v7 design (parser, validator, mutex protocol, checkpoint, rehearsal, feature flag, severity case-fold, gate semantics) preserved verbatim. v1-v7 preserved as historical baselines. Files LD-NEW `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1`. **Note:** handoff v2.4 cited v7; v2.5 amendment this session updates §1-area Header bullet sha256 reference from spec v3 stale SHA-1 (`e8ea981844a339a24fc89123ba2960044863233b`) to spec v8 actual sha256 + appends §11 v2.5 versioning entry. Schema-ref doc §5 NOT updated by v8 (v8 introduces no schema-side change). Author: Claude Opus 4.7 (1M context); session: gallant-bouman-804b4f post-CLI-Phase-F.
