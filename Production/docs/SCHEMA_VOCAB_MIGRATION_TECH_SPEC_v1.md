# Schema Vocab Migration — Tech Spec v1

**Authored:** 2026-05-08.
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance + data migration).
**Status:** DESIGN ONLY — execution is gated on Kim approval per §7.

**Related artifacts:**
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec (severity / task_category / scope_domain audit).
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed; this migration spec does NOT depend on it but COMPLEMENTS it.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating that future code import the helper rather than rolling its own dict.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion (see §10).

---

## §1 — Goal

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

## §2 — Background

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

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules

Each rule is debated as an Advocate vs Counter pair. Resolution criteria are explicit and tied to evidence in the cleanup report.

### Rule 1 — severity HIGH/CRITICAL → HARD migration

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

**Verdict:** **DEFER, lean Counter.** The Counter case wins on cost-vs-benefit: Part 1 already solved the correctness problem; the migration only buys aesthetic consistency. If Kim wants to migrate anyway for clarity, the Advocate position has a clean execution plan in §5; treat that as an OPTIONAL future polish session, not a blocker.

If migration IS authorized, the mapping is:
- `CRITICAL` → `HARD` (129 rows)
- `critical` → `HARD` (2 rows)
- `HIGH` → `HARD` (174 rows)
- `high` → `HARD` (15 rows)

Total: 320 rows touched.

### Rule 2 — lowercase severity variants

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

### Rule 3 — task_category remap / extend / split

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

### Rule 4 — scope_domain remap

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

## §4 — Per-rule action table

Consolidating the four rules into a single execution-ready table:

| Rule | Action | Volume | Risk | Depends-on |
|---|---|---|---|---|
| 1 | severity HIGH/CRITICAL → HARD | 320 rows | LOW (mechanical) | Kim approves Counter-or-Advocate verdict |
| 2 | severity lowercase → UPPERCASE | 37 rows | TRIVIAL (case-fold) | none |
| 3a | task_category enum extension (7 new values) | 0 rows | LOW (Kim performs in admin UI) | Kim approves the 7 names |
| 3b | task_category synonym remaps | ~110 rows | LOW (mechanical) | Rule 3a (extension) lands first |
| 4 | scope_domain remaps | 29 rows | LOW (mechanical) | none |

**Total row touches (max scope):** 320 + 37 + 110 + 29 = ~496 PATCHes.

**Schema enum changes (Kim's hands):** 7 task_category additions in the Directus admin UI before Rule 3b begins.

If Kim chooses the Counter verdict on Rule 1, the total drops to ~176 PATCHes (37 + 110 + 29).

---

## §5 — Migration sequence

A migration script `Production/scripts/migrate_schema_vocab_v1.py` performs the work in 6 phases. Each phase is independently approvable + skippable.

### Phase 0 — Non-mutating dry run

For each rule's mapping, the script:
1. Pulls current row counts for each old/new value pair from Directus.
2. Emits a JSON dry-run report with: `rows_to_touch`, `current_values`, `target_values`, `expected_after_counts`.
3. Writes the report to `Production/docs/SCHEMA_VOCAB_MIGRATION_DRY_RUN_<YYYYMMDD>.md`.
4. NO PATCHes performed.

**Gate:** Kim reviews the dry-run report and emits a "Phase 0 approved" Directus row in `prod_activity_log` (decision_key `SCHEMA_VOCAB_MIGRATION_PHASE_0_APPROVED_V1`). Without this row, Phase 1 refuses to run.

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

### Phase 5 — Rule 1 (severity HIGH/CRITICAL → HARD, 320 rows) — ONLY IF KIM AUTHORIZES

Per the §3 verdict, this phase runs ONLY if Kim explicitly approves the lossy collapse. Mapping:
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

## §6 — Pre-implementation gates Kim must approve

Before any migration phase runs, Kim must explicitly answer:

| # | Gate | Kim's decision required |
|---|---|---|
| 1 | Rule 1 verdict: migrate severity HIGH/CRITICAL → HARD (320 rows, lossy) OR DEFER per the Counter case? | DEFER / EXECUTE |
| 2 | Rule 3a: approve the 7 task_category additions verbatim? | ENUMS APPROVED / AMEND / DEFER |
| 3 | Rule 3b ambiguous values (`production_pipeline`, `visual_production`, `tools`, `feature`): triage per-row, OR collapse them into existing canonical? | TRIAGE / COLLAPSE |
| 4 | RESOLVED_BUT_NOT_CLOSED rows (~30 estimated): close them now (status=superseded), keep as standing-reference HARD, or defer? | CLOSE / KEEP / DEFER |
| 5 | Phase 5 first-5 dry-run: approve before the remaining 315 PATCHes? | YES / NO (per phase) |
| 6 | Migration script authoring: should Claude write `migrate_schema_vocab_v1.py` first and have Cursor cross-review BEFORE any Directus PATCH runs? | YES (recommended) / NO |
| 7 | Backup: should the migration script snapshot every touched row's full body to `Production/docs/SCHEMA_VOCAB_MIGRATION_BACKUP_<YYYYMMDD>.jsonl` before any PATCH? | YES (recommended) / NO |
| 8 | Activity-log volume: ~500 activity-log rows in one session is high-volume; should the audit-trail entries be batched (one row per phase) or per-row? | PER-ROW (recommended for forensic) / BATCHED |

---

## §7 — Risk assessment

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

---

## §8 — Rollback per phase

Each phase has an independent rollback path:

- **Phase 0 (dry-run):** no rollback needed (no mutations).
- **Phase 1 (scope_domain):** for every activity-log row matching `rule=4`, PATCH the row's scope_domain back to the `old` value.
- **Phase 2 (severity case-fold):** symmetric — PATCH each row back to lowercase from the audit-log.
- **Phase 3 (Kim's enum extension):** Kim removes the 7 added enum values via Directus admin UI. Existing rows that USE those values (post-Phase-4) become technically out-of-enum (but Directus still accepts them on read; new writes would reject). **Phase 4 should NOT run unless Phase 3 is permanent.**
- **Phase 4 (task_category remap):** for every activity-log row matching `rule=3b`, PATCH back.
- **Phase 5 (severity HARD migration):** for every activity-log row matching `rule=1`, PATCH back to the snapshot-recorded `old` value. **This is the most consequential rollback** because Phase 5 is the lossy phase; the snapshot must capture the original CRITICAL vs HIGH distinction.

---

## §9 — Operational notes

- **Run order matters:** Phase 1 (scope_domain) and Phase 2 (case-fold) are commutative and safe in either order. Phase 3 MUST precede Phase 4 (enum target must exist). Phase 5 is independent of all others.
- **Single-session vs multi-session:** safest is multi-session (one Kim approval per phase between sessions). Aggressive is single-session with all gates pre-approved upfront. Default recommendation: multi-session, with Phase 1 + Phase 2 as a "low-risk warmup" session and Phase 5 as its own gated session.
- **Performance:** ~500 PATCHes at 100ms-per-PATCH = ~50 seconds of network time, with read-back doubling that. Total ~2-minute network budget. Activity-log writes add another ~1 minute. Total wall-clock: 3-5 minutes per phase.
- **Concurrency:** the migration script MUST hold a lockfile so a concurrent run cannot double-PATCH rows. Recommend `~/.claude/mindfulnest-cache/schema_vocab_migration.lock`.

---

## §10 — Cursor review companion

This spec is paired with a Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508.md` (handoff template v2 format). Cursor's verdict authorizes / amends / blocks before any migration session is scheduled.

The Cursor review handoff is mandatory before Phase 1 begins.

---

## §11 — Reference index

- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec.
- `Production/lib/severity_vocab.py` — Part 1 helper.
- `Production/scripts/governance_drift_check.py` — vocab-tolerant consumer (Part 1).
- `Production/scripts/failure_mode_matrix.py` — vocab-tolerant consumer (Part 1).
- `Production/scripts/preflight_hook.py` — vocab-tolerant consumer (Part 1).
- `Production/scripts/lock_decision.py` — current LD-writer wrapper; choices list will need extending to include HARD when migration runs (currently still legacy choices).
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule.
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff format used by §10's companion.

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: DESIGN ONLY pending Cursor review + Kim's gate-1-through-8 decisions.
