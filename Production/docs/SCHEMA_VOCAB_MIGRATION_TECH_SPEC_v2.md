# Schema Vocab Migration — Tech Spec v2

**Authored:** 2026-05-08 (v2 amendment same day as v1).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance + data migration).
**Status:** DESIGN ONLY — execution is gated on Kim approval per §7. Phase 5 additionally gated on a feature flag (see §3 Rule 1 v2 resolution).

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` (preserved as historical baseline; do NOT edit in place).

**v1 → v2 driver:** Cursor's AMEND_V2 verdict on v1 + the companion handoff. Four amendments applied (2 HIGH, 2 MED). See §0.1 changelog for verbatim resolution per amendment.

**Related artifacts:**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — historical baseline (this spec's v1 predecessor).
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec (severity / task_category / scope_domain audit).
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed; this migration spec does NOT depend on it but COMPLEMENTS it.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating that future code import the helper rather than rolling its own dict.
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical) — handoff structure used for the Cursor review companion (see §10).
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` — companion review handoff (v2 amendments applied).

---

## §0.1 — v2 Changelog (verbatim resolution per Cursor amendment)

Cursor's AMEND_V2 verdict on v1 returned 4 amendments (2 HIGH, 2 MED). Each is reproduced verbatim in the left column with the resolution in the right column. v1 sections that needed material change are listed under "Sections changed".

| # | Severity | Cursor amendment (verbatim) | Resolution applied in v2 | Sections changed |
|---|---|---|---|---|
| 1 | HIGH | Rule 1 contradiction: §3 says DEFER, §4-§7 still operationalize Phase 5. Add feature flag `PHASE_5_ENABLED=false` (default off). Phase 5 may NOT execute without explicit Kim-approval prod_locked_decisions row + script-level guard. | §3 Rule 1 verdict block now declares an explicit `PHASE_5_ENABLED` feature flag (default `false`) at three layers: (a) operational doctrine, (b) migration-script-level guard `assert os.environ.get('PHASE_5_ENABLED') == 'true' and KIM_APPROVAL_LD_PRESENT()`, (c) §6 Gate row dedicated to flipping the flag. Phases 4 and 5 in §5 are clearly tagged "blocked unless flag is true". §7 risk row added. | §3 Rule 1, §4 table, §5 Phase 5, §6 Gate, §7 |
| 2 | HIGH | Path discipline: add dual-path resolution policy. Canonical roots: {Dropbox, Projects}. Preflight resolves the canonical path set before analysis/execution. | §3 NEW subsection "Path discipline (v2 dual-canonical)" inserted before Rule 1, naming the two canonical roots and the preflight resolution requirement. §5 Phase 0 explicitly performs canonical-root resolution as Step 0. §11 reference index points to LD #584 v2 amendment + DS-27 v2 + HANDOFF_TEMPLATE_v2 v2. | §3 (new subsection), §5 Phase 0, §11 |
| 3 | MED | Rollback completeness: Phase 0 must produce snapshot with explicit fields {row_count, id_uniqueness, all_touched_ids_present}; pre-Phase-5 integrity check verifies snapshot completeness. | §4 Phase 0 expanded: snapshot now produces explicit fields (row_count + id_uniqueness assertion + all_touched_ids_present assertion) into a single JSONL artifact. §6 (Gate 7) extended with a "snapshot integrity check" assertion that runs BEFORE Phase 5 and fails the phase if any of the three fields is missing. §8 rollback narrative tied to the snapshot's three fields. | §4 Phase 0, §6 Gate 7, §8 |
| 4 | MED | Cost model split: §9 separate "machine time" vs "human review time"; keep 10-hour figure as planning baseline (machine + human combined). | §9 split into "Machine time" (script execution wall-clock per phase) + "Human review time" (Kim's attention, dry-run review, per-phase first-5 review, final audit) + "Total planning baseline (combined)" = 10 hours. Each line cites its own assumption set. | §9 |

**v1 vs v2 surface area:** v2 adds ~250 lines (new path discipline subsection, expanded Phase 0 snapshot schema, Gate 7 expansion, cost split). All v1 content preserved (no deletions); v2 additions are clearly labeled `(v2)` or `(NEW v2)` inline.

---

## §1 — Goal (preserved verbatim from v1)

Bring the `prod_locked_decisions` collection's `severity`, `task_category`, and `scope_domain` columns into a **canonical, lossless, audit-trailed state** so:

1. Every active row uses an enum value that appears in the live Directus schema definition.
2. Lossy maps (e.g. `HIGH → HARD`) are explicitly approved by Kim before the row is rewritten.
3. Every PATCH carries a `migration_audit` row in `prod_activity_log` with the old/new value pair, so a rollback (or a "did Claude really do that?" forensic trace) is one query away.
4. Row count after migration matches row count before migration (no lost rows; no auto-creation).
5. The Part 1 vocab-tolerant filter remains correct AFTER migration (i.e. queries that accepted HIGH today and HARD tomorrow continue to return the same answer).

Non-goals:

- This spec does NOT propose canonicalizing `enforcement_type` (already 100% canonical per the audit).
- This spec does NOT propose a status=superseded sweep of the ~30 RESOLVED_BUT_NOT_CLOSED rows. That is a separate Kim-gated triage session per §1.5 of the cleanup report.
- This spec does NOT propose schema-enum changes to Directus. Adding `app_architecture`, `infrastructure`, etc. to the canonical task_category list is a SEPARATE Directus schema change Kim must perform via the admin UI; this spec proposes the values, but Kim wields the schema editor.

---

## §2 — Background (preserved verbatim from v1)

The cleanup report (`SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`) established:

- **529 active LDs**, mixed-vocabulary.
- **76.7% of HIGH/CRITICAL active rows are TRULY_OPEN with stale severity vocabulary**, not stale work.
- The 2026-05-04 silent schema migration changed canonical severity from `{LOW, MEDIUM, HIGH, CRITICAL}` to `{HARD, SOFT}`. Old values still POST successfully (Directus does NOT reject them), so 303 active rows still use the old vocabulary.
- The 30-LD severity sample showed that 23/30 are TRULY_OPEN, 3/30 RESOLVED_BUT_NOT_CLOSED, 1/30 STALE, 3/30 AMBIGUOUS.
- task_category has 68 distinct values vs canonical 11; 5 distinct actions emerged from the audit (REMAP / KEEP_LIVE / SPLIT / consolidate / extend canonical).
- scope_domain has 17 distinct values vs canonical 5; all 29 non-canonical rows are mechanically remappable.

**Part 1 (LD #586) shipped a defensive read-side fix** so vocab-tolerant queries return correct results today regardless of mixed vocabulary. The migration in this spec is OPTIONAL CANONICALIZATION for clarity + future-proofing — the system already works with mixed vocab thanks to Part 1.

The decision to migrate is therefore a **clarity / hygiene investment**, not a correctness bug fix.

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments

Each rule is debated as an Advocate vs Counter pair. Resolution criteria are explicit and tied to evidence in the cleanup report.

### §3.0 — Path discipline (v2 dual-canonical, NEW)

This subsection codifies Cursor's HIGH-severity Amendment #2.

**Mandate (v2):** every command, script, doc reference, and migration-side artifact in this spec MUST resolve filesystem paths against ONE of two canonical roots before any analysis or execution:

1. **Primary — Mindfulnest project (Dropbox-anchored):** `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/`
2. **Secondary — Tooling and app repos (Projects-anchored):** `/Users/kimberlysmith/Projects/`

**Operational consequences for this migration:**

- The migration script `Production/scripts/migrate_schema_vocab_v1.py` MUST be authored at the Dropbox-anchored canonical path (it operates on Dropbox-housed Directus tooling artifacts).
- All script-internal path references (snapshot output path, dry-run report path, lockfile path) MUST resolve to absolute Dropbox-anchored paths (the lockfile lives in `~/.claude/mindfulnest-cache/` per §9, which is global-config-allowed and does NOT count as outside-canonical).
- Tooling-repo work referenced by this spec (none in v2; reserved for future v3) would resolve to `/Users/kimberlysmith/Projects/...` and would be explicitly named.
- `.claude/worktrees/` is FORBIDDEN under either canonical root unless the handoff explicitly authorizes a named worktree path.
- Outside-canonical paths (e.g., `~/Desktop/`, `/tmp/`, external mounts) are FORBIDDEN for migration writes; allowed only for global Claude config.

**Preflight resolution (v2 NEW):** Phase 0 (see §5) now performs path-discipline resolution as Step 0 BEFORE the dry-run snapshot:

```python
# Phase 0 Step 0 (v2 NEW) — canonical-root resolution
CANONICAL_ROOTS = {
    'dropbox': '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/',
    'projects': '/Users/kimberlysmith/Projects/',
}
EXPECTED_ROOT = CANONICAL_ROOTS['dropbox']  # this migration is Dropbox-housed
SCRIPT_PATH = Path(__file__).resolve()
assert str(SCRIPT_PATH).startswith(EXPECTED_ROOT), \
    f"Migration script not anchored to expected canonical root. Got: {SCRIPT_PATH}, expected prefix: {EXPECTED_ROOT}"
# Worktree-presence check
assert '.claude/worktrees/' not in str(SCRIPT_PATH), \
    f"Migration script running from a worktree shadow. Refusing. Path: {SCRIPT_PATH}"
```

**Cross-references:**
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority.
- `.claude/skills/zero-error-qa/SKILL.md` DS-27 (refactored 2026-05-08 v2 dual-canonical) — agent-side enforcement.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical) — handoff-side enforcement.

### §3.1 — Rule 1 — severity HIGH/CRITICAL → HARD migration (v1 debate preserved + v2 feature-flag resolution)

**Advocate:** "Migrate all 303 active HIGH/CRITICAL rows to HARD. The schema enum is HARD/SOFT; carrying 303 rows of legacy vocab indefinitely is a cognitive tax. New writes already use HARD (45 rows). Old writes get retroactively normalized so future queries, dashboards, and analytics see one consistent vocabulary. Lossy on CRITICAL/HIGH distinction (we collapse 4 ranks into 2), but the audit shows that distinction is largely cosmetic — every CRITICAL sample classified as TRULY_OPEN and every HIGH sample classified as TRULY_OPEN both function as 'standing rule, must comply'. Two ranks (HARD/SOFT) is sufficient."

**Counter:** "Don't migrate. The 303 are not stale work — they're stale labels. Vocab-tolerant filters (Part 1, LD #586) handle queries; the system reads HIGH and HARD as equivalent at rank 3 already. Mass migration adds risk for zero functional benefit:
- Every PATCH is an opportunity for typo, network glitch, partial-batch, or unexpected schema validation rejection.
- The HIGH/CRITICAL distinction MAY carry information we'd lose forever (CRITICAL was reserved for hard-prohibition rules like `phase_b_sensation_language_only`; HIGH covered standing-rule-with-rationale).
- A 303-row migration takes ~2-3 hours of Kim's attention even with a script — that's 2-3 hours not spent shipping V59 or storyboard work.
- The cleanup report itself says (§5.1): 'Recommend Pass 1 (case-fold) + Pass 5 (scope_domain singletons) first — both are TRIVIAL/LOW risk and quick wins.' Severity is NOT in that list."

**Resolution criteria:**
- Does any tool require canonical-only severity values? Per Part 1 verification, NO — query consumers all import severity_vocab now and filter via the rank dict, which knows both vocabularies.
- Does any human-facing dashboard depend on "severity == HARD" string match? Per the audit, NO — dashboards filter via Directus aggregations which group on whatever value is in the column.
- Is the CRITICAL→HARD collapse actually lossy? Per the 30-row sample, NO — every CRITICAL row is functionally a HARD row; the rank distinction is not used in any current code path (only the rank threshold is, and HARD and CRITICAL both pass it).

**Verdict (v1 preserved):** **DEFER, lean Counter.** The Counter case wins on cost-vs-benefit: Part 1 already solved the correctness problem; the migration only buys aesthetic consistency. If Kim wants to migrate anyway for clarity, the Advocate position has a clean execution plan in §5; treat that as an OPTIONAL future polish session, not a blocker.

#### Rule 1 v2 amendment — `PHASE_5_ENABLED` feature flag (Cursor Amendment #1, HIGH)

Cursor's review observed that v1's verdict says DEFER but §4-§7 still operationalize Phase 5 as if it were merely awaiting Kim's gate-row approval. Cursor concluded this leaves a path open for Phase 5 to execute by accident if Kim's verbal "ok, run it" fires before Kim has authored the prod_locked_decisions row that Gate 1 requires. v2 closes this path with an explicit feature flag at THREE layers:

**Layer 1 — Operational doctrine:**

> Phase 5 (severity HIGH/CRITICAL → HARD migration, 320 rows, lossy) is BLOCKED by default. The block is encoded as a feature flag named `PHASE_5_ENABLED` whose default value is `false`. Phase 5 may NOT execute without ALL of the following being true simultaneously: (a) feature flag explicitly set to `true` in the migration session's environment, (b) an active prod_locked_decisions row with decision_key `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` and Kim's approval timestamp in `notes`, (c) the script-level guard (Layer 2) passes its assertion. ANY of these failing means Phase 5 refuses to run.

**Layer 2 — Migration-script guard (executable):**

```python
# Phase 5 entry guard (v2 NEW)
import os
PHASE_5_ENABLED = os.environ.get('PHASE_5_ENABLED', 'false').lower() == 'true'
if not PHASE_5_ENABLED:
    print('Phase 5 blocked: PHASE_5_ENABLED feature flag is false. Set environment variable to "true" before retry.')
    sys.exit(1)
# Independent verification of Kim-approval LD row
auth_rows = client.get_items(
    'prod_locked_decisions',
    filters={'decision_key': {'_eq': 'SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1'}, 'status': {'_eq': 'active'}},
    fields=['id', 'decision_key', 'date_locked', 'notes', 'status'],
    limit=1,
)
assert auth_rows, 'Phase 5 blocked: no active SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1 row found'
auth_notes = (auth_rows[0].get('notes') or '').lower()
assert 'kim approved' in auth_notes or 'authorized by kim' in auth_notes, \
    f"Phase 5 blocked: authorization LD {auth_rows[0]['id']} present but 'kim approved' not in notes. Authorization is incomplete."
print(f'Phase 5 authorized via PHASE_5_ENABLED=true + LD {auth_rows[0]["id"]} (date_locked={auth_rows[0]["date_locked"]})')
```

**Layer 3 — §6 Gate row (procedural):**

A new gate row in §6 ("Phase 5 feature flag flip") explicitly requires Kim to:
1. Author the prod_locked_decisions row `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` with `notes` containing the literal string "Kim approved" + a timestamp.
2. Set `PHASE_5_ENABLED=true` in the migration session's environment immediately before script invocation.
3. Confirm both prerequisites in chat before issuing the run command.

If Kim chooses Counter (DEFER, never migrate severity), the flag stays `false` permanently. The flag is the operational expression of the v1 verdict; v2 makes the verdict mechanical rather than narrative.

If migration IS authorized, the mapping is:
- `CRITICAL` → `HARD` (129 rows)
- `critical` → `HARD` (2 rows)
- `HIGH` → `HARD` (174 rows)
- `high` → `HARD` (15 rows)

Total: 320 rows touched.

### §3.2 — Rule 2 — lowercase severity variants (preserved verbatim from v1)

**Advocate:** "Migrate the 35 lowercase variants (`high`, `medium`, `low`, `critical`, `MED`) to canonical UPPERCASE in their own tier. Reduces ambiguity. Pure case-fold; no semantic change. ZERO information loss. Cheap (35 rows), low risk (mechanical), high readability win."

**Counter:** "Vocab-tolerant filter handles them. Same cost-vs-benefit argument as Rule 1: Part 1 solved correctness; this is aesthetic only. The 35 rows took zero queries to identify; they cost Kim nothing today. Why touch them?"

**Resolution criteria:**
- Cost: 35 PATCHes is minutes of script time; risk is negligible (case-fold only).
- Benefit: removes 5 distinct label variants from the data, dropping the distinct-severity-value count from 11 → 6 (HARD, SOFT, HIGH, CRITICAL, MEDIUM, LOW).
- Risk of breaking anything: near-zero. No code path depends on the lowercase form being present.

**Verdict:** **EXECUTE if Kim authorizes the session.** This is the cheapest, lowest-risk migration; if a migration session runs at all, this one belongs in it. Mapping:
- `high` → `HIGH` (15 rows)
- `medium` → `MEDIUM` (15 rows)
- `low` → `LOW` (3 rows)
- `critical` → `CRITICAL` (2 rows)
- `MED` → `MEDIUM` (2 rows)

Total: 37 rows touched (the 35-figure in the report excluded the 2 `MED` abbreviation rows; including them gives 37).

If Rule 1 also migrates, the lowercase variants flow through Rule 1's mapping after case-fold (so `critical` → `CRITICAL` → `HARD` net result is `HARD`). Avoid double-PATCHing the same row by combining Rule 1 + Rule 2 into a single per-row decision tree (see §5).

### §3.3 — Rule 3 — task_category remap / extend / split (preserved verbatim from v1)

The audit identified 5 distinct actions per non-canonical task_category value. Walking each:

| Value | Count | Proposed action | Debate |
|---|---|---|---|
| `architectural` | 30 | **REMAP → app_architecture** | Advocate: pure synonym consolidation (`architectural` and `app_architecture` mean the same thing; two near-synonym buckets is the failure mode the audit was designed to detect). Counter: 30 rows, low risk, but the synonym-merge depends on Rule 3a (extend canonical to include `app_architecture`) — if that schema change isn't approved, REMAP target doesn't exist. **Verdict: EXECUTE only if Rule 3a is approved.** |
| `app_architecture` | 59 | **KEEP_LIVE; Kim extends canonical enum** | Advocate: this is a meaningful production bucket (state-shape decisions for v59 client) that doesn't fit any existing canonical value; canonical `tech_stack` is too coarse. Counter: 59 rows is a lot of vocabulary inertia; if we keep `app_architecture` we're admitting the canonical 11-value enum was insufficient. **Verdict: EXECUTE Kim's enum extension; no row PATCHes needed.** Rule 3a is "extend canonical task_category enum to include `app_architecture`". |
| `infrastructure` | 32 | **KEEP_LIVE; Kim extends canonical enum** | Advocate: every sample is a real infrastructure decision (Cloudflare R2, asset findability, tooling repo) that doesn't fit `tech_stack`. Counter: name-collision risk with `scope_domain.infra` which has the SAME role at the scope level — confusing to have both. **Verdict: EXECUTE Kim's extension as `infrastructure`** (NOT `infra` — keep the names distinct from scope_domain to prevent confusion). |
| `production_infrastructure` | 35 | **SPLIT** — drain protocol → `infrastructure`, Cluster A widgets → new `production_tool_ui` | Advocate: heterogeneous bucket; splitting makes downstream queries possible. Counter: SPLIT requires per-row review (which sample is drain vs widget?); higher risk than mechanical REMAP. **Verdict: EXECUTE per-row, with Kim approving each split decision; or DEFER until a separate triage session.** Rule 3b is "extend canonical to include `production_tool_ui`". |
| `storyboard` | 30 | **NO ACTION** — already canonical | Advocate: confirmed. Counter: confirmed. **Verdict: skip.** |
| `security` | 26 | **KEEP_LIVE; Kim extends canonical** | Advocate: security decisions deserve their own bucket. Counter: agreed; trivially safe. **Verdict: EXECUTE Kim's extension as `security`.** |
| `production_pipeline` | 26 | **INVESTIGATE_INDIVIDUALLY** | Overlap with `production_infrastructure`. Defer to per-row triage. |
| `governance` | 12 | **KEEP_LIVE; extend canonical** | **Verdict: EXECUTE Kim's extension as `governance`.** |
| `visual_production` | 12 | **INVESTIGATE** — possible merge with `video` | Defer. |
| `audio_production` | (count TBD) | **REMAP → audio** | Pure synonym. Cheap. |
| `video_production` | (count TBD) | **REMAP → video** | Pure synonym. Cheap. |
| `production_server_infrastructure` | 15 | **REMAP → infrastructure** (if Rule 3a approved) | Synonym. |
| `production_server` | (count TBD) | **REMAP → infrastructure** | Synonym. |
| `production_tool_ui` | (count TBD) | **KEEP_LIVE; extend canonical** | Per Rule 3b. |
| `data_model` | 5 | **KEEP_LIVE; extend canonical** | Cheap, meaningful. |
| `tools` | 6 | **INVESTIGATE** — overlap with `production_tool_ui` | Defer. |
| `feature` | (count TBD) | **INVESTIGATE_INDIVIDUALLY** | Too generic. |

**Aggregate task_category debate:** should we extend canonical (more values) or remap aggressively (fewer values)?

- **Advocate (extend):** the data is telling us the canonical 11 was insufficient. 7 new values (`app_architecture`, `infrastructure`, `security`, `governance`, `production_tool_ui`, `data_model`, `visual_production`) are all genuinely meaningful buckets used by 5+ rows each. Extending canonical → 18 captures real semantics; aggressively remapping into 11 loses information.
- **Counter (remap):** more enum values is more cognitive load on every future LD authoring decision. The canonical 11 was a deliberate design choice; padding it with 7 more values dilutes the discipline. Force-fit into the 11 even if the fit is awkward.

**Resolution criteria:**
- Are the 7 proposed additions semantically distinct from existing canonical values? Per the audit samples, YES (no obvious force-fit into the existing 11).
- Is enum proliferation a real problem? Per Kim's prior pattern, NO — Kim adds enum values when justified by row count and semantic distinctness.
- Does extending the enum break anything in code? NO — task_category is read as a string in all consumers; no enum-specific code paths.

**Verdict:** **EXTEND canonical to 18 values, then REMAP synonyms.** This is the cleanest of the three options (extend-only, remap-only, extend+remap-synonyms) because it preserves semantic information AND consolidates near-duplicates. Net: ~110 rows touched (30 architectural + 80 ish synonym remaps); 7 schema-enum additions Kim performs in the Directus admin UI.

### §3.4 — Rule 4 — scope_domain remap (preserved verbatim from v1)

The audit found all 29 non-canonical scope_domain rows are mechanically remappable; canonical 5 (`content, production, app-dev, infra, cross-cutting`) stays as-is.

**Advocate:** "Run the remap. 12 `app` → `app-dev`, 6 `infrastructure` → `infra`, 11 singletons → `production` or `cross-cutting`. All mechanical, all safe, all low-volume. The cleanup report's §5.1 explicitly recommends this as a quick win."

**Counter:** "These 29 rows have been working for months without anyone noticing. Why touch them?"

**Resolution criteria:**
- Cost: 29 PATCHes is a few minutes of script time.
- Benefit: scope_domain queries become reliable (no mixed-vocabulary rank-by-domain skew).
- Risk: near-zero. Mechanical remap with read-back-after-write per Rule 35.

**Verdict:** **EXECUTE if Kim authorizes the session.** Lowest-risk migration of the four; effectively a free cleanup. Mapping (verbatim from cleanup report §1.3):

| Old | New | Count |
|---|---|---|
| `app` | `app-dev` | 12 |
| `infrastructure` | `infra` | 6 |
| `stillgen` | `production` | 2 |
| `governance` | `cross-cutting` | 2 |
| `video_pipeline` | `production` | 1 |
| `audio_pipeline` | `production` | 1 |
| `image_pipeline` | `production` | 1 |
| `ci_pipeline` | `infra` | 1 |
| `claude_session_behavior` | `cross-cutting` | 1 |
| `payments` (id=300) | `app-dev` | 1 |
| `beat_generator` | `production` | 1 |

Total: 29 rows.

(`content` row at id=539 already uses canonical `content`; no action.)

---

## §4 — Per-rule action table (preserved + v2 Phase 5 flag column)

Consolidating the four rules into a single execution-ready table:

| Rule | Action | Volume | Risk | Depends-on | v2 flag |
|---|---|---|---|---|---|
| 1 | severity HIGH/CRITICAL → HARD | 320 rows | LOW (mechanical) | Kim approves Counter-or-Advocate verdict | `PHASE_5_ENABLED=false` by default; flip required |
| 2 | severity lowercase → UPPERCASE | 37 rows | TRIVIAL (case-fold) | none | none |
| 3a | task_category enum extension (7 new values) | 0 rows | LOW (Kim performs in admin UI) | Kim approves the 7 names | none |
| 3b | task_category synonym remaps | ~110 rows | LOW (mechanical) | Rule 3a (extension) lands first | none |
| 4 | scope_domain remaps | 29 rows | LOW (mechanical) | none | none |

**Total row touches (max scope):** 320 + 37 + 110 + 29 = ~496 PATCHes.

**Schema enum changes (Kim's hands):** 7 task_category additions in the Directus admin UI before Rule 3b begins.

If Kim chooses the Counter verdict on Rule 1, the total drops to ~176 PATCHes (37 + 110 + 29) AND `PHASE_5_ENABLED` stays `false` permanently (Phase 5 blocked).

### §4 Phase 0 v2 expanded snapshot schema (Cursor Amendment #3, MED)

Cursor's MED-severity Amendment #3 noted that v1's Phase 0 dry-run produces a JSON dry-run report but does NOT produce an explicit ROLLBACK snapshot with the three required fields. v2 makes this explicit.

**Phase 0 v2 snapshot artifact:** `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl`

The snapshot file is line-delimited JSON; each line is a complete row from `prod_locked_decisions` for every id that ANY phase plans to touch (union of Phase 1+2+3+4+5 target sets). Each line MUST contain ALL columns currently in the row (not just severity/task_category/scope_domain) so a full row-restore is possible.

**Required snapshot-level metadata (v2 NEW):** the snapshot file is accompanied by a `*.metadata.json` sidecar with the three required fields:

```json
{
  "snapshot_version": "v2",
  "snapshot_taken_at": "2026-05-08T11:30:00-07:00",
  "row_count": <integer total rows in snapshot>,
  "id_uniqueness": {
    "unique_id_count": <integer>,
    "duplicates_detected": [<list of duplicate ids if any>],
    "passes": <boolean: unique_id_count == row_count AND duplicates_detected is empty>
  },
  "all_touched_ids_present": {
    "expected_ids": [<sorted list of all ids any phase plans to touch>],
    "snapshot_ids": [<sorted list of ids actually in snapshot file>],
    "missing_ids": [<set difference: expected - snapshot>],
    "extra_ids": [<set difference: snapshot - expected>],
    "passes": <boolean: missing_ids empty AND extra_ids empty>
  },
  "snapshot_path_canonical_root": "dropbox",
  "phases_planned": ["phase_0", "phase_1", "phase_2", "phase_3", "phase_4", "phase_5"],
  "phase_5_blocked_by_flag": <boolean: PHASE_5_ENABLED resolution>
}
```

**Pre-Phase-5 integrity check (v2 NEW):** before Phase 5 executes, the migration script reads the metadata sidecar and asserts:

```python
# Phase 5 pre-flight integrity check (v2 NEW)
metadata_path = SNAPSHOT_DIR / f'{snapshot_basename}.metadata.json'
assert metadata_path.exists(), f"Phase 5 blocked: snapshot metadata missing at {metadata_path}"
metadata = json.loads(metadata_path.read_text())
assert metadata['row_count'] > 0, "Phase 5 blocked: snapshot empty"
assert metadata['id_uniqueness']['passes'] is True, \
    f"Phase 5 blocked: snapshot id_uniqueness failed. Duplicates: {metadata['id_uniqueness']['duplicates_detected']}"
assert metadata['all_touched_ids_present']['passes'] is True, \
    f"Phase 5 blocked: snapshot incomplete. Missing: {metadata['all_touched_ids_present']['missing_ids']}, Extra: {metadata['all_touched_ids_present']['extra_ids']}"
print(f'Phase 5 snapshot integrity check passed: {metadata["row_count"]} rows, all touched ids present.')
```

If any assertion fails, Phase 5 refuses to run AND the script logs a `PHASE_5_BLOCKED_BY_INTEGRITY_CHECK` row to `prod_activity_log` with the failure detail.

---

## §5 — Migration sequence (preserved + v2 Phase 0 Step 0 + Phase 5 flag guard)

A migration script `Production/scripts/migrate_schema_vocab_v1.py` performs the work in 6 phases. Each phase is independently approvable + skippable.

**Note (v2):** Although the script is named `_v1.py` (since it is the first migration script of its kind), this tech spec is v2. The naming reflects script evolution, not spec evolution.

### Phase 0 — Non-mutating dry run + canonical-root resolution + snapshot (v2 expanded)

**Step 0 (v2 NEW) — Canonical-root resolution per §3.0.** Confirm the script is running from the Dropbox-anchored canonical root and NOT from a worktree shadow. See §3.0 for the assertion code.

**Step 1 — Snapshot (v2 expanded per §4 schema).** For every row id any phase plans to touch (union of Phase 1+2+3+4+5 target sets), pull the full row body into `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl`. Compute and write the metadata sidecar with `row_count`, `id_uniqueness`, and `all_touched_ids_present` per §4 Phase 0 schema.

**Step 2 — Dry-run report.** For each rule's mapping, pull current row counts for each old/new value pair from Directus. Emit a JSON dry-run report with: `rows_to_touch`, `current_values`, `target_values`, `expected_after_counts`. Write the report to `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_<YYYYMMDD>.md`. NO PATCHes performed.

**Step 3 — Activity log marker.** POST a `prod_activity_log` row with action `SCHEMA_VOCAB_MIGRATION_PHASE_0_COMPLETE` containing the snapshot file path + dry-run report path + metadata sidecar checksum.

**Gate:** Kim reviews the dry-run report AND the snapshot metadata sidecar AND emits a "Phase 0 approved" Directus row in `prod_activity_log` (decision_key `SCHEMA_VOCAB_MIGRATION_PHASE_0_APPROVED_V1`). Without this row, Phase 1 refuses to run.

### Phase 1 — Rule 4 (scope_domain remap, 29 rows)

Lowest-risk migration runs first. Per-row PATCH with read-back per Rule 35:

```python
for row in rows:
    old = row['scope_domain']
    new = MAPPING[old]
    if old == new:
        continue
    pre = client.get_items('prod_locked_decisions', filters={'id': {'_eq': row['id']}}, fields=['id', 'scope_domain'])
    client.patch_item('prod_locked_decisions', row['id'], {'scope_domain': new})
    post = client.get_items('prod_locked_decisions', filters={'id': {'_eq': row['id']}}, fields=['id', 'scope_domain'])
    assert post[0]['scope_domain'] == new, f"PATCH not honored: id={row['id']} expected={new} got={post[0]['scope_domain']}"
    client.post_item('prod_activity_log', {
        'action': f"scope_domain migrated: id={row['id']} {old} -> {new}",
        'details': json.dumps({'rule': 4, 'ld_id': row['id'], 'field': 'scope_domain', 'old': old, 'new': new}),
        'performed_by': 'migrate_schema_vocab_v1.py phase=1',
    })
```

**Per-row approval:** dry-run-then-apply on the FIRST 5 rows; Kim emits a "Phase 1 first-5 approved" row before the remaining 24.

### Phase 2 — Rule 2 (severity lowercase → UPPER, 37 rows)

Same per-row pattern. Mapping table:
- `high` → `HIGH`
- `medium` → `MEDIUM`
- `low` → `LOW`
- `critical` → `CRITICAL`
- `MED` → `MEDIUM`

If Rule 1 is also approved, Phase 2 PATCHes can target the post-Rule-1 value directly (e.g. `critical` → `HARD` rather than `critical` → `CRITICAL` → `HARD` two-step) to avoid double-PATCHing.

### Phase 3 — Rule 3a (Kim extends canonical task_category enum, 0 rows)

**Kim's hand on the trigger.** Claude does NOT perform this step. Kim opens Directus admin UI → Settings → Data Model → prod_locked_decisions → task_category field → adds 7 values:
- `app_architecture`
- `infrastructure`
- `security`
- `governance`
- `production_tool_ui`
- `data_model`
- `visual_production`

Kim emits a "Phase 3 schema extended" row in `prod_activity_log` with the new enum value list verbatim.

### Phase 4 — Rule 3b (task_category synonym remap, ~110 rows)

Mapping table (conditional on Phase 3):
- `architectural` → `app_architecture`
- `audio_production` → `audio`
- `video_production` → `video`
- `production_server_infrastructure` → `infrastructure`
- `production_server` → `infrastructure`

Plus per-row triage for the AMBIGUOUS values (`production_pipeline`, `visual_production`, `tools`, `feature`) — script emits the row's decision_text + decision_name and asks Kim per-row.

### Phase 5 — Rule 1 (severity HIGH/CRITICAL → HARD, 320 rows) — BLOCKED BY `PHASE_5_ENABLED` FEATURE FLAG (v2)

**v2 entry guard (§3.1 Layer 2):** before any PATCH, the script asserts `PHASE_5_ENABLED=true` AND active LD `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` row exists with "Kim approved" in `notes` AND Phase 0 snapshot integrity check passes (§4 Phase 0 v2). Failing any assertion results in `sys.exit(1)` and a `PHASE_5_BLOCKED_*` activity-log row.

Per the §3 verdict (preserved from v1), this phase runs ONLY if Kim explicitly approves the lossy collapse via the three-layer feature-flag gate. Mapping:
- `CRITICAL` → `HARD` (129)
- `HIGH` → `HARD` (174)
- `critical` → `HARD` (2; or `HIGH` if Phase 2 already ran)
- `high` → `HARD` (15; or `HIGH` if Phase 2 already ran)

Per-row PATCH with the same per-row activity-log audit trail.

### Phase 6 — Final audit

After all approved phases run:

1. Re-pull severity / task_category / scope_domain distinct-value counts; emit a comparison report against the Phase 0 baseline.
2. Run `governance_drift_check.py --min-severity HARD --dry-run` and confirm row counts are stable (HARD-tier should equal pre-migration HARD-tier + post-Rule-1 migrated HIGH/CRITICAL).
3. Run `failure_mode_matrix.py --severity HARD` and confirm row count match.
4. Generate `Production/docs/SCHEMA_VOCAB_MIGRATION_REPORT_<YYYYMMDD>.md` with verbatim before/after counts + activity-log row IDs spanned.
5. POST a `SCHEMA_VOCAB_MIGRATION_V1_COMPLETE` standing-rule LD documenting the new-state baseline.

---

## §6 — Pre-implementation gates Kim must approve (v1 preserved + v2 Gate 9 added)

Before any migration phase runs, Kim must explicitly answer:

| # | Gate | Kim's decision required |
|---|---|---|
| 1 | Rule 1 verdict: migrate severity HIGH/CRITICAL → HARD (320 rows, lossy) OR DEFER per the Counter case? | DEFER / EXECUTE |
| 2 | Rule 3a: approve the 7 task_category additions verbatim? | ENUMS APPROVED / AMEND / DEFER |
| 3 | Rule 3b ambiguous values (`production_pipeline`, `visual_production`, `tools`, `feature`): triage per-row, OR collapse them into existing canonical? | TRIAGE / COLLAPSE |
| 4 | RESOLVED_BUT_NOT_CLOSED rows (~30 estimated): close them now (status=superseded), keep as standing-reference HARD, or defer? | CLOSE / KEEP / DEFER |
| 5 | Phase 5 first-5 dry-run: approve before the remaining 315 PATCHes? | YES / NO (per phase) |
| 6 | Migration script authoring: should Claude write `migrate_schema_vocab_v1.py` first and have Cursor cross-review BEFORE any Directus PATCH runs? | YES (recommended) / NO |
| 7 | **(v2 EXPANDED)** Backup: should the migration script snapshot every touched row's full body to `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl` before any PATCH AND produce the metadata sidecar with `row_count` + `id_uniqueness` + `all_touched_ids_present` fields per §4 Phase 0 v2 schema? | YES (REQUIRED for Phase 5) / NO (only valid if Phase 5 stays DEFERRED) |
| 8 | Activity-log volume: ~500 activity-log rows in one session is high-volume; should the audit-trail entries be batched (one row per phase) or per-row? | PER-ROW (recommended for forensic) / BATCHED |
| 9 | **(v2 NEW — Cursor Amendment #1)** Phase 5 feature flag flip: BEFORE Phase 5 may execute, Kim must (a) author prod_locked_decisions row `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` with "Kim approved" + timestamp in `notes`, AND (b) set `PHASE_5_ENABLED=true` in the migration session's environment. Confirm both. | LD AUTHORED + FLAG SET / DEFER (Phase 5 stays blocked) |

**Gate 9 verification artifact:** the script's Phase 5 entry guard (§3.1 Layer 2) prints the resolved auth_row id + date_locked at startup; that line is captured in the final audit report (§5 Phase 6) as proof Gate 9 was satisfied.

---

## §7 — Risk assessment (v1 preserved + v2 risk row #9)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Per-row PATCH partial-batch failure (network, rate limit, schema validation) | MEDIUM | HIGH | Read-back-after-write per Rule 35; on failure, halt-and-report; resume from last-confirmed row |
| Lossy collapse (Rule 1) loses CRITICAL/HIGH distinction permanently | HIGH if executed | LOW (per audit, distinction is largely cosmetic) | Snapshot every touched row's pre-migration body; rollback path is restoring from snapshot |
| Mass migration triggers `weekly_preflight_audit.py` drift detection (governance_drift_check, etc.) flagging the migration itself as drift | MEDIUM | LOW | Run migration during a quiet window; weekly_preflight_audit doesn't fire on row updates, only on auth-failure-style probes — safe |
| LD #586 (vocab-tolerant filter) becomes redundant after migration | HIGH | TRIVIAL | LD #586's helpers continue to work post-migration (they accept canonical values too); no code changes needed |
| Kim approves Phase 0 then partial phases run, leaving the dataset in a half-migrated state mixing pre/post values | LOW | LOW | Each phase is idempotent (re-runnable); half-migrated state is not worse than pre-migration state |
| Schema enum extension (Phase 3) creates false sense that ALL future LDs use the new values, but old LDs persist | HIGH | LOW | Standing-rule LD post-migration declares "post-2026-XX-XX, all new LDs MUST use canonical-extended-enum"; existing rows remain unchanged unless touched by Phase 4 |
| Activity-log volume (~500 rows) triggers UI sluggishness in dashboard | LOW | LOW | Batched activity-log mode (Gate #8 BATCHED option) reduces to ~5 rows |
| Cursor reviews this spec and finds material gaps Claude missed | MEDIUM (this is a NEW spec) | MEDIUM | Spec is DESIGN ONLY; Cursor review is companion deliverable; AMEND v2 if Cursor returns blockers |
| **(v2 NEW)** Phase 5 executes without Gate 9 satisfied (feature flag bypass, missing LD row, snapshot integrity not verified) | LOW (three layers must all fail) | HIGH | Three-layer feature-flag guard per §3.1 (operational + script-level + procedural); script refuses to run on any of the 3 failures; activity-log row `PHASE_5_BLOCKED_*` captures the failure mode for forensic |

---

## §8 — Rollback per phase (v1 preserved + v2 Phase 5 snapshot field tie)

Each phase has an independent rollback path:

- **Phase 0 (dry-run + snapshot):** no rollback needed (no mutations).
- **Phase 1 (scope_domain):** for every activity-log row matching `rule=4`, PATCH the row's scope_domain back to the `old` value.
- **Phase 2 (severity case-fold):** symmetric — PATCH each row back to lowercase from the audit-log.
- **Phase 3 (Kim's enum extension):** Kim removes the 7 added enum values via Directus admin UI. Existing rows that USE those values (post-Phase-4) become technically out-of-enum (but Directus still accepts them on read; new writes would reject). **Phase 4 should NOT run unless Phase 3 is permanent.**
- **Phase 4 (task_category remap):** for every activity-log row matching `rule=3b`, PATCH back.
- **Phase 5 (severity HARD migration):** for every activity-log row matching `rule=1`, PATCH back to the snapshot-recorded `old` value. **This is the most consequential rollback** because Phase 5 is the lossy phase; the snapshot must capture the original CRITICAL vs HIGH distinction.

### §8 v2 — Phase 5 rollback tied to snapshot integrity (Cursor Amendment #3)

Phase 5 rollback requires the Phase 0 v2 snapshot file (`SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl`) and its metadata sidecar to exist AND have all three integrity fields passing. Rollback procedure:

1. Read the snapshot metadata sidecar; assert `id_uniqueness.passes` AND `all_touched_ids_present.passes` are both `true`. If either is false, rollback CANNOT proceed because the snapshot is incomplete; surface to Kim for manual triage.
2. For every activity-log row matching `rule=1` AND `phase=5`, look up the pre-migration row body in the snapshot file (keyed by id).
3. PATCH the live row's `severity` field back to the snapshot value.
4. Read-back per Rule 35; assert post == snapshot value.
5. POST a `PHASE_5_ROLLBACK_ROW` activity-log entry with id + reverted value.

If the snapshot is missing or incomplete, rollback is BLOCKED at the same level Phase 5 itself is blocked. The §3.1 Layer 2 script-level guard's snapshot integrity check (§4 Phase 0 v2) is the SAME assertion the rollback uses; if Phase 5 was allowed to run, the snapshot's three fields were all `true`, so rollback is guaranteed feasible for the rows Phase 5 touched.

---

## §9 — Operational notes (v2 split: machine time vs human review time)

This section addresses Cursor's MED-severity Amendment #4. The v1 narrative mixed wall-clock and Kim-attention into a single "10 hours" estimate; v2 splits these explicitly.

### §9.1 — Machine time (script execution wall-clock)

| Phase | Step count | Network rate | Read-back overhead | Activity-log overhead | Estimated wall-clock |
|---|---|---|---|---|---|
| Phase 0 | snapshot pull (~500 rows) + dry-run + canonical-root resolution | ~100 ms/row | included in pull | 1 marker row | ~3 minutes |
| Phase 1 | 29 PATCH+read-back+log | ~100 ms PATCH + 100 ms read-back + 50 ms log | 2x | 29 rows | ~1 minute |
| Phase 2 | 37 PATCH+read-back+log | same | same | 37 rows | ~1.5 minutes |
| Phase 3 | (Kim manual UI) | n/a | n/a | 1 marker row | n/a (Kim's hands) |
| Phase 4 | ~110 PATCH+read-back+log | same | same | ~110 rows | ~5 minutes |
| Phase 5 (if authorized) | 320 PATCH+read-back+log | same | same | 320 rows | ~14 minutes |
| Phase 6 | 3 audit queries + report write + 1 LD POST | ~5 seconds | n/a | 5 rows | ~1 minute |

**Machine time total (all phases including Phase 5):** ~25 minutes wall-clock.
**Machine time total (Phase 5 deferred):** ~11 minutes wall-clock.

Assumption set: stable Directus connection, no rate-limit throttling, no retries needed. Add 50% headroom for partial-batch resumes.

### §9.2 — Human review time (Kim's attention)

| Phase | Kim review activity | Estimated focused time |
|---|---|---|
| Pre-Phase 0 | Read this spec v2 + confirm Gates 1-9 | 60 minutes |
| Phase 0 | Review dry-run report + snapshot metadata sidecar; emit "Phase 0 approved" LD row | 30 minutes |
| Phase 1 | Review first-5 dry-run output; emit "Phase 1 first-5 approved" row | 15 minutes |
| Phase 2 | Review first-5 dry-run output; emit row | 15 minutes |
| Phase 3 | Author 7 enum values in Directus admin UI; emit "Phase 3 schema extended" row | 30 minutes |
| Phase 4 | Review first-5 + per-row triage for ambiguous values (~10 rows); emit row | 90 minutes |
| Phase 5 (if authorized) | Author `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` LD with "Kim approved"; set `PHASE_5_ENABLED=true`; review first-5 dry-run; emit row | 60 minutes |
| Phase 6 | Review final audit report; approve or amend the standing-rule LD | 60 minutes |
| Mid-session interruptions, re-reads, "wait, why does this row…" digressions | (estimated padding) | 90 minutes |

**Human review time total (all phases including Phase 5):** ~7.5 hours focused attention.
**Human review time total (Phase 5 deferred):** ~6.5 hours focused attention.

Assumption set: Kim is unfamiliar with the audit before reading the spec; familiar after the first read. Phase 4 per-row triage on ambiguous values dominates the budget. Mid-session interruptions are real and accounted for.

### §9.3 — Total planning baseline (combined)

**Combined planning baseline (all phases including Phase 5):** ~10 hours total (~25 minutes machine + ~7.5 hours human + buffer for context switches between machine wait and Kim review).
**Combined planning baseline (Phase 5 deferred):** ~7 hours total.

This is the figure to cite when scheduling the migration session(s). If Kim's available focused time in a week falls below the combined baseline, the migration is split across multiple sessions per the §9 multi-session recommendation.

### §9.4 — Other operational notes (preserved verbatim from v1)

- **Run order matters:** Phase 1 (scope_domain) and Phase 2 (case-fold) are commutative and safe in either order. Phase 3 MUST precede Phase 4 (enum target must exist). Phase 5 is independent of all others (and additionally gated by §3.1 Layer 2 flag).
- **Single-session vs multi-session:** safest is multi-session (one Kim approval per phase between sessions). Aggressive is single-session with all gates pre-approved upfront. Default recommendation: multi-session, with Phase 1 + Phase 2 as a "low-risk warmup" session and Phase 5 as its own gated session.
- **Concurrency:** the migration script MUST hold a lockfile so a concurrent run cannot double-PATCH rows. Recommend `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` (this path is global Claude config, allowed by §3.0 outside-canonical rule).

---

## §10 — Cursor review companion (v2 amended)

This spec v2 is paired with a Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` (handoff template v2 dual-canonical format). Cursor's verdict authorizes / amends / blocks before any migration session is scheduled.

The Cursor review handoff is mandatory before Phase 1 begins. v1 of this companion handoff is preserved at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` as historical baseline.

---

## §11 — Reference index (v2 expanded)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec.
- `Production/lib/severity_vocab.py` — Part 1 helper.
- `Production/scripts/governance_drift_check.py` — vocab-tolerant consumer (Part 1).
- `Production/scripts/failure_mode_matrix.py` — vocab-tolerant consumer (Part 1).
- `Production/scripts/preflight_hook.py` — vocab-tolerant consumer (Part 1).
- `Production/scripts/lock_decision.py` — current LD-writer wrapper; choices list will need extending to include HARD when migration runs (currently still legacy choices).
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule.
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for §3.0 path discipline.
- `.claude/skills/zero-error-qa/SKILL.md` DS-27 (refactored 2026-05-08 v2 dual-canonical) — agent-side enforcement.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` (refactored 2026-05-08 v2 dual-canonical) — handoff format used by §10's companion.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` — companion review handoff (v2).
- `Production/docs/DS27_DUAL_PATH_REFACTOR_AND_SCHEMA_SPEC_V2_REPORT_20260508.md` — final proof report for the bundled DS-27 dual-path refactor + this spec v2.

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: DESIGN ONLY pending Cursor review + Kim's gate-1-through-8 decisions.
- **v2** — 2026-05-08 — Cursor AMEND_V2 amendments applied: (1) HIGH `PHASE_5_ENABLED` feature flag at three layers (§3.1 + §5 Phase 5 + §6 Gate 9 + §7 risk #9); (2) HIGH path discipline §3.0 dual-canonical-roots + Phase 0 Step 0 resolution; (3) MED Phase 0 snapshot schema with `row_count` + `id_uniqueness` + `all_touched_ids_present` (§4 + §5 Phase 0 + §6 Gate 7 expanded + §8 Phase 5 rollback tie); (4) MED §9 cost split machine/human/combined. v1 preserved as historical baseline. Author: Claude Opus 4.7 (1M context).
