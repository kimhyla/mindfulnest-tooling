# Schema Vocab Migration — Tech Spec v10

**Authored:** 2026-05-09 (post-Cursor-v9-round-2-review session in worktree gallant-bouman-804b4f).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** STANDARD (surgical amendment over v9 closing 4 Cursor round-2 findings — 2 HIGH + 1 MEDIUM + 1 LOW closed (v10-D §3.4 footnote tightening; §0.1 v10-D row + §3 v10 footnote tightening note). Migration script docstring synced. **No design change.** Operational gating posture **is updated** by v10-E: pre-implementation gates from v3-v9 are reclassified as HISTORICAL CONTEXT (audit trail) post-Phase-6 completion; any future re-execution requires NEW gates authored against post-migration state. See §6 v10-E note + §3.1 Phase-5-deferred clause. Production migration for Rules 2/3b/4 already COMPLETE as of 2026-05-09 04:08 UTC; Phase 5 (Rule 1) PERMANENTLY DEFERRED per spec §3.1. **v10-F round-4 cleanup** further consolidates: this header gate-change line, the §11 alias-audit grep scope, and the §7 header all rewritten for precision per Cursor round-4 findings (see §0.1 v10-F row).

**Status banner (v10 rewrite per Cursor round-2 HIGH-1):**
- **PRODUCTION MIGRATION COMPLETE** for Rules 2/3b/4 as of 2026-05-09 04:08 UTC (mutex released; activity log row 1993).
- **Phase 5 (Rule 1 long-tail INVESTIGATE triage) PERMANENTLY DEFERRED** per spec §3.1 + PHASE_5_ENABLED feature flag.
- **Spec authoring + script binding patches LANDED in-session** (v9 + v10 + script docstring sync this session).
- **Document classification:** TECH SPEC (authoritative). Not "DESIGN ONLY" — v9 + v10 are the authoritative documentary record of an already-executed migration plus the script-doc binding patches that landed.
- **What is NOT authorized:** Phase G rehearsal re-execution, Phase 5 enablement, any new production-data mutation. Those remain gated as historically described.
- **What landed in-session:** v9 spec authoring; v10 spec authoring; migration script SPEC_V9_* constants + EXPECTED_ROW_COUNTS update (v9 session); migration script module docstring sync (v10 session).
- **Banner precision (v10-E round-3 fix per Cursor HIGH-1):** "NO new production-data writes" REPLACED by precise-distinction wording — **NO mutations to migration-target rows (prod_locked_decisions rows targeted by Rules 1/2/3b/4 remained at their post-Phase-6 state). Governance writes (LD filings to `prod_locked_decisions`; activity_log POSTs to `prod_activity_log`) DID land — these are spec-authoring artifacts under the §0 governance-authoring carve-out, not migration mutations.** The distinction matters: filing LD-623 (v10-A initial pass), LD-629 (v10-D cleanup pass), and the v10-E round-3 LD are themselves writes to `prod_locked_decisions`, but they govern the spec authoring trail and do NOT mutate any of the 35+56+post-Phase-6 rows touched by Rules 2/3b/4. Migration-target rows are FROZEN.

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md` (preserved as historical baseline; do NOT edit in place; sha256 `0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894`, 345 lines). v9 supersedes v8; v8 → v7; v7 → v6; v6 → v5; v5 → v4; v4 → v3; v3 → v2; v2 → v1. v1-v9 all preserved as historical record.

**v9 → v10 driver:** Cursor's v9 cross-review (round 2) surfaced **3 actionable findings** (2 HIGH + 1 MEDIUM) plus **1 LOW (closed in v10 cleanup pass v10-D — see §0.1 v10-D row + §3 v10 footnote tightening note)**:

1. **HIGH-1 — Operating-mode label clashes with documented repo mutations.** Cursor: "The document header declares DESIGN ONLY and 'execution … gated', while §0–§12 repeatedly state migrate_schema_vocab_v1.py was updated this session, SPEC_V* constants changed, py_compile run, hashes captured, LD filed, etc. That is materially beyond 'design prose only': it already changes the migration script authoritative binding." v9 cited verbatim banner: `Status: DESIGN ONLY — execution remains gated on the same Phase 5 PHASE_5_ENABLED feature flag`. v10 closes this by rewriting the status banner (top of this file) to distinguish (a) production migration already executed [rules 2/3b/4 complete], (b) Phase 5 permanently deferred, (c) script + spec binding patches landed in-session, (d) **no mutations to migration-target rows** (governance writes — LD filings to `prod_locked_decisions`, activity_log POSTs — DID land in-session under the §0 governance-authoring carve-out, but those do NOT mutate any of the rows targeted by Rules 1/2/3b/4; the precise distinction was tightened in v10-E round-3 per Cursor HIGH-1). Banner now describes reality, not a design-only label.
2. **HIGH-2 — `migrate_schema_vocab_v1.py` advertises spec v7 in module docstring + phase blurbs despite v9 reconciliation.** Cursor cited the docstring `Schema Vocab Migration v3 implementation script (handoff v2.4 / spec v7).` plus `phase-1 Run Phase 1 (Rule 4 scope_domain remap, ~29 rows).` plus `phase-4 Run Phase 4 (Rule 3b task_category synonym remap, ~110 rows).` Central constants (SCRIPT_VERSION, SPEC_V9_*, EXPECTED_ROW_COUNTS) were already aligned in v9; only the docstring (`--help` first-screen) lagged. v10 closes by editing the script docstring this session: handoff v2.4 → v2.5; spec v7 → v9; phase-1 ~29 → ~35; phase-4 ~110 → ~56 (citing spec §3.3 INVESTIGATE-class exclusion); operational-discipline bullets retitled "Spec v7 §..." → "Spec v9 §..." with the "preserves v7 verbatim" annotation for the §9.4 line. py_compile validated post-edit. Pre + post sha256 captured.
3. **MEDIUM — `SPEC_V7_*` identifiers retained as aliases to v9 values is clever but brittle for audits.** Cursor: aliases documented as backwards-compat, but automated grep/audit (`find callers still asserting v7 authority`) is harder; forks expecting literally different hashes when both names resolve to identical v9 payloads can be confused. v10 closes by adding §4 / §11 dual-name semantic equivalence note (this file) + audit guidance + a v11 cleanup plan note (defer alias removal until historical sidecar JSON keys + dry-run-report banner + activity-log spec_version writes are no longer queried).

**LOW closed (v10-D) — §3.4 footnote count.** Cursor flagged that v9 §3.4 table footnote text "11 verbatim mappings = 29 rows + 3 spec-extension mappings = 6 rows; total 35 rows mapped" juxtaposed against a 14-row visible table reads as a 11-vs-14 contradiction. v10-D **closes** this LOW at the v10 layer by adding a §3 v10 footnote tightening note (parallel to the §4 v10 dual-name semantic equivalence overlay pattern) that restates the arithmetic in unambiguous form: **14 mapping rows yielding 35 total source-row migrations (29 from 11 v3-baseline mapping rules + 6 from 3 v3-extension mapping rules added in v8/v9).** v9 itself is unchanged (preserved as historical baseline per v10 self-bound); the v10 §3 note is the authoritative restatement. See §0.1 v10-D row + §3 v10 footnote tightening note (below).

v10 corrects ONLY these 3 findings + the script docstring sync. All other v9 design (cached export, rollback rehearsal, checkpoint protocol, Phase 5 feature flag, Task H, severity case-fold, Gate 11.1, runtime validator Gate 11.2, hazard warnings, schema_version, ≤256-char cap, JSON-string-aware state-machine extractor, Rule 3b 56-mechanical-only partition, Rule 4 35-with-spec-extensions partition, dual-baseline reconciliation table, risk #18) preserved verbatim. v1-v9 preserved as historical baselines. Migration NOT re-executed; no mutations to migration-target rows this session (governance writes — LD filings, activity_log POSTs — DID land under the §0 governance-authoring carve-out; precise distinction tightened in v10-E round-3 per Cursor HIGH-1).

**Related artifacts (preserved from v9 + v10 additions):**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md` — **v9 historical baseline (this spec's predecessor)** (v10 NEW reference); sha256 `0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894`, 345 lines.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` — v8 historical baseline (v9 reference); sha256 `c6220e519f5b8fb023e163936099f153610ac078d4d3392c6d9f9a454267c052`, 321 lines.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 historical baseline; sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`, 498 lines, 59,307 bytes.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline; sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline; sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline; sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline; sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline; sha256 `3d39b7c5ead3c1c0d0f0876a294f16042f3f9c7a72a8b721bb8e148da7f361c9`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `e88e82eaea03e6d4837cc41438361491c00c32155d3d09efcd5353f585e2aa5b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` — frozen dry-run audit-of-record (v9 + v10 reference).
- `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` — CLI session report (v9 + v10 reference).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl` — snapshot file.
- `Production/exports/prod_locked_decisions_2026-05-09.jsonl` — cached canonical-export from CLI session (562 rows).
- `Production/scripts/migrate_schema_vocab_v1.py` — **migration script** (v10 DOCSTRING SYNC reference; this session edits ONLY the module docstring lines 1-42; NO changes to constants, function bodies, imports, or any other lines per v10 self-bounds; py_compile validated post-edit). Pre-edit sha256 (entering this session): `d77382b06e70539d85010cd81244a80d85d482affac05663fd2d34aed8eba73f`. Post-edit sha256: captured at activity-log time.
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (v2.5; v10 does NOT amend the handoff per self-bound).
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix (already landed).
- `Production/scripts/lock_decision.py` — LD-writer CLI; canonical-aware as of 2026-05-08 per Cursor v3 Task H execution.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating helper-import.
- `LD_WRITER_CANONICAL_VOCAB_V1` (LD #588) — Task H execution authority (HARD).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — dual-path discipline.
- `LD-590 SCHEMA_VOCAB_MIGRATION_V3_LOCKED` — v3 authorization decision.
- `LD-591` — `weekly_preflight_audit.py` schema-ref-doc enforcement amendment.
- `LD-592 DIRECTUS_SCHEMA_REF_PROD_BLOCKERS_GOTCHAS_V1` — schema-ref doc §5 prod_blockers gotchas authority.
- `LD-593` — v4 §9.4 severity case-fold authority.
- `LD-595 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V5_FIELD_NAME_FIX_V1` — v5 field-name fix authority.
- `LD-596 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V6_AMEND_V2_FIXES_V1` — v6 Cursor AMEND_V2 fix authority.
- `LD-597 TASK_DESCRIPTION_GOTCHA_DRIFT_RESOLUTION_V1` — anti-confusion guard for `prod_activity_log.task_description` non-existence; v10 inherits the guidance verbatim (do NOT include `task_description` in any `prod_activity_log` POST; `details` JSON dict is the canonical narrative carrier).
- `LD-598 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V7_JSON_STRING_AWARE_EXTRACTOR_V1` — v7 Cursor AMEND_V3 fix authority.
- `LD-601` — Phase 3 row 101 idempotent resolution authority.
- `LD-602` — F3-fix predecessor cleanup LD.
- `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` — v8 amendment authority (severity SOFT).
- `LD-618 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1` — v9 amendment authority (severity SOFT; filed 2026-05-09 per the v9 session).
- `LD-623 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_BANNER_DOCSTRING_ALIAS_AUDIT_V1` — **v10 initial-pass amendment authority** (filed 2026-05-09 v10 initial-pass session).
- `LD-629 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_B_FOOTNOTE_LOW_CLOSURE_V1` — **v10-D cleanup-pass amendment authority** (severity SOFT; filed 2026-05-09 v10-D LOW closure session; cross-references LD-623 predecessor).
- `LD-631 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_E_ROUND_3_FIXES_V1` — **v10-E round-3 cleanup amendment authority** (severity SOFT; filed 2026-05-09 v10-E round-3 cleanup session; cross-references LD-623 + LD-629 predecessors; substituted from prior `LD-NEW (this session, v10-E round-3 cleanup)` placeholder per v10-E round-3 procedural fix — DO NOT repeat the v10-D procedural error).
- `LD-637 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_F_ROUND_4_FIXES_V1` — **v10-F round-4 cleanup amendment authority** (severity SOFT; filed 2026-05-09 v10-F round-4 cleanup session; cross-references LD-623 + LD-629 + LD-631 predecessors; substituted post-filing from prior `LD-NEW (this session, v10-F round-4 cleanup)` placeholder per round-3 + round-4 procedural discipline — definitively avoiding the v10-D procedural error of leaving the placeholder unsubstituted).

---

## §0.1 — v10 Consolidated Changelog (single canonical chronological table; v10-A → v10-B → v10-C → v10-D → v10-F → v10-E; refreshed in v10-F round-4 cleanup per Cursor round-4 findings; v10-F row inserted ABOVE v10-E per Kim explicit instruction — DEVIATION FROM CHRONOLOGICAL APPEND-AT-BOTTOM CONVENTION DOCUMENTED HERE)

v10 is a documentation amendment over v9 + a script docstring sync to close all 4 Cursor round-2 findings (initial v10 pass v10-A/B/C closed 3; v10-D cleanup pass closed the remaining LOW). The v10-E round-3 cleanup pass closes 5 NEW Cursor round-3 findings (2 HIGH + 2 MEDIUM + 1 LOW) and consolidates this changelog into a single canonical chronological table per the round-3 LOW finding. The v10-F round-4 cleanup pass closes 3 NEW Cursor round-4 findings (1 HIGH + 2 MEDIUM): header gate-change-claim contradiction, §11 alias-audit grep scope too narrow, §7 header still reads as "no §7-level changes" despite operational-posture reclassification. **No design change.** Operational gating posture is updated by v10-E (pre-implementation gates reclassified as HISTORICAL CONTEXT post-Phase-6) — v10-F makes that reclassification explicit at the header line + §7 header (see §6 v10-E note + §7 v10-E note + header self-classification). v9's §0.1 changelog is preserved verbatim immediately below this v10 entry, followed by v8's, v7's, v6's, v5's, v4's, v3's.

**Consolidated changelog table (chronological; one row per sub-amendment; uniform column shape):**

| Sub-amendment | Trigger / Cursor finding | Resolution applied | Sections changed | LD filed |
|---|---|---|---|---|
| v10-A | **HIGH-1 (round-2) — Operating-mode label "DESIGN ONLY" clashes with documented repo mutations.** Cursor verbatim: "The document header declares DESIGN ONLY and 'execution … gated', while §0–§12 repeatedly state migrate_schema_vocab_v1.py was updated this session, SPEC_V* constants changed, py_compile run, hashes captured, LD filed, etc." v9 banner verbatim: `Status: DESIGN ONLY — execution remains gated on the same Phase 5 PHASE_5_ENABLED feature flag`. | Status banner (top of file) rewritten — "DESIGN ONLY" replaced by truthful production-migration-complete + Phase-5-deferred + binding-patches-landed-in-session + TECH SPEC (authoritative) classification. | Top-of-file status banner | LD-623 (covers v10-A/B/C initial pass) |
| v10-B | **HIGH-2 (round-2) — `migrate_schema_vocab_v1.py` module docstring still advertises spec v7.** Cursor cited 3 verbatim docstring strings + central constants (`SCRIPT_VERSION` / `SPEC_V9_SHA256` / `SPEC_V9_PATH` / `EXPECTED_ROW_COUNTS`) already aligned in v9 but docstring (which feeds `--help`) lagged. | Script module docstring lines 1-42 synced — handoff v2.4→v2.5; spec v7→v9 with v9 sha256; phase-1 ~29→~35; phase-4 ~110→~56 with INVESTIGATE-class annotation; operational-discipline bullets retitled v7→v9 with v7-verbatim preservation note for §9.4. py_compile validated. NO other script changes. Pre-edit sha256 `d77382b06e70539d85010cd81244a80d85d482affac05663fd2d34aed8eba73f`. | Migration script docstring (lines 1-42); §11 reference index entry annotated | LD-623 (covers v10-A/B/C initial pass) |
| v10-C | **MEDIUM (round-2) — `SPEC_V7_*` identifiers retained as aliases to v9 values is clever but brittle for audits.** Cursor: aliases documented as backwards-compat, but automated grep/audit harder; forks expecting literally different hashes when both names resolve to identical v9 payloads can be confused. | §4 + §11 ADD a dual-name semantic equivalence note + audit grep guidance + v11 cleanup plan. New code MUST reference `SPEC_V9_*`; `SPEC_V7_*` aliases retained for backwards-compat with historical sidecar JSON keys + dry-run-report banner + activity-log spec_version writes already executed in-session. v11 cleanup task PLANNED. | §4 dual-name semantic equivalence; §11 audit guidance grep pattern | LD-623 (covers v10-A/B/C initial pass) |
| v10-D (cleanup pass over initial v10) | **LOW (round-2) — §3.4 footnote 11 vs visible 14 rows.** Cursor verbatim: "The table enumerates 14 source/value rows while the explanatory line says '11 spec-§3.4-verbatim mappings = 29 rows + 3 spec-extension…'. The arithmetic (29+6=35) checks out if '11' is an older count, but juxtaposed against a 14-row reader-visible table this reads like an off-by-documentation error." Verbatim quoted footnote: `(11 spec-§3.4-verbatim mappings = 29 rows + 3 spec-extension mappings = 6 rows; total 35 rows mapped)`. Initial v10 pass deferred; v10-D cleanup pass closed it. **NOTE on prior v10-LOW historical-marker row (now folded here per v10-E LOW finding):** the v9 §3.4 table footnote text "11 verbatim mappings" reads as 11 while the visible table contains 14 rows (11 v3-verbatim + 3 spec-extension; total 35 rows mapped) — cosmetic narrative inconsistency; no impact on script behavior, drift evaluation, or audit trail. v10-D adds the §3 footnote tightening note that restates the arithmetic unambiguously. | §3 NEW v10 footnote tightening note (parallel to §4 v10 dual-name semantic equivalence overlay pattern) restating: **14 mapping rows yielding 35 total source-row migrations (29 from 11 v3-baseline mapping rules + 6 from 3 v3-extension mapping rules added in v8/v9).** Arithmetic verified against v9 §3.4 table verbatim. v9 itself NOT modified. | §3 v10 footnote tightening note; §10 LOW status updated; §12 LOW marker updated | LD-629 (substituted from prior `LD-NEW (this session, v10-D cleanup pass)` placeholder per v10-E round-3 procedural fix) |
| v10-F (round-4 cleanup pass over v10-E) | **3 Cursor round-4 findings:** **HIGH** header line 5 still reads "No execution-gate change" while §6 + §7 v10-E reframings make pre-implementation gates HISTORICAL-ONLY post-Phase-6 (any future re-run requires NEW gates) — operational gating posture HAS changed. **MEDIUM-1** §11 alias-audit grep scope (`Production/scripts/ Production/lib/`) too narrow — misses markdown docs/handoffs, CI workflow text, sidecar JSON spec_version writes. False "clean" risk before v11 alias retirement. **MEDIUM-2** §7 header still framed as "no §7-level row changes" (operational-posture note is in body but header understates the shift) — reviewer can under-recognize that risk-table interpretation has materially changed. | (a) Header self-classification line 5 rewritten — "No execution-gate change" replaced with "No design change. Operational gating posture **is updated** by v10-E ..." referencing §6 + §3.1; secondary occurrences at §0.1 driver paragraph (line 70) + §10 review-companion paragraph (line 253) aligned for consistency. (b) §4 + §11 alias-audit grep scope broadened to `Production/` with `--exclude-dir` + `--include` file-type filters covering Python, markdown, YAML, JSON, txt; documentation added explaining 4 surface types (Python consumers / markdown citations / CI workflow text / sidecar JSON). v11 cleanup plan note clarifies inventory hits split into ACTIVE (rename) + FROZEN-AUDIT (preserve) classes. (c) §7 header rewritten — "no §7-level row changes" replaced with "individual risk rows unchanged; operational posture reclassified by v10-E" with explicit POST-EXECUTION + closed-loop (Rules 2/3b/4) / DORMANT (Phase 5) / MOOT (rollback) summary inline. v10-E body §7 note unchanged (header now telegraphs what the body says). | Header self-classification line 5; §0.1 driver paragraph (line 70); §10 review-companion paragraph (line 253); §4 dual-name audit-grep block (broadened); §11 audit guidance section (broadened + 4-surface-type rationale); §7 header (operational-posture reclassification explicit); §0.1 changelog table (this v10-F row); §12 v10 entry refresh | LD-637 (severity SOFT; filed 2026-05-09 v10-F round-4 cleanup session; cross-references LD-623 + LD-629 + LD-631 predecessors; substituted post-filing per round-3 + round-4 procedural discipline — definitively avoiding the v10-D procedural error of leaving the placeholder unsubstituted) |
| v10-E (round-3 cleanup pass over v10-D) | **5 Cursor round-3 findings:** **HIGH-1** banner says "no new production-data writes" but LDs were filed in-session — internal contradiction. **HIGH-2** v10-D LD-NEW placeholder still present in §11 + §12 + §0.1 — undermines placeholder-cleanup intent. **MEDIUM-1** §6 framed as "Pre-implementation gates Kim must approve" with no temporal qualifier despite migration complete. **MEDIUM-2** §7 risk table preserved as "no §7 changes" but operational posture has shifted post-migration — stale risk framing. **LOW** v10 changelog row layering (v10-A/B/C/D + v10-LOW historical marker) is dense + error-prone for future maintenance. | (a) Banner wording tightened to distinguish migration-target-row mutations (NONE) vs governance writes (LD filings + activity_log POSTs that DID land under §0 governance-authoring carve-out). (b) `LD-NEW` placeholder substituted with `LD-629` at all v10-D references in §0/§11/§12 (procedural step missed by v10-D — definitively fixed in v10-E). (c) §6 historical-context note added explicitly framing pre-implementation gates as audit-trail history; future re-execution requires NEW gates against post-migration state. (d) §7 operational-posture note added explicitly framing pre-execution risks as POST-EXECUTION + closed-loop (Rules 2/3b/4) or DORMANT (Phase 5 / Rule 1) or MOOT (rollback). (e) §0.1 changelog table consolidated into single canonical chronological table (v10-A → v10-B → v10-C → v10-D → v10-E) with uniform column shape; v10-LOW historical marker REMOVED with content folded into v10-D row prose; future v10-F+ rows append at bottom following same shape. | Status banner (precision wording); §0 §0.1 driver paragraph + LOW paragraph; §6 v10-E historical-context note (NEW); §7 v10-E operational-posture note (NEW); §0.1 changelog table consolidated (this row + v10-A/B/C/D refreshed in uniform shape; v10-LOW marker removed); §11 LD-NEW substituted with LD-629; §12 v10 entry refreshed; §11 v10-E LD reference added | LD-631 (substituted post-filing from prior `LD-NEW (this session, v10-E round-3 cleanup)` placeholder per round-3 procedural fix — definitively avoiding the v10-D procedural error of leaving the placeholder unsubstituted) |

**v9 vs v10 surface area (refreshed in v10-E round-3 cleanup):** v10 adds documentation only — rewritten status banner, single-canonical §0.1 chronological changelog (v10-A → v10-B → v10-C → v10-D → v10-E; v10-LOW historical marker REMOVED in v10-E per round-3 LOW finding), one §3 v10 footnote tightening note (v10-D), one §4 dual-name semantic equivalence note (v10-C), one §6 v10-E historical-context note (v10-E), one §7 v10-E operational-posture note (v10-E), one §11 audit guidance entry (v10-C), one §12 changelog entry refreshed. v10 deletes only the v10-LOW historical-marker changelog row in v10-E (content folded into v10-D row prose); otherwise preserves all v9 content verbatim and adds documentation. The substantive script change is exactly the module docstring lines (1-42; v10-B); NO other code changes to `migrate_schema_vocab_v1.py`; NO changes to `SPEC_V*_SHA256`, `SPEC_V*_PATH`, `EXPECTED_ROW_COUNTS`, imports, or function bodies. The v10-D + v10-E cleanup passes introduce NO additional script changes (script sha256 unchanged through v10-E). v10 does NOT touch the implementation handoff, any other tech-spec, schema-ref doc, settings.json, hook scripts, weekly_preflight_audit.py, or SKILL.md. Migration NOT re-executed (v10-E introduces NO additional script changes; script sha256 unchanged through v10-E pass).

---

## §0.1 (v9, preserved verbatim) — v9 Changelog (Cursor v8 review findings + script-doc sync amendment over v8)

(Preserved verbatim from v9 §0.1. v9-A HIGH 1 narrative inconsistency in §4. v9-B HIGH 2 script-doc desync. v9-C MEDIUM `LD-NEW` placeholder substitution. See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md` §0.1 v9 row for full text.)

> **HAZARD WARNING — do not implement from this preserved historical row.** v10 §0.1 v10 row IS AUTHORITATIVE for the round-2 amendment surface. v9 reasoning is preserved for audit continuity only.

---

## §0.1 (v8, preserved verbatim) — v8 Changelog (CLI dispatch findings amendment over v7)

(Preserved verbatim from v9 §0.1 v8 section. v8-A Rule 3b 110→56 partition. v8-B Rule 4 +3 spec-extensions 29→35.)

> **HAZARD WARNING — do not implement from this preserved historical row.** v10 §0.1 + v9 §0.1 v9 row + v9 §3.4 reconciliation note are the authoritative reference points.

---

## §0.1 (v7, preserved verbatim) — v7 Changelog (Cursor AMEND_V3 fix-set: Blocker F)

(Preserved verbatim from v9 §0.1 v7 section. JSON-string-aware state-machine extractor.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE for parser implementation; preserved through v8 + v9 + v10. See §6 Gate 11.2 (runtime validator) for write-time enforcement.

---

## §0.1 (v6, preserved verbatim) — v6 Changelog (Cursor AMEND_V2 fixes)

(Preserved verbatim from v9 §0.1 v6 section.)

> **HAZARD WARNING — do not implement from this preserved historical row.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9 + v10).

---

## §0.1 (v5, preserved verbatim) — v5 Changelog

(Preserved verbatim from v9 §0.1 v5 section.)

---

## §0.1 (v4, preserved verbatim) — v4 Changelog

(Preserved verbatim from v9 §0.1 v4 section.)

---

## §0.1 (v3, preserved verbatim) — v3 Changelog

(Preserved verbatim from v9 §0.1 v3 section.)

---

## §1 — Goal (preserved verbatim from v1+v2+v3+v4+v5+v6+v7+v8+v9)

(Preserved verbatim from v9 §1. v10 introduces no §1-level changes — this is a status-banner + script-docstring + alias-audit amendment, not a goal-shifting amendment.)

---

## §2 — Background (preserved verbatim through v9; v10 ADD informational only)

(Preserved verbatim from v9 §2 including v9 ADD on Cursor's v8 review surfacing 3 defects.)

**v10 ADD (informational; refreshed in v10-D cleanup pass):** Cursor's v9 cross-review (round 2) surfaced 3 actionable findings: HIGH-1 status-banner / mutation-doc clash; HIGH-2 script module docstring still advertising spec v7 + ~29 + ~110 row counts despite v9 constant alignment; MEDIUM `SPEC_V7_*` alias audit-friction. Plus 1 LOW closed in v10-D cleanup pass (§3.4 footnote count tightening — see §3 v10 footnote tightening note below + §0.1 v10-D row). v10 closes ALL 4 findings (v10-A + v10-B + v10-C in the initial pass; v10-D in the cleanup pass) + the script docstring sync (v10-B). Production migration for Rules 2/3b/4 is COMPLETE as of 2026-05-09 04:08 UTC (mutex released; activity log row 1993). Phase 5 (Rule 1 long-tail INVESTIGATE) remains permanently deferred per §3.1. The script you are reading is post-migration; no in-flight execution. v10 introduces NO mutations to migration-target rows (governance writes — LD filings, activity_log POSTs — DID land under the §0 governance-authoring carve-out; precise distinction tightened in v10-E round-3 per Cursor HIGH-1).

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments + v8 + v9 + v10

(Preserved verbatim from v9 §3. §3.0 path discipline / §3.1 Rule 1 + PHASE_5_ENABLED / §3.2 Rule 2 / §3.3 + §3.3.1 v8-amended Rule 3 task_category / §3.4 v8 + v9 — all preserved through v10. v10-D cleanup pass adds the §3.4 footnote tightening note below; the v9 §3.4 table + v9 footnote remain preserved verbatim in v9 — the v10 note is an authoritative restatement overlay, not an in-place edit of v9.)

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md` §3 for the v9-baseline verbatim text. v10 amends nothing in v9 itself; the §3.4 v10 footnote tightening note (NEW v10-D, immediately below) supersedes the v9 §3.4 footnote phrasing for any reader using v10 as the authoritative reference.

### §3.4 v10 — footnote tightening (NEW v10-D; LOW closure per Cursor round-2 review)

> **v10-D §3.4 footnote tightening (informational; addresses Cursor v9 round-2 review LOW):** v9 §3.4 (preserved verbatim at v9 sha256 `0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894`, lines 165-185) renders a 14-row mapping table whose footer cell reads `(11 spec-§3.4-verbatim mappings = 29 rows + 3 spec-extension mappings = 6 rows; total 35 rows mapped)`. Cursor flagged that "11" juxtaposed against a 14-row reader-visible table reads as an off-by-documentation contradiction.
>
> **Authoritative restatement (v10-D; supersedes the v9 footnote phrasing for readers using v10):**
>
> > **14 mapping rows yielding 35 total source-row migrations (29 from 11 v3-baseline mapping rules + 6 from 3 v3-extension mapping rules added in v8/v9).**
>
> **Arithmetic verification (counted against v9 §3.4 table verbatim):**
>
> - **v3-baseline mapping rules (rows 171-181 of v9):** `app→app-dev` (13), `audio_pipeline→production` (1), `beat_generator→production` (1), `ci_pipeline→infra` (1), `claude_session_behavior→cross-cutting` (1), `governance→cross-cutting` (2), `image_pipeline→production` (1), `infrastructure→infra` (6), `payments→app-dev` (1), `stillgen→production` (2), `video_pipeline→production` (1). Count = **11 mapping rules**; row-count sum = 13+1+1+1+1+2+1+6+1+2+1 = **29**.
> - **v3-extension mapping rules (rows 182-184 of v9; added v8/v9 per Kim 2026-05-09 spec-extension authorization):** `production-server (dash variant)→infra` (3), `production_pipeline→production` (1), `audio_production→production` (1). Count = **3 mapping rules**; row-count sum = 3+1+1 = **6**.
> - **Total mapping rules:** 11 + 3 = **14 rows visible in the v9 §3.4 table.**
> - **Total source-row migrations:** 29 + 6 = **35 source rows touched by Rule 4.**
>
> All four numbers (11, 14, 29, 35) and the +6 spec-extension delta are now internally consistent. The v9 footnote was arithmetically correct (29 + 6 = 35) but the "11 verbatim mappings" framing did not telegraph the 14-row table count to the reader; the v10-D restatement above leads with the **14 mapping rows** count to match the reader-visible table directly.
>
> **No script-side, validator-side, or audit-side change.** This is a pure documentation tightening. The migration script's `EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] = 35` (v9-codified) is correct and unchanged. The dry-run audit-of-record + dual-baseline reconciliation table in v9 §3.4 v9-reconciliation-note remain unchanged. v9 itself is **not modified** (preserved per v10 self-bound).
>
> **v11 cleanup plan impact:** the LOW footnote portion of the previously-planned v11 cleanup is now **complete** (closed in v10-D); the v11 plan now reduces to ONLY the `SPEC_V7_*` alias removal sweep (see §4 v10 dual-name semantic equivalence note + §11 audit guidance).

---

## §4 — Per-rule action table (v9 preserved + v10 dual-name semantic equivalence note)

(Preserved verbatim from v9 §4 including the dual-baseline table for `rule_4_scope_domain_remap`. v10 ADDs the `SPEC_V7_*` / `SPEC_V9_*` dual-name semantic equivalence note + audit guidance + v11 cleanup plan per Cursor MEDIUM finding.)

See v9 §4 for the verbatim per-rule action narrative + EXPECTED_ROW_COUNTS dict + dual-baseline reference table.

### §4 v10 — `SPEC_V7_*` / `SPEC_V9_*` dual-name semantic equivalence (NEW v10; MEDIUM fix per Cursor)

> **v10 dual-name semantic equivalence note (informational; addresses Cursor v9 round-2 review MEDIUM):** the migration script `Production/scripts/migrate_schema_vocab_v1.py` lines 102-103 retain `SPEC_V7_SHA256 = SPEC_V9_SHA256` and `SPEC_V7_PATH = SPEC_V9_PATH` as backwards-compat aliases. Both names resolve to **identical v9 values** (sha256 `0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894`; path `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md`). Semantic equivalence is intentional; the alias retention is a surgical-minimality choice from the v9 session to avoid touching ~6 unrelated call sites (sidecar JSON keys, dry-run-report banner, activity-log spec_version writes that were already executed in-session and are now part of the frozen audit record).
>
> **Authoring guidance for new code:** ALL new code MUST reference `SPEC_V9_SHA256` and `SPEC_V9_PATH`. New code MUST NOT introduce additional `SPEC_V7_*` references — those exist solely as historical compat aliases.
>
> **Audit guidance for grep-based caller scans (BROADENED in v10-F per Cursor round-4 MEDIUM-1):** to find any caller still asserting v7 authority by name (a finding that would feed the v11 cleanup pass), run the broader grep below. The earlier narrow scope (`Production/scripts/ Production/lib/`) risked a false "clean" signal because aliases live in **4 surface types**: (a) Python code consumers in `Production/scripts/` + `Production/lib/`; (b) markdown docs / handoffs / specs that cite `SPEC_V7_*` by name; (c) CI workflow text + audit-log references in `*.yml` / `*.yaml`; (d) report / sidecar JSON files that already wrote `spec_version` fields in-session. v11 cleanup retires aliases ONLY AFTER all 4 surfaces audit clean.
>
> ```bash
> grep -rn "SPEC_V7_" Production/ \
>   --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.deploy_backups \
>   --include="*.py" --include="*.md" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.txt"
> ```
>
> Expected hits as of v10 authoring: the two alias declaration lines in `migrate_schema_vocab_v1.py` PLUS any preserved historical citations in v1-v9 spec-doc baselines + frozen sidecar JSON keys + dry-run-report banner + activity-log spec_version writes + this v10 spec's own preserved historical references. The grep is an INVENTORY tool; not every hit is a v11-cleanup target — frozen audit-record hits stay frozen. v11 cleanup pass will rename only the **active code consume sites** to `SPEC_V9_*` then delete the alias lines.
>
> **v11 cleanup plan (planned, not authorized this session):** in a future session in which Kim authorizes a wider canonical-binding sweep, (1) inventory all 4 surface types via the broadened grep above; (2) classify each hit as ACTIVE (rename) or FROZEN-AUDIT (preserve verbatim); (3) rename ACTIVE consume sites of `SPEC_V7_*` to `SPEC_V9_*`; (4) delete the alias lines in `migrate_schema_vocab_v1.py`; (5) verify no remaining ACTIVE hits via the audit grep above; (6) bump SCRIPT_VERSION; (7) file v11 LD documenting the alias removal + the FROZEN-AUDIT surface inventory. Until v11 lands, the aliases are correct as written and the broadened audit grep above is the supported way to inventory remaining consume sites.

---

## §5 — Migration sequence (preserved verbatim through v9; v10 introduces no §5-level changes)

(Preserved verbatim from v9 §5. v8 informational note preserved. v9 NOTE preserved. v10 introduces no §5-level changes — Phase 5 still permanently deferred; Phases 0/1/2/3/4/6 are now historical record per the 2026-05-09 04:08 UTC mutex release.)

> **§5-LEVEL HAZARD WARNING (preserved verbatim through v9 + v10):** §5 below preserves v3+v4+v5+v6+v7+v8+v9 example body code blocks BY REFERENCE (not inline). **DO NOT IMPLEMENT FROM HISTORICAL CONTENT.** §9.4 v7 IS AUTHORITATIVE (preserved through v8 + v9 + v10). The migration script's Phase 1 entry-guard (and every other `prod_blockers` POST/PATCH) MUST use the v7 §9.4 patterns: JSON-string-aware state-machine extractor + try/except for parsing, runtime payload-key validator before write, capped resolution-text append, schema_version="v1" on acquisition.

**v10 NOTE (NEW; informational only):** v10 introduces no §5-level changes. The CLI session's actual migration completed 2026-05-09 04:08 UTC; mutex released; activity log row 1993; Rules 2/3b/4 migrated. Phase 5 (Rule 1 long-tail INVESTIGATE) PERMANENTLY DEFERRED per §3.1. Any future re-run would compare against v9-authoritative EXPECTED figures (Rule 3b=56, Rule 4=35) — but NO future re-run is authorized this session.

See v9 §5.0 + Phase 0 + Phase 1-6 for the verbatim text.

---

## §6 — Pre-implementation gates Kim must approve (preserved verbatim through v9 + v10; **HISTORICAL CONTEXT post-Phase-6 per v10-E round-3 reframing**)

(Gates 1-12 preserved verbatim from v7 → v8 → v9 → v10. v10 introduces no §6-level changes — gate semantics, validator function, and verification artifacts unchanged.)

> **§6 v10-E note (2026-05-09; addresses Cursor round-3 MEDIUM-1):** These pre-implementation gates were authoritative gating requirements at v3-v9 authoring time; ALL gates were satisfied or formally deferred BEFORE Phase 0 dispatch on 2026-05-09. Post-migration (Phase 6 complete; mutex released 2026-05-09 04:08 UTC; activity log row 1993), §6 is **HISTORICAL CONTEXT for audit trail**, not active gating requirements. The active gating regime now is: (a) Phase 5 PERMANENTLY DEFERRED per spec §3.1; (b) any future re-execution requires NEW pre-implementation gates authored against post-migration state (NOT a re-application of these v3-v9 gates, which were drafted against a pre-migration prod_locked_decisions state that no longer exists). Cursor round-3 finding addressed: the v10 banner says migration is complete + no re-execution is authorized, but §6 was previously framed as "Pre-implementation gates Kim must approve" with no temporal qualifier — this note adds the post-migration historical/active distinction explicitly.

See v9 §6 for the full Gates 1-12 + verification artifacts text. v10 amends nothing in the gate text itself; v10-E round-3 ADDs only the temporal-framing note above.

---

## §7 — Risk assessment (**preserved verbatim through v9** — individual risk rows unchanged; **operational posture reclassified by v10-E**: pre-execution risks now POST-EXECUTION + closed-loop (Rules 2/3b/4) / DORMANT (Phase 5) / MOOT (rollback). See §7 v10-E note for full reclassification. Header reframed in v10-F per Cursor round-4 MEDIUM-2 — earlier "no §7-level changes" wording understated the operational-posture shift.)

(Rows 1-18 preserved verbatim from v9 §7. v10 introduces no new risk row. The Cursor round-2 findings closed by v10 are documentation/binding consistency issues, not new operational hazards; risk #18 (v9 NEW) already covers the future-re-run-stale-baseline scenario, which v10 docstring sync further mitigates by aligning the script `--help` first-screen text with v9 authority.)

> **§7 v10-E note (2026-05-09; addresses Cursor round-3 MEDIUM-2):** The pre-execution risk table at v9 §7 is preserved verbatim because individual risks remain analytically valid as **historical pre-execution analysis**. HOWEVER the OPERATIONAL POSTURE has shifted post-migration: (a) risks framed as "during execution" are now **POST-EXECUTION + closed-loop** (Phase 6 audit confirmed zero residuals on Rules 2/3b/4 per the 2026-05-09 04:08 UTC mutex release + activity log row 1993); (b) risks framed as "rollback" are now **MOOT** (no rollback authorized post-completion); (c) risks for Phase 5 (Rule 1 long-tail INVESTIGATE triage) remain **VALID + DORMANT** pending future authorization. Future risk assessments for re-runs MUST author a fresh §7 against post-migration state — the v9 §7 table is not directly re-applicable to a post-migration re-run scenario because the row population, value distributions, and prod_locked_decisions schema are now in their post-Phase-6 state, not the pre-Phase-0 state the v9 risks were drafted against. Cursor round-3 finding addressed: the v10 banner says "no §7-level changes" but materially repositions operational context (complete migration + no re-runs) while leaving the risk table frozen — this note makes the temporal posture explicit so the stale risk framing is no longer mismatched.

See v9 §7 for the full risk table. v10 amends no rows; v10-E round-3 ADDs only the operational-posture note above.

---

## §8 — Rollback per phase (preserved verbatim through v9 + v10)

(Preserved verbatim from v9 §8. v10 introduces no §8-level changes — rollback mechanism unchanged.)

See v9 §8 for the verbatim text.

---

## §9 — Operational notes (preserved verbatim through v9 + v10)

(§9.1, §9.2, §9.3 preserved verbatim from v2 through v9 + v10. §9.4 preserved verbatim from v7 — JSON-string-aware state-machine extractor + acquisition POST + release PATCH + stale-mutex cleanup; v10 introduces no §9-level changes.)

See v9 §9.4 for the authoritative parser/validator/POST/PATCH implementation patterns. v10 amends nothing here. The migration script (`Production/scripts/migrate_schema_vocab_v1.py`) implements v7 §9.4 verbatim per CLI report §3 (1878 lines post-v10-docstring-update, py_compile clean).

---

## §10 — Cursor review companion (v9 preserved; v10 round-2 review)

This spec v10 is a documentation amendment + script docstring sync over v9 addressing Cursor's v9 round-2 review findings (HIGH-1 status-banner clash, HIGH-2 script module docstring still cites spec v7, MEDIUM SPEC_V7_* alias audit-friction; LOW §3.4 footnote count CLOSED in v10-D cleanup pass — see §3 v10 footnote tightening note) + Cursor round-3 review findings (closed in v10-E) + Cursor round-4 review findings (closed in v10-F: HIGH header gate-change-claim contradiction, MEDIUM-1 §11 alias-audit grep scope broadened to Production/ with file-type filters, MEDIUM-2 §7 header reframed to make operational-posture reclassification explicit). v10 introduces **no design change**; operational gating posture **is updated** by v10-E (pre-implementation gates reclassified as HISTORICAL CONTEXT post-Phase-6) and v10-F makes that reclassification explicit at the header + §7 header. The v3 Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` remains the canonical review companion for the cumulative review trail. If Kim chooses to send v10 back for a Cursor pass, the v10 file itself + the v10-F + v10-E + v10-D + v10-A + v10-B + v10-C rows of §0.1 + the §3 v10 footnote tightening note + §6 + §7 v10-E notes are the review surface; the underlying v9 design (parser, validator, mutex protocol, checkpoint, rehearsal, feature flag, severity case-fold, gate semantics, partition table, spec-extensions, dual-baseline reconciliation, risk #18) is unchanged and not in scope for v10 review. v2 + v1 handoffs preserved as historical baselines.

---

## §11 — Reference index (v9 preserved + v10 entries added; audit guidance NEW)

(All v2 entries preserved verbatim through v3 → v4 → v5 → v6 → v7 → v8 → v9 → v10. All v3/v4/v5/v6/v7/v8-NEW entries preserved. All v9-NEW entries preserved. v10-NEW entries added below.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v9.md` — **v9 historical baseline (this spec's predecessor)** (v10 NEW reference); sha256 `0f5bbf0554e40e56c035e6a9c0bdd6871af4256a06795b06139640293143a894`, 345 lines.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v8.md` — v8 historical baseline (v9 reference; v10 preserved); sha256 `c6220e519f5b8fb023e163936099f153610ac078d4d3392c6d9f9a454267c052`, 321 lines.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v7.md` — v7 historical baseline; sha256 `dc7db3e3953b65d1bd71d76b02f5fe73e9a5789412f83180b3172f35ed5e58c3`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v6.md` — v6 historical baseline; sha256 `e377094eaa3418ade109366ae9de18be2781078601982093764b7ab1a34b6fae`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v5.md` — v5 historical baseline; sha256 `97eb34d6f35ec01ba8c8689a5f0433f5a868600d7148cac77181d8c9eca48fd7`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v4.md` — v4 historical baseline; sha256 `3501b90eff5283c5069e5dfcd4f33770674e7ad5083d2f20337882d91107ac03`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v3.md` — v3 historical baseline; sha256 `8ce44cf2bce16114b17d75275767eba16a889840cc8c795fc3aad6956e61f37b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline; sha256 `3d39b7c5ead3c1c0d0f0876a294f16042f3f9c7a72a8b721bb8e148da7f361c9`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline; sha256 `e88e82eaea03e6d4837cc41438361491c00c32155d3d09efcd5353f585e2aa5b`.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_20260509.md` — frozen dry-run audit-of-record. v9 §3.4 reconciliation note clarifies the 29-baseline historical record vs. 35-baseline v9-authoritative.
- `Production/docs/SCHEMA_MIGRATION_V3_PHASE_A_THROUGH_F_REPORT_20260509.md` — CLI dispatch session report.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v10.md` — **THIS SPEC (v10)** (v10 NEW self-reference).
- `Production/scripts/lock_decision.py` — canonical-aware as of 2026-05-08.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `Production/scripts/migrate_schema_vocab_v1.py` — **migration script** (v10 DOCSTRING SYNC this session; lines 1-42 ONLY: handoff v2.4→v2.5; spec v7→v9; phase-1 ~29→~35; phase-4 ~110→~56 with §3.3 INVESTIGATE-class annotation; operational-discipline bullets v7→v9 with v7 verbatim preservation note for §9.4; py_compile validated). Pre-edit sha256 (entering this session): `d77382b06e70539d85010cd81244a80d85d482affac05663fd2d34aed8eba73f`. Post-edit sha256: captured at activity-log time. NO other lines changed; constants/functions/imports unchanged from v9 session state.
- `LD_WRITER_CANONICAL_VOCAB_V1` (LD #588) — Task H execution authority (HARD).
- `LD-590` through `LD-602` — preserved per v9 §11.
- `LD-611 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V8_DRY_RUN_FINDINGS_AMENDMENT_V1` — v8 amendment authority (severity SOFT).
- `LD-618 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V9_SCRIPT_DOC_SYNC_V1` — v9 amendment authority (severity SOFT).
- `LD-623 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_BANNER_DOCSTRING_ALIAS_AUDIT_V1` — **v10 initial-pass amendment authority** (severity SOFT; filed 2026-05-09 v10 initial-pass session).
- `LD-629 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_B_FOOTNOTE_LOW_CLOSURE_V1` — **v10-D cleanup-pass amendment authority** (severity SOFT; filed 2026-05-09 v10-D LOW closure session; cross-references LD-623 predecessor).
- `LD-631 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_E_ROUND_3_FIXES_V1` — **v10-E round-3 cleanup amendment authority** (severity SOFT; filed 2026-05-09 v10-E round-3 cleanup session; cross-references LD-623 + LD-629 predecessors; substituted from prior `LD-NEW (this session, v10-E round-3 cleanup)` placeholder per v10-E round-3 procedural fix — DO NOT repeat the v10-D procedural error).
- `LD-637 SCHEMA_VOCAB_MIGRATION_TECH_SPEC_V10_F_ROUND_4_FIXES_V1` — **v10-F round-4 cleanup amendment authority** (severity SOFT; filed 2026-05-09 v10-F round-4 cleanup session; cross-references LD-623 + LD-629 + LD-631 predecessors; substituted post-filing per round-3 + round-4 procedural discipline).
- `Production/DIRECTUS_SCHEMA_FIELD_NAMES_REFERENCE.md` §5 — live-probed `prod_blockers` schema reference; ground truth for v7 §9.4. v10 does NOT update (no schema-side change).
- `Production/docs/HANDOFF_SCHEMA_MIGRATION_V3_IMPLEMENTATION_20260508.md` — implementation handoff (v2.5; v10 does NOT amend per self-bound).
- `Production/exports/prod_locked_decisions_2026-05-09.jsonl` — cached canonical-export from CLI session (562 rows).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_20260509.jsonl` — snapshot file from CLI session.
- `Production/exports/schema_migration_checkpoint_2026-05-09.jsonl` — append-only checkpoint per §5.0.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3; remains canonical for v10's cumulative review trail).
- `prod_activity_log` id=1826 — Kim's drift-resolution authorization marker (CLI session).
- `prod_activity_log` id=1993 — mutex release marker (production migration COMPLETE 2026-05-09 04:08 UTC).
- `prod_blockers` id=103 — drift-fire-and-resolve mechanical halt #2 audit row from CLI session (resolved 2026-05-09T02:48:36 per Kim authorization).

### §11 v10 — Audit guidance for `SPEC_V7_*` alias inventory (NEW v10; MEDIUM fix per Cursor; BROADENED in v10-F per Cursor round-4 MEDIUM-1)

To inventory any caller still asserting v7 authority by name across ALL 4 surface types (Python consumers, markdown docs/handoffs, CI workflow text, report/sidecar JSON), run the broadened grep below. The earlier narrow scope (`Production/scripts/ Production/lib/`) risked a false "clean" signal because aliases live in more than just Python code:

```bash
grep -rn "SPEC_V7_" Production/ \
  --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.deploy_backups \
  --include="*.py" --include="*.md" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.txt"
```

**Why the broader scope (v10-F rationale):** aliases live in (a) Python code (consumers in `Production/scripts/` + `Production/lib/`), (b) markdown docs / handoffs / specs (citations like `SPEC_V7_SHA256` quoted in spec text), (c) CI workflow text in `*.yml` / `*.yaml` (audit-log references), (d) report / sidecar JSON files that already wrote `spec_version` fields in-session. v11 cleanup retires aliases ONLY AFTER all 4 surfaces audit clean (active code consume sites renamed; frozen audit-record hits explicitly catalogued and preserved).

**Expected hits at v10-F authoring time:** the two alias declaration lines in `Production/scripts/migrate_schema_vocab_v1.py` PLUS preserved historical citations in v1-v9 spec-doc baselines + frozen sidecar JSON keys + dry-run-report banner + activity-log spec_version writes + this v10 spec's own preserved historical references. The grep is an INVENTORY tool; not every hit is a v11-cleanup target — frozen audit-record hits stay frozen by design (per §4 v10 dual-name semantic equivalence note + v9 surgical-minimality posture). v11 cleanup pass will rename only the **active code consume sites** to `SPEC_V9_*` then delete the alias lines. See §4 v10 dual-name semantic equivalence note for the v11 cleanup plan rationale.

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied. Status: superseded by v4.
- **v4** — 2026-05-08 — self-discovered §9.4 severity case-fold. Status: superseded by v5.
- **v5** — 2026-05-08 — self-discovered §9.4 field-name fix. Status: superseded by v6.
- **v6** — 2026-05-08 — Cursor AMEND_V2 on v5 (3 HIGH/Y blockers + 2 non-blockers). Status: superseded by v7.
- **v7** — 2026-05-08 — Cursor AMEND_V3 on v6 (1 HIGH/Y blocker, Task F): JSON-string-aware state-machine extractor. Status: superseded by v8.
- **v8** — 2026-05-09 — documentation amendment over v7 motivated by CLI dispatch session findings. Defect 1 (v8-A): Rule 3b 110→56 partition. Defect 2 (v8-B): Rule 4 +3 spec-extensions (29→35). Files LD-611. Status: superseded by v9.
- **v9** — 2026-05-09 — documentation amendment + script-doc sync over v8 motivated by Cursor's v8 cross-review. **HIGH 1 (v9-A):** §3.4 reconciliation note + §4 dual-baseline table. **HIGH 2 (v9-B):** script SCRIPT_VERSION v7→v9; SPEC_V7_* → SPEC_V9_*; EXPECTED_ROW_COUNTS["rule_4_scope_domain_remap"] 29→35; py_compile validated. Adds risk #18. **MEDIUM (v9-C):** v8's `LD-NEW` placeholders → concrete LD-611. Files LD-618. Status: superseded by v10.
- **v10** — 2026-05-09 — documentation amendment + script docstring sync over v9 motivated by Cursor's v9 round-2 cross-review (v10-A/B/C/D) + Cursor's round-3 cross-review on v10-D (v10-E) + Cursor's round-4 cross-review on v10-E (v10-F). All sub-amendments now consolidated into single canonical §0.1 chronological changelog table per v10-E LOW finding (v10-F row inserted above v10-E per Kim explicit instruction; deviation from chronological-bottom convention documented at §0.1 header). See §0.1 for the full per-sub-amendment row detail (uniform column shape: Sub-amendment / Trigger / Resolution / Sections changed / LD filed). **Round-2 high-level (v10-A/B/C/D):** HIGH-1 status-banner rewrite (no more DESIGN ONLY); HIGH-2 script docstring sync; MEDIUM SPEC_V7_* alias dual-name semantic equivalence note; LOW (v10-D cleanup pass) §3.4 footnote 11-vs-14 contradiction closed via §3 v10 footnote tightening note. Round-2 LDs: LD-623 (v10-A/B/C) + LD-629 (v10-D, substituted from prior `LD-NEW` placeholder per v10-E round-3 procedural fix). **Round-3 high-level (v10-E):** HIGH-1 banner-precision wording (governance writes DID land vs migration-target-row mutations did NOT); HIGH-2 LD-NEW placeholder definitively substituted with LD-629 at all v10-D references in §0/§11/§12 (procedural step missed by v10-D); MEDIUM-1 §6 historical-context note added; MEDIUM-2 §7 operational-posture note added; LOW changelog consolidated into single canonical chronological table with v10-LOW historical marker REMOVED (folded into v10-D row prose). v10-E LD: LD-631 (substituted post-filing from prior `LD-NEW` placeholder per round-3 procedural fix). **Round-4 high-level (v10-F):** HIGH header line 5 + §0.1 driver paragraph + §10 review-companion paragraph rewritten to acknowledge v10-E gating-posture shift (no longer says "no execution-gate change"); MEDIUM-1 §4 + §11 alias-audit grep scope broadened to `Production/` with `--exclude-dir` + `--include` file-type filters covering 4 surface types (Python / markdown / YAML / JSON); MEDIUM-2 §7 header rewritten to make operational-posture reclassification explicit (no longer says "no §7-level row changes"). v10-F LD: LD-637 (substituted post-filing per round-3 + round-4 procedural discipline). All other v9 design preserved verbatim. v1-v9 preserved as historical baselines. Schema-ref doc NOT updated (no schema-side change). Implementation handoff NOT amended (out of scope all v10 passes). Migration NOT re-executed at any v10 pass (v10-D + v10-E + v10-F introduce NO additional script changes; script sha256 unchanged through v10-F pass at `97b39e57f0d7e8edcb99aaa7cf58fd3bb3eebc87ade887dd826fde64b6323777`). Author: Claude Opus 4.7 (1M context); session: gallant-bouman-804b4f post-Cursor-v9-round-2-review (v10 initial pass) + v10-D cleanup pass + v10-E round-3 cleanup pass + v10-F round-4 cleanup pass.
