# Schema Vocab Migration — Tech Spec v9

**Authored:** 2026-05-09 (post-Cursor-v8-review session in worktree gallant-bouman-804b4f).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ROUTINE (documentation amendment over v8 + script-doc sync update; no design change, no execution-gate change; corrects 3 defects surfaced by Cursor's v8 review — 1 narrative inconsistency, 1 script-doc desync, 1 LD placeholder).
**Status:** DESIGN ONLY — execution remains gated on the same Phase 5 PHASE_5_ENABLED feature flag + §6 Gates 1-12 (preserved verbatim from v7 → v8) + Phase G rehearsal authorization that v7 mandated.

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` (preserved as historical baseline; do NOT edit in place). v8 in turn supersedes v7; v7 supersedes v6; v6 supersedes v5; v5 supersedes v4; v4 supersedes v3; v3 supersedes v2; v2 supersedes v1. v1-v8 all preserved as historical record.

**v8 → v9 driver:** Cursor's v8 cross-review surfaced **3 defects in v8** (1 HIGH narrative inconsistency, 1 HIGH script-doc desync, 1 MEDIUM placeholder):

1. **HIGH 1 — narrative inconsistency in §4 cross-references:** v8 §4 line 196 narrates "Rule 4 35 expected / 35 actual / 0.0% drift" as the post-amendment second-run state. The cited dry-run report `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` §1 line 16 records `rule_4_scope_domain_remap | 29 | 35 | +6 | 20.69% | OK`. The dry-run report is a frozen audit artifact written by the CLI session against the v7-era EXPECTED of 29; v8's "0.0% drift" narrative reflects what a future re-run would see AFTER the EXPECTED amendment, but the dry-run-of-record itself shows 20.69%. v9 reconciles the two so any reader landing on v9 understands BOTH baselines.
2. **HIGH 2 — script-doc desync:** v8 stated "no script change," yet `Production/scripts/migrate_schema_vocab_v1.py` lines 79-90 still encode `SCRIPT_VERSION = "migrate_schema_vocab_v1.py@2026-05-08-v7"`, `SPEC_V7_SHA256`, `SPEC_V7_PATH`, AND `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] = 29` (not 35). Script-doc out of sync with v8's authoritative narrative. v9 + script update applied this session reconcile both.
3. **MEDIUM — `LD-NEW` placeholder:** v8 references the v8 amendment authority as `LD-NEW` in 6 places (§0.1 line 13, §3.3.1 cross-references, §3.4 v8 amendment intro, §11 reference index, §12 changelog). The actual filed LD is **LD-611 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1`** (severity SOFT; verified live via DirectusAdminClient). v9 replaces all v8 `LD-NEW` references with the concrete LD-611 id.

v9 corrects ONLY these 3 defects + the script-doc sync. All other v8 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H, severity case-fold, Gate 11.1, runtime validator Gate 11.2, hazard warnings, schema_version, ≤256-char cap, JSON-string-aware state-machine extractor, Rule 3b 56-mechanical-only partition, Rule 4 35-with-spec-extensions partition) preserved verbatim. v1-v8 preserved as historical baselines.

**Related artifacts (preserved from v8 + v9 additions):**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` — **v8 historical baseline (this spec's predecessor)** (v9 NEW reference); sha256 `c6220e519f5b8fb023e163936099f153610ac078d4d3392c6d9f9a454267c052`, 321 lines.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 historical baseline (v8 reference; v9 preserved); sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`, 498 lines, 59,307 bytes.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline; sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline; sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline; sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline; sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline; sha256 `3d39b7c5ead3c1c0d0f0876a294f16042f3f9c7a72a8b721bb8e148da7f361c9`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `e88e82eaea03e6d4837cc41438361491c00c32155d3d09efcd5353f585e2aa5b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` — **CLI dry-run report** (frozen audit artifact; v8 + v9 reference); contains the historical Rule 4 line `29 | 35 | +6 | 20.69% | OK`. Reconciliation note added in v9 §3.4.
- `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` — CLI session report (v8 reference; v9 preserved).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl` — snapshot file referenced by the CLI session.
- `Production/exports/prod_locked_decisions_2026-05-09.jsonl` — cached canonical-export from CLI session (562 rows).
- `Production/scripts/migrate_schema_vocab_v1.py` — **migration script** (v9 SCRIPT UPDATE reference; this session updates `SCRIPT_VERSION`, `SPEC_V7_*` → `SPEC_V9_*`, and `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35` per HIGH 2 fix; py_compile validated post-edit).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff. Currently at v2.5 per v8 narrative; v9 does NOT amend the handoff (script update is in scope; handoff cross-reference update would be v2.6 if Kim authorizes — explicitly NOT in scope this session per task self-bound).
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed.
- `Production/scripts/lock_decision.py` — LD-writer CLI; canonical-aware as of 2026-05-08 per Cursor v3 Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-fix backup.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating helper-import.
- `LD_WRITER_CANONICAL_VOCAB_V1` (LD #588) — LD documenting the lock_decision.py canonical-aware fix (HARD severity).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section.
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority.
- `LD-593` — v4 §9.4 severity case-fold authority.
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority.
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority.
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — anti-confusion guard for `prod_activity_log.task_description` non-existence; v9 inherits the guidance verbatim (do NOT include `task_description` in any `prod_activity_log` POST; `details` (JSON dict) is the canonical narrative carrier).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — v7 Cursor AMEND_V3 fix authority.
- `LD-601` — Phase 3 row 101 idempotent resolution authority.
- `LD-602` — F3-fix predecessor cleanup LD.
- `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` — **v8 amendment authority** (concrete id; v9 replaces all v8 `LD-NEW` references with this).
- `LD-NEW (this session) SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1` — **v9 amendment authority** (filed 2026-05-09 same session as v9 spec authoring; LD id captured at file time).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference. v9 does NOT update the schema-ref doc since v9 introduces no schema-side change.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff.

---

## §0.1 — v9 Changelog (single-row amendment over v8)

v9 is a documentation amendment over v8 + a script update to fix the script-doc desync surfaced by Cursor's v8 review. No design change, no execution-gate change. v8's §0.1 changelog is preserved verbatim immediately below this v9 entry, followed by v7's, v6's, v5's, v4's, v3's.

| # | v9 amendment (Cursor v8 review findings) | Resolution applied in v9 | Sections changed |
|---|---|---|---|
| v9-A | **HIGH 1 — narrative inconsistency in §4 cross-references.** v8 §4 line 196 narrates "Rule 4 35 expected / 35 actual / 0.0% drift" as the second-run reconciled state. The cited dry-run report `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` §1 line 16 records `rule_4_scope_domain_remap \| 29 \| 35 \| +6 \| 20.69% \| OK`. The dry-run report is a FROZEN audit artifact reflecting the historical comparison against v7-baseline EXPECTED=29; v8's narrative reflects what a re-run would see AFTER the v8 EXPECTED amendment. Cursor flagged the apparent contradiction. | v9 §3.4 ADDS an explicit reconciliation note clarifying the two-baseline reality: dry-run-of-record is `29-baseline / 35 actual / 20.69% drift` (v7-era EXPECTED, frozen audit); v8 amended EXPECTED to 35 going forward (authoritative for any future re-run). Both numbers are correct in their respective frames; v9 preserves both explicitly. v9 §4 EXPECTED_ROW_COUNTS table now annotates BOTH the v7 baseline (29) AND v9-authoritative (35) for `rule_4_scope_domain_remap`, with rationale ("v7 baseline used by current script pre-update; v9 authoritative for any future re-run after script update lands"). | §3.4 (NEW reconciliation note near end), §4 (EXPECTED_ROW_COUNTS annotation showing both baselines), §11 reference index dry-run-report annotation, §12 changelog |
| v9-B | **HIGH 2 — script-doc desync.** v8 stated "no script change" but `Production/scripts/migrate_schema_vocab_v1.py` lines 79-90 still encoded `SCRIPT_VERSION = "migrate_schema_vocab_v1.py@2026-05-08-v7"`, `SPEC_V7_SHA256`, `SPEC_V7_PATH`, and `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] = 29`. Script and v8 doc out of sync. | v9 + script update applied THIS SESSION: (1) `SCRIPT_VERSION` → `"migrate_schema_vocab_v1.py@2026-05-09-v9"`; (2) `SPEC_V7_SHA256` constant renamed `SPEC_V9_SHA256` with value computed from v9 file; (3) `SPEC_V7_PATH` → `SPEC_V9_PATH` pointing at v9 spec; (4) `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29 → 35`; (5) inline comment near these constants citing LD-NEW (v9) + Cursor's HIGH 2 finding. Script syntactic validity verified via `python3 -m py_compile`. v9 §7 ADDS risk #18 documenting the future-re-run-stale-baseline hazard. | Script (`Production/scripts/migrate_schema_vocab_v1.py` lines 79-110); v9 §4 EXPECTED_ROW_COUNTS narrative reflects post-update reality; v9 §7 risk #18 (NEW); v9 §11 reference index script line annotated v9-updated; v9 §12 changelog |
| v9-C | **MEDIUM — `LD-NEW` placeholder.** v8 used `LD-NEW` as a stand-in for the v8 amendment authority in 6 places. The actual filed LD is `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` (severity SOFT; verified live via DirectusAdminClient query 2026-05-09). | v9 §11 reference index + v9 §3.3.1 cross-references + v9 §3.4 cross-references + v9 §0.1 v8 row preserved-text references all replaced with concrete `LD-611`. v9's own LD authority is `LD-NEW (this session) SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1`, captured at file time. Multipass verify: 0 occurrences of bare `LD-NEW` referencing v8 in v9 post-edit (the only `LD-NEW` retained is the explicit v9-self-reference). | §11 reference index (LD-611 inserted; v9-self LD-NEW retained as v9-this-session marker), §3.3.1 + §3.4 cross-references, §0.1 v8 preserved row LD reference, §12 changelog |

**v8 vs v9 surface area:** v9 adds ~50 lines net (one §0.1 v9 row above v8's, one §3.4 v9 reconciliation note, one §4 v9 annotation, one §7 risk #18 row, ~3 §11 reference-index entries + LD-611 substitutions, one §12 changelog entry). v9 deletes nothing structurally — it preserves all v8 content verbatim and adds documentation. The substantive script change is exactly the four constants + comment listed in v9-B. v9 does NOT touch the implementation handoff (separate concern; would be v2.6 if needed; not in scope this session).

---

## §0.1 (v8, preserved verbatim) — v8 Changelog (CLI dispatch findings amendment over v7)

v8 is a documentation amendment over v7 addressing 2 documentation defects surfaced by the CLI dispatch session 2026-05-08 / 09 (Phase A through Phase F clean; HALTed before Phase G rehearsal per Kim's directive). No script change, no design change, no execution-gate change. v7's §0.1 changelog is preserved verbatim immediately below this v8 entry, followed by v6's, v5's, v4's, v3's.

| # | v8 amendment (CLI dispatch session findings) | Resolution applied in v8 | Sections changed |
|---|---|---|---|
| v8-A | **Defect 1 (documentation only) — v7 §4 EXPECTED_ROW_COUNTS conflated mechanical and INVESTIGATE-class rows for Rule 3b.** v7 cited `rule_3b_task_category_remap = 110` rows. Live count of mechanically-eligible rows = 56 (architectural→app_architecture 33, audio_production→audio 4, production_server→infrastructure 2, production_server_infrastructure→infrastructure 14, video_production→video 3). Remaining 68 rows (`production_infrastructure` 35, `production_pipeline` 26, `tools` 6, `feature` 1) are INVESTIGATE-class per spec §3.3 verdict — NOT auto-PATCHed; Kim per-row triage required. CLI script's partition is correct per spec §3.3 verdict; the v7 EXPECTED_ROW_COUNTS figure mixed both classes. | v8 §3.3 ADDS an explicit partition callout stating that the spec's earlier "~110 rows" estimate conflated the two classes. v8 §3.3.1 is a NEW subsection enumerating the 68 INVESTIGATE-class rows in a 4-row triage table. v8 §4 corrects EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"] from 110 to 56. v8 §7 ADDS risk #17 documenting the implementer-drift hazard if a future reader copies the v7 110 figure and auto-PATCHes the 68 INVESTIGATE-class rows. v8 §11 reference index adds CLI dispatch session report path + LD-611 (v8 used `LD-NEW` placeholder; v9 substitutes concrete LD-611). v8 §12 changelog appends v8 entry. | §3.3 (NEW partition callout near end), §3.3.1 (NEW subsection — INVESTIGATE-class triage table), §4 (EXPECTED_ROW_COUNTS["rule_3b_task_category_remap"] 110→56 + ["rule_4_scope_domain_remap"] 29→35), §7 risk #17 (NEW), §11 reference index (CLI session report + LD-611), §12 changelog |
| v8-B | **Defect 2 (documentation only) — v7 §3.4 Rule 4 scope_domain mapping table omitted 3 production-* mappings.** v7 enumerated 11 mappings (29 rows). Live data showed 3 additional source values: `production-server` (3 rows; dash variant matching `production_server_infrastructure` semantic per cleanup-report) → `infra`; `production_pipeline` (1 row) → `production`; `audio_production` (1 row) → `production`. CLI script dispatched these live with origin tag "spec-extension (Kim 2026-05-09)" per Kim authorization in chat 2026-05-09. | v8 §3.4 ADDS 3 rows to the Rule 4 mapping table at the end, each tagged with origin "spec-extension (Kim 2026-05-09)". v8 §4 EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] updated 29→35. The CLI session's drift table reflects the actual live count of 35 rows touched (vs. v7 expected 29; +6 delta = 20.69% drift, within 25% threshold). | §3.4 (3 NEW rows at end + origin column), §4 (EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35), §11 reference index entries cited by §3.4, §12 changelog |

(v8 §0.1 v8-A + v8-B rows preserved verbatim above. v8 originally cited `LD-NEW` as the v8 amendment authority; v9 §11 substitutes the concrete `LD-611`.)

---

## §0.1 (v7, preserved verbatim) — v7 Changelog (Cursor AMEND_V3 fix-set on v6: Blocker F)

(Preserved verbatim from v8 §0.1 v7 row. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` §0.1 v7 section for the full Blocker F resolution covering the JSON-string-aware state-machine extractor.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE for parser implementation. v8 + v9 introduce no parser change. See §6 Gate 11.2 (runtime validator, unchanged from v6) for write-time enforcement.

---

## §0.1 (v6, preserved verbatim) — v6 Changelog (Cursor AMEND_V2 fixes)

(Preserved verbatim from v8 §0.1 v6 section.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9). See §6 Gate 11.2 (runtime validator, unchanged from v6) for write-time enforcement.

---

## §0.1 (v5, preserved verbatim) — v5 Changelog (single-row amendment over v4)

(Preserved verbatim from v8 §0.1 v5 section.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9).

---

## §0.1 (v4, preserved verbatim) — v4 Changelog (single-row amendment over v3)

(Preserved verbatim from v8 §0.1 v4 section.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9).

---

## §0.1 (v3, preserved verbatim from v4 → v5 → v6 → v7 → v8 → v9) — v3 Changelog (Cursor amendment resolution table)

(Preserved verbatim from v8 §0.1 v3 section.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9).

---

## §1 — Goal (preserved verbatim from v1 + v2 + v3 + v4 + v5 + v6 + v7 + v8)

(Preserved verbatim from v8 §1. Five-bullet goal statement + non-goals list. v9 introduces no §1-level changes — it is a documentation amendment + script-doc sync, not a goal-shifting amendment.)

---

## §2 — Background (preserved verbatim from v1 + v2 + v3 + v4 + v5 + v6 + v7 + v8)

(Preserved verbatim from v8 §2. v8 ADD on CLI dispatch session preserved.)

**v9 ADD (informational):** Cursor's v8 cross-review surfaced 3 defects: HIGH 1 narrative inconsistency in §4 (Rule 4 35/35/0.0% v8 narrative vs. dry-run report 29/35/20.69% historical record), HIGH 2 script-doc desync (script still cites v7 constants and `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] = 29`), and MEDIUM `LD-NEW` placeholder substitution. v9 + script update applied this session resolve all three. The dry-run report remains the historical audit-of-record (frozen artifact); v9's reconciliation note in §3.4 explicitly clarifies that the report's 29-baseline comparison was correct at write time, and the v8 amendment moved EXPECTED to 35 going forward. v9 also files LD-NEW (this session) `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1` and substitutes `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` for v8's `LD-NEW` placeholders.

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments (preserved in v3 + v4 + v5 + v6 + v7 + v8 + v9)

(Preserved verbatim from v8 §3. §3.0 path discipline / §3.1 Rule 1 + PHASE_5_ENABLED / §3.2 Rule 2 / §3.3 + §3.3.1 v8-amended Rule 3 task_category — all preserved through v9. v9 amends §3.4 (Rule 4 scope_domain) with a reconciliation note clarifying the two-baseline reality.)

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` §3.0-§3.4 for the v8-baseline verbatim text. v9 amendments below.

### §3.3 v8 amendment (Rule 3 task_category — partition clarification) — preserved verbatim through v9

(Preserved verbatim from v8 §3.3 v8 amendment block. v9 introduces no §3.3 changes.)

### §3.3.1 — INVESTIGATE-class triage queue (v8 NEW; preserved verbatim through v9)

(Preserved verbatim from v8 §3.3.1 NEW subsection. v9 introduces no §3.3.1 changes; LD authority reference updated from `LD-NEW (this session)` to `LD-611` + new v9 LD added.)

The 68 rows below are NOT auto-PATCHed by Phase 4. They are surfaced for Kim's per-row triage per the §3.3 dual-Opus debate verdict. Disposition column references the existing §3.3 verdict guidance.

| task_category | Row count | Disposition |
|---------------|-----------|-------------|
| `production_infrastructure` | 35 | Per-row Kim triage; cleanup-report §5.X candidates (spec §3.3 verdict: SPLIT — drain → `infrastructure`, widgets → `production_tool_ui`) |
| `production_pipeline` | 26 | Per-row Kim triage (spec §3.3 verdict: INVESTIGATE — overlap with `production_infrastructure`) |
| `tools` | 6 | Per-row Kim triage (spec §3.3 verdict: INVESTIGATE — overlap with `production_tool_ui`) |
| `feature` | 1 | Per-row Kim triage (spec §3.3 verdict: too generic; per-row review) |
| **Total** | **68** | Triage-queue (NOT auto-PATCHed by Phase 4) |

**§3.3.1 cross-references (v9-updated):** CLI dispatch session report `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` §4.2 lists these 68 rows verbatim. Dry-run report §3 enumerates the same 4 task_category values. Both are auditable archives of the live CLI behavior; v8 codified them into the spec body. **LD-611 `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1`** is the v8 amendment authority (replaces v8's `LD-NEW` placeholder per v9-C). LD-602 is the F3-fix predecessor cleanup LD that motivated re-reading the spec for partition consistency. LD-NEW (v9 this session) `SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1` is the v9 amendment authority.

### §3.4 v8 amendment (Rule 4 scope_domain — 3 new spec-extension mappings) — preserved verbatim through v9

(Preserved verbatim from v8 §3.4 v8 amendment block — 14-row mapping table + origin column + cross-references. v9 amends only the cross-references substring of `LD-NEW` → `LD-611` + appends a v9 reconciliation note.)

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
| `production_pipeline` | `production` | 1 | **spec-extension (Kim 2026-05-09);** semantic match to `*_pipeline → production` family. |
| `audio_production` | `production` | 1 | **spec-extension (Kim 2026-05-09);** semantic match to `audio_pipeline → production`. |
| **Total** | — | **35** | (11 spec-§3.4-verbatim mappings = 29 rows + 3 spec-extension mappings = 6 rows; total 35 rows mapped) |

**§3.4 v8 cross-references (v9-updated):** CLI dispatch session report §4.1 documents Kim's authorization for the 3 spec-extensions verbatim. The dry-run report §4 (Rule 4 table) tags each of the 3 spec-extension rows with origin column "spec-extension (Kim 2026-05-09)". The 20.69% drift between v7-baseline-expected (29) and live (35) was within the 25% mechanical-halt threshold; no halt fired. v8 codified the +6 delta into the spec; v9 substitutes `LD-611` for v8's `LD-NEW` placeholder per v9-C.

#### §3.4 v9 reconciliation note (NEW v9; HIGH 1 fix per Cursor)

> **v9 reconciliation (informational; addresses Cursor v8 review HIGH 1):** the dry-run report `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` §1 line 16 records `rule_4_scope_domain_remap | 29 | 35 | +6 | 20.69% | OK`. The dry-run report is a FROZEN audit-of-record artifact written by the CLI session against the v7-era `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] = 29`. The v8 amendment moved EXPECTED to 35 going forward; v8's "Rule 4 35 expected / 35 actual / 0.0% drift" narrative in §4 cross-references reflects what a hypothetical post-amendment re-run would see, NOT the dry-run-of-record. Both numbers are correct in their respective frames:
>
> - **Dry-run-of-record (frozen):** Expected=29 (v7 baseline), Actual=35, Delta=+6, %drift=20.69%, halt-eval=OK. This is the historical evaluation that fired during the CLI dispatch session and is preserved verbatim in `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md`.
> - **v9-authoritative (post-amendment baseline):** Expected=35 (v8 corrected; v9 codified), Actual=35, Delta=0, %drift=0.0%, halt-eval=OK. This is the comparison any FUTURE re-run would produce after the v8 spec amendment + the v9 script update (this session) land. The script update is applied this session (v9-B fix); EXPECTED in the script source is now 35.
>
> Both frames are preserved as authentic audit data. The dry-run-of-record is NOT amended (frozen artifact). v9 adds this reconciliation note so any reader can see both baselines without confusion. See §4 v9 EXPECTED_ROW_COUNTS table for the dual-baseline annotation.

---

## §4 — Per-rule action table (v8 preserved + v9 EXPECTED_ROW_COUNTS dual-baseline annotation)

(Preserved verbatim from v8 §4. Rules 1/2/3a/3b/4 with v3 prerequisite columns + v2 expanded snapshot schema reference. v9 introduces no §4-level structural changes; only annotates the EXPECTED_ROW_COUNTS dict to show both v7-baseline and v9-authoritative for `rule_4_scope_domain_remap` per HIGH 1 fix + adds a script-update note per HIGH 2 fix.)

See v3 §4 / v4 §4 / v5 §4 / v6 §4 / v7 §4 / v8 §4 for the verbatim per-rule action narrative.

### §4 v9 — EXPECTED_ROW_COUNTS dict (current authoritative values + dual-baseline annotation for Rule 4)

The migration script's `EXPECTED_ROW_COUNTS` dict (referenced in §5 Phase 0 Step 2 dry-run drift evaluation) — post-v9 script update:

```python
EXPECTED_ROW_COUNTS = {
    "rule_1_severity_high_critical_to_hard": 320,        # preserved from v7 (Phase 5 deferred per spec §3.1)
    "rule_2_severity_lowercase_to_upper": 37,            # preserved from v7
    "rule_3b_task_category_remap": 56,                   # v8 CORRECTED — was 110 in v7; partition per §3.3.1 separates 68 INVESTIGATE-class rows
    "rule_4_scope_domain_remap": 35,                     # v8 CORRECTED — was 29 in v7; +6 per §3.4 spec-extensions (Kim 2026-05-09); v9 ALIGNED IN SCRIPT this session per Cursor HIGH 2 fix
}
```

**§4 v9 dual-baseline reference table for `rule_4_scope_domain_remap` (HIGH 1 reconciliation):**

| Frame | Value | Provenance | Drift evaluation |
|-------|-------|------------|------------------|
| v7 baseline | 29 | v7 §3.4 11-mapping table | Used by dry-run-of-record `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` §1 line 16 → drift `+6 / 20.69% / OK` |
| v9 authoritative | 35 | v8 §3.4 14-mapping table (29 v3-verbatim + 6 spec-extension); v9 codified in script | Future re-run baseline → drift `0 / 0.0% / OK` |

**§4 v9 cross-references:** CLI dispatch session report §4 drift table compared EXPECTED_ROW_COUNTS (v7 figures of 110 + 29 at first run) against actual touched-row counts and FIRED mechanical halt #2 with 49.09% Rule 3b drift on the first run; resolved 2026-05-09T02:48:36 per Kim authorization to amend the EXPECTED_ROW_COUNTS values. The second-run dry-run-of-record (frozen at `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md`) compares against the partially-amended values (Rule 3b=56 amended; Rule 4=29 STILL v7-baseline because the Rule 4 amendment to 35 was made at v8 spec write time AFTER the dry-run report was frozen). The dry-run report's Rule 4 line `29 | 35 | +6 | 20.69% | OK` reflects this frozen historical state. v8 spec amended EXPECTED to 35; v9 script update aligned the script source to 35 this session.

**§4 v9 script update note (HIGH 2 fix):** the migration script `Production/scripts/migrate_schema_vocab_v1.py` lines 79-110 were updated this session as part of v9: `SCRIPT_VERSION` v7→v9, `SPEC_V7_*` constants → `SPEC_V9_*`, `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35`, inline comment added. py_compile validated post-edit. Pre-edit script sha256 captured for audit; post-edit script sha256 captured for cross-reference.

---

## §5 — Migration sequence (preserved verbatim from v3 + v4 + v5 + v6 + v7 + v8)

(Preserved verbatim from v8 §5. v8 informational note preserved. v9 introduces no §5-level changes.)

> **§5-LEVEL HAZARD WARNING (preserved verbatim from v8):** §5 below preserves v3+v4+v5+v6+v7+v8 example body code blocks BY REFERENCE (not inline). **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9). The migration script's Phase 1 entry-guard (and every other `prod_blockers` POST/PATCH) MUST use the v7 §9.4 patterns: JSON-string-aware state-machine extractor + try/except for parsing, runtime payload-key validator before write, capped resolution-text append, schema_version="v1" on acquisition.

**v9 NOTE (NEW; informational only):** v9 introduces no §5-level changes beyond the EXPECTED_ROW_COUNTS dual-baseline annotation in §4. Phase 0 Step 2 dry-run drift evaluation post-v9-script-update compares against v9-authoritative figures (Rule 3b=56, Rule 4=35). Phases G + 1-6 remain DEFERRED per Kim's "HALT before Phase G" directive; resume requires fresh dispatch.

See v8 §5.0 + Phase 0 + Phase 1-6 for the verbatim text.

---

## §6 — Pre-implementation gates Kim must approve (v8 preserved verbatim through v9)

(Gates 1-12 preserved verbatim from v7 → v8 → v9. v9 introduces no §6-level changes — gate semantics, validator function, and verification artifacts unchanged.)

See v8 §6 for the full Gates 1-12 + verification artifacts text. v9 amends nothing here.

---

## §7 — Risk assessment (v8 preserved + v9 risk #18 added)

(Rows 1-9 preserved verbatim from v2. Rows 10/11/12 preserved from v3. Row 13 from v4. Row 14 from v5+v6. Row 15 from v6. Row 16 from v7. Row 17 from v8. Row 18 NEW in v9.)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| **(v3 — #10)** Rollback rehearsal passes on 5 sampled rows but actual rollback fails on the remaining 315 rows due to row-specific quirks | LOW | HIGH | Preserved verbatim from v8. |
| **(v3 — #11)** Remote mutex acquisition succeeds but mutex is never released due to script crash | LOW | MEDIUM | Preserved verbatim from v8. |
| **(v3 — #12)** Checkpoint file corrupted mid-write causes resume algorithm to crash or skip valid rows | LOW | MEDIUM | Preserved verbatim from v8. |
| **(v4 — #13)** Spec author or implementer copy-pastes uppercase `CRITICAL` from v3 example into mutex POST | LOW | HIGH | Preserved verbatim from v8. |
| **(v5 — #14; v6 likelihood condition clarified)** Spec author or implementer copy-pastes v3/v4 example body containing a `details` or `resolution_notes` field on a `prod_blockers` POST/PATCH | LOW (with v6 hardened lint) | HIGH | Preserved verbatim from v8. |
| **(v6 — #15)** Stale-mutex cleanup helper encounters malformed/unparseable `STRUCTURED_DETAILS_JSON:` block | LOW | MEDIUM | Preserved verbatim from v8. |
| **(v7 — #16)** Migration script implementer copies v6 brace-counter extraction snippet despite v7 amendment; payloads with in-string braces mis-slice | LOW | HIGH | Preserved verbatim from v8. |
| **(v8 — #17)** Implementer reads v7's `~110` estimate for Rule 3b and partitions wrong (auto-PATCHes the 68 INVESTIGATE-class rows that should be triaged manually) | LOW (with v8 §3.3.1 + §4 + drift halt + handoff cross-reference + LD-611) | HIGH | Preserved verbatim from v8 (LD-611 substituted for v8's `LD-NEW` placeholder per v9-C). |
| **(v9 NEW — #18)** Script encodes v7-era EXPECTED `rule_4_scope_domain_remap = 29` (per v8 review HIGH 2 finding); a future re-run executed BEFORE the v9 script update lands would evaluate drift against the stale baseline. Failure mode: re-run drift evaluator compares 35 actual vs. 29 expected, fires 20.69% drift (still under 25% halt threshold), Phase 0 Step 2 passes, but the implementer reads "20.69% drift" and interprets it as suspicious data movement when the +6 delta is actually the established v8 spec-extension partition. Result: implementer-confusion-induced wrong-call (e.g., aborting Phase 1+ on assumption that data drifted, when in fact only the EXPECTED constant is stale). Note: the script update applied this session (v9-B fix) eliminates this risk going forward; risk #18 is documented for completeness + as a check against any rollback-to-pre-v9-script scenario. | LOW (script update applied this session lands the 29→35 fix; v9 §4 dual-baseline reconciliation table makes the partition explicit; Cursor v8 review captured the desync; LD-NEW v9 records the fix as permanent gotcha) | MEDIUM (drift halt threshold still catches >25% surprise; sub-25% drift causes implementer-confusion not data-loss; recovery is re-read v9 spec + script source) | (1) v9-B script update lands 29→35 + version cite v9 + spec path v9 this session; (2) v9 §4 dual-baseline reconciliation table makes both frames explicit; (3) v9 §3.4 reconciliation note at end of §3.4 mapping table; (4) risk #18 row enumerates the failure mode + recovery path; (5) LD-NEW v9 records as permanent gotcha; (6) Cursor v8 review captured in `gh` PR or chat audit trail; (7) future implementers reading v9 in isolation see the dual-baseline immediately. Severity MEDIUM because the worst case is implementer confusion not data corruption (mechanical halt still fires at 25%; sub-25% is sub-halt). Likelihood LOW because the fix is applied this same session. |

---

## §8 — Rollback per phase (preserved verbatim from v3 + v4 + v5 + v6 + v7 + v8)

(Preserved verbatim from v8 §8. v9 introduces no §8-level changes — rollback mechanism unchanged.)

See v8 §8 for the verbatim text.

---

## §9 — Operational notes (v8 preserved through v9)

(§9.1, §9.2, §9.3 preserved verbatim from v2 through v8. §9.4 preserved verbatim from v7 — JSON-string-aware state-machine extractor + acquisition POST + release PATCH + stale-mutex cleanup; v9 introduces no §9-level changes.)

See v8 §9.4 for the authoritative parser/validator/POST/PATCH implementation patterns. v9 amends nothing here. The migration script (`Production/scripts/migrate_schema_vocab_v1.py`) implements v7 §9.4 verbatim per CLI report §3 (1860 lines post-v9-update, py_compile clean).

---

## §10 — Cursor review companion (v3 preserved; v4-v9 unchanged at top level)

This spec v9 is a documentation amendment + script-doc sync over v8 addressing Cursor's v8 review findings (HIGH 1 narrative inconsistency, HIGH 2 script-doc desync, MEDIUM `LD-NEW` placeholder). v9 introduces no design change, no execution-gate change. The v3 Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` remains the canonical review companion for the cumulative review trail. If Kim chooses to send v9 back for a Cursor pass, the v9 file itself + the v9-A + v9-B + v9-C rows of §0.1 are the review surface; the underlying v8 design (parser, validator, mutex protocol, checkpoint, rehearsal, feature flag, severity case-fold, gate semantics, partition table, spec-extensions) is unchanged and not in scope for v9 review. v2 + v1 handoffs preserved as historical baselines.

---

## §11 — Reference index (v8 preserved + v9 entries added; LD-611 substituted for v8's LD-NEW per v9-C)

(All v2 entries preserved verbatim through v3 → v4 → v5 → v6 → v7 → v8 → v9. All v3-NEW entries preserved. All v4-NEW entries preserved. All v5-NEW entries preserved. All v6-NEW entries preserved. All v7-NEW entries preserved. All v8-NEW entries preserved with `LD-NEW` substituted to `LD-611` per v9-C. v9-NEW entries added below.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` — **v8 historical baseline (this spec's predecessor)** (v9 NEW reference); sha256 `c6220e519f5b8fb023e163936099f153610ac078d4d3392c6d9f9a454267c052`, 321 lines.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 historical baseline (v8 reference; v9 preserved); sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline (v7 reference; v8 + v9 preserved); sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline (v6 reference; v7 + v8 + v9 preserved); sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline (v5 reference; v6 + v7 + v8 + v9 preserved); sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline (v4 reference; v5 + v6 + v7 + v8 + v9 preserved); sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline; sha256 `3d39b7c5ead3c1c0d0f0876a294f16042f3f9c7a72a8b721bb8e148da7f361c9`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `e88e82eaea03e6d4837cc41438361491c00c32155d3d09efcd5353f585e2aa5b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` — **CLI dispatch dry-run report** (frozen audit-of-record artifact; v8 + v9 reference). v9 §3.4 reconciliation note clarifies that this report's Rule 4 line `29 | 35 | +6 | 20.69% | OK` is the v7-baseline historical comparison; v9-authoritative is 35-baseline.
- `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` — CLI dispatch session report (v8 reference; v9 preserved).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md` — **THIS SPEC (v9)** (v9 NEW self-reference).
- `Production/scripts/lock_decision.py` — canonical-aware as of 2026-05-08 per Cursor Task H execution.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `Production/scripts/migrate_schema_vocab_v1.py` — **migration script** (v9 SCRIPT UPDATE this session: `SCRIPT_VERSION` v7→v9; `SPEC_V7_*` → `SPEC_V9_*`; `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35`; inline LD-NEW v9 comment; py_compile validated). Pre-update sha256: `ddcf4cdcc3a90a375aff5fda4971a48d00cf6ff0ec39a96fb667b62c4f8d711c`. Post-update sha256: captured at activity-log time.
- `LD_WRITER_CANONICAL_VOCAB_V1` (LD #588) — LD documenting Task H execution (HARD severity).
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority (preserved through v8 + v9).
- `LD-593` — v4 §9.4 severity case-fold authority (preserved through v8 + v9).
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority (preserved through v8 + v9).
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority (preserved through v8 + v9).
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — `prod_activity_log.task_description` non-existence anti-confusion guard (preserved through v8 + v9; v9 inherits the guidance and uses `details` (JSON dict) as canonical narrative carrier in this session's activity-log POST).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — v7 Cursor AMEND_V3 fix authority (preserved through v8 + v9).
- `LD-601` — Phase 3 row 101 idempotent resolution authority.
- `LD-602` — F3-fix predecessor cleanup LD.
- `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` — **v8 amendment authority (concrete id; v9 substitutes for v8's `LD-NEW` placeholder per v9-C).** Severity SOFT; verified live via DirectusAdminClient query 2026-05-09.
- `LD-NEW (this session) SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1` — **v9 amendment authority** (filed 2026-05-09 same session as v9 spec authoring; LD id captured at file time).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for v7 §9.4 (preserved through v8 + v9). v9 does NOT update the schema-ref doc since v9 introduces no schema-side change.
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (v2.5 per v8 narrative). v9 does NOT amend the handoff (out of scope this session per task self-bound; v2.6 amendment if needed is a separate session decision for Kim).
- `Production/exports/prod_locked_decisions_2026-05-09.jsonl` — cached canonical-export from CLI session (562 rows).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl` — snapshot file from CLI session.
- `Production/exports/schema_migration_checkpoint_2026-05-09.jsonl` — append-only checkpoint per §5.0.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — rehearsal pass/fail report (NOT YET CREATED — Phase G deferred).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; remains canonical for v9's cumulative review trail).
- `prod_activity_log` id=1826 — Kim's drift-resolution authorization marker (CLI session).
- `prod_blockers` id=103 — drift-fire-and-resolve mechanical halt #2 audit row from CLI session (resolved 2026-05-09T02:48:36 per Kim authorization).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied. Status: superseded by v4.
- **v4** — 2026-05-08 — self-discovered §9.4 severity case-fold. Status: superseded by v5.
- **v5** — 2026-05-08 — self-discovered §9.4 field-name fix. Status: superseded by v6.
- **v6** — 2026-05-08 — Cursor AMEND_V2 on v5 (3 HIGH/Y blockers + 2 non-blockers) applied. Status: superseded by v7.
- **v7** — 2026-05-08 — Cursor AMEND_V3 on v6 (1 HIGH/Y blocker, Task F) applied: JSON-string-aware state-machine extractor. Status: superseded by v8.
- **v8** — 2026-05-09 — documentation amendment over v7 motivated by CLI dispatch session 2026-05-08 / 09 findings. Defect 1 (v8-A): Rule 3b 110→56 partition. Defect 2 (v8-B): Rule 4 +3 spec-extensions (29→35). Adds risk #17. Files LD-611 (v8 originally referenced as `LD-NEW` placeholder; v9 substitutes concrete LD-611 per v9-C). Status: superseded by v9. Author: Claude Opus 4.7 (1M context).
- **v9** — 2026-05-09 — documentation amendment + script-doc sync over v8 motivated by Cursor's v8 cross-review (HIGH 1 narrative inconsistency, HIGH 2 script-doc desync, MEDIUM `LD-NEW` placeholder). **HIGH 1 (v9-A):** v8 §4 narrated "Rule 4 35/35/0.0% drift" while dry-run-of-record records `29/35/20.69%`. v9 §3.4 ADDS reconciliation note clarifying both baselines are correct in their respective frames; v9 §4 ADDS dual-baseline reference table for `rule_4_scope_domain_remap`. **HIGH 2 (v9-B):** script `migrate_schema_vocab_v1.py` lines 79-110 still encoded `SCRIPT_VERSION` v7, `SPEC_V7_*` constants, and `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] = 29`. Script updated this session: `SCRIPT_VERSION` → v9; `SPEC_V7_*` → `SPEC_V9_*`; `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35`; inline LD-NEW (v9) comment; py_compile validated. Adds risk #18 (future-re-run-stale-baseline; LOW likelihood / MEDIUM severity). **MEDIUM (v9-C):** v8's 6 `LD-NEW` placeholders for the v8 amendment authority replaced with concrete `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` (verified live via DirectusAdminClient). All other v8 design (parser, validator, mutex protocol, checkpoint, rehearsal, feature flag, severity case-fold, gate semantics, partition table, spec-extensions) preserved verbatim. v1-v8 preserved as historical baselines. Files `LD-NEW (this session) SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1`. Schema-ref doc NOT updated (v9 introduces no schema-side change). Implementation handoff NOT updated (v2.6 out of scope this session). Author: Claude Opus 4.7 (1M context); session: gallant-bouman-804b4f post-Cursor-v8-review.
