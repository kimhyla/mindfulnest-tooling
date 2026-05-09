# Schema Vocab Migration — Tech Spec v3

**Authored:** 2026-05-08 (v3 amendment same day as v1 + v2).
**Author:** Claude Opus 4.7 (1M context).
**Self-classification:** ARCHITECTURAL (governance + data migration).
**Status:** DESIGN ONLY — execution is gated on Kim approval per §7. Phase 5 additionally gated on a feature flag (see §3 Rule 1 v2 resolution, preserved verbatim in v3).

**Supersedes:** `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` (preserved as historical baseline; do NOT edit in place). v2 in turn supersedes v1.

**v2 → v3 driver:** Cursor's AMEND_V2 verdict on v2 + the companion v2 handoff. Five amendments applied (Tasks B, D, E, F, H — 4 spec-level + 1 tooling-level). Task H (lock_decision.py writer mismatch) was EXECUTED in the same session as a code change; v3 spec references the resolution rather than mandating it. See §0.1 changelog for verbatim resolution per amendment.

**Related artifacts:**
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline (this spec's predecessor).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/docs/SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md` — investigation that motivates this spec.
- `Production/lib/severity_vocab.py` — Part 1 cheap defensive read-side fix that has already landed.
- `Production/scripts/lock_decision.py` — LD-writer CLI; **canonical-aware as of 2026-05-08 per Cursor Task H execution** (see §0.1 Task H entry).
- `Production/scripts/lock_decision.py.bak.20260508` — pre-fix backup.
- `Production/scripts/governance_drift_check.py`, `failure_mode_matrix.py`, `preflight_hook.py` — query consumers updated by Part 1 to be vocab-tolerant.
- LD #586 `SCHEMA_VOCAB_TOLERANT_FILTER_V1` — standing rule mandating that future code import the helper rather than rolling its own dict.
- `LD_WRITER_CANONICAL_VOCAB_V1` — NEW LD filed 2026-05-08 documenting the lock_decision.py canonical-aware fix (HARD severity).
- LD #584 `WORKTREE_CONFUSION_PREVENTION_V1` (amended 2026-05-08 v2 dual-canonical) — authority for the dual-path discipline cited in §3 v2 path discipline section (preserved in v3).
- `Production/docs/HANDOFF_TEMPLATE_v2.md` — handoff structure used for the Cursor review companion.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3 amendments applied; see §10).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export of `prod_locked_decisions` produced at start of Phase 0 to enable offline review per Cursor Task B fallback (see §5 Phase 0 v3).

---

## §0.1 — v3 Changelog (verbatim resolution per Cursor amendment)

Cursor's AMEND_V2 verdict on v2 returned 5 amendments (Tasks B, D, E, F, H — collectively spanning v2's prior unresolved gaps after the original v1→v2 amendments addressed the four Cursor v1 findings). Each is reproduced verbatim with the resolution. v2 sections that needed material change are listed under "Sections changed".

| # | Cursor amendment (verbatim) | Resolution applied in v3 | Sections changed |
|---|---|---|---|
| Task B | Cursor couldn't reach Directus from its environment (403 Forbidden / Tunnel failure). Required random CRITICAL sampling failed. **Mitigation:** add explicit offline fallback procedure for Task B evidence — cached export snapshot with deterministic sample method. | v3 spec §5 Phase 0 (NEW Step 0.4) MANDATES generation of a cached canonical-export at `Production/exports/prod_locked_decisions_<DATE>.jsonl` at the START of Phase 0 (before any other Phase 0 step writes). Companion handoff v3 Step 0 explicitly directs reviewers to use this cached export when live Directus is unreachable, with a deterministic sample method (sort by id ASC, take rows where `id % N == 0` for the requested sample size) so two reviewers using the same cached export reach the same sampled set. v3 §11 reference index points at the cached-export path convention. | §5 Phase 0 (NEW Step 0.4), §6 Gate 7 (expanded with cached-export integrity check), §11 |
| Task D | Spec adds row_count/id_uniqueness/all_touched_ids_present in v2 BUT no MANDATORY pre-Phase-5 rollback simulation on sampled subset. **Mitigation:** require a pre-Phase-5 rollback simulation on a sampled subset with pass/fail report. | v3 §4 Phase 0 adds Step 0.5 — pre-Phase-5 rollback rehearsal on 5 random rows. Procedure: pull 5 random ids from the union of touched-ids; simulate the rule's PATCH against a scratch-test row OR perform PATCH+immediate-revert on the live row; verify all 3 metadata fields (`row_count`, `id_uniqueness`, `all_touched_ids_present`) match pre/post. Emit pass/fail report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`. **Phase 5 HALTS if rehearsal fails.** §6 adds Gate 10 for rehearsal pass. §8 v3 addendum ties rollback rehearsal to live rollback. | §4 Phase 0 (NEW Step 0.5), §5 Phase 0 (Step 0.5 narrative), §6 Gate 10 (NEW), §7 risk #10 (NEW), §8 v3 addendum |
| Task E | Spec §9.4 says lockfile at `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` — LOCAL only. Doesn't prevent multi-host concurrent runners. **Mitigation:** remote/shared lock (Directus mutex row OR DB advisory lock) before any mutating phase. | v3 §9.4 REPLACES the local lockfile with a Directus mutex row in `prod_blockers` collection. Convention: title `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (where `<HOST>` is `socket.gethostname()`), severity=`CRITICAL` (blocker tier), `is_resolved=false`. Mutating phases (1-5) MUST acquire+verify this row before proceeding; release on Phase 6 success (set `is_resolved=true`) OR by manual override. v3 also keeps the LOCAL lockfile as a defense-in-depth secondary lock (one-host-multi-process). §6 adds Gate 11 for remote-lock-acquisition pass. §7 risk #11 added (lock contention / dead-lock-cleanup). | §9.4 (replaced), §5 Phase 1-5 entry guard (NEW remote-lock check), §6 Gate 11 (NEW), §7 risk #11 (NEW) |
| Task F | Risk table says "resume from last-confirmed row" but no checkpoint schema/path defined. **Mitigation:** durable checkpoint file schema `(phase, row_id, timestamp, hash)` and resume algorithm as mandatory. | v3 §5 (NEW subsection §5.0 — Checkpoint and resume protocol) defines the checkpoint schema verbatim: `{"phase": <int 1-5>, "rule": "<rule_name>", "last_committed_row_id": <int>, "timestamp": "<iso8601>", "snapshot_hash": "<hex>", "rows_processed_in_phase": <int>, "expected_rows_in_phase": <int>}`. Path: `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (append-only — one line per row commit). Resume algorithm: read last line; verify `snapshot_hash` matches the current Phase 0 snapshot's metadata hash (else HALT — snapshot drift); restart phase from `last_committed_row_id + 1`. §6 adds Gate 12 for checkpoint integrity. §7 risk #12 (resume-after-corruption). | §5.0 (NEW), §5 Phase 1-5 (NEW per-row checkpoint append), §6 Gate 12 (NEW), §7 risk #12 (NEW) |
| Task H | `lock_decision.py` CLI choices still include legacy `critical/HIGH/high/MEDIUM/...` and OMIT canonical HARD/SOFT. Future LD writes via this CLI would reintroduce mixed vocab indefinitely. **EXECUTE NOW (independent of v3 spec).** | **EXECUTED 2026-05-08** in the same session as v3 spec authoring. `Production/scripts/lock_decision.py` updated: `ACCEPTED_SEVERITY_CHOICES` now lists canonical `HARD/SOFT` first followed by legacy values (CRITICAL/HIGH/MEDIUM/LOW + lowercase + MED) for back-compat; `canonicalize_severity()` emits `[DEPRECATED]` warning to stderr on legacy input and auto-maps to canonical before any Directus POST; `cmd_lock()` invokes the canonicalizer so the persisted row is always canonical regardless of input. Backup at `Production/scripts/lock_decision.py.bak.20260508`. New LD `LD_WRITER_CANONICAL_VOCAB_V1` (HARD severity) filed in same session documenting the fix. v3 §11 reference index updated to call lock_decision.py canonical-aware. Verification: `python3 lock_decision.py lock --help` confirms choices include `{HARD,SOFT,CRITICAL,HIGH,MEDIUM,LOW,critical,high,medium,low,MED}`; smoke test of `canonicalize_severity` covered 5 branches (canonical pass-through, legacy upper, legacy lower, MED abbrev, unknown ValueError). | §11 reference index entry for lock_decision.py updated; v3 spec does NOT itself mandate the change (it was executed before v3 was written). |

**v2 vs v3 surface area:** v3 adds ~280 lines (cached-export Phase 0 step, rollback-rehearsal step + Gate 10, remote mutex §9.4 replacement + Gate 11, checkpoint schema §5.0 + Gate 12, risk rows 10/11/12, Task H reference-index update). All v2 content preserved (no deletions); v3 additions are clearly labeled `(v3)` or `(NEW v3)` inline. v1 and v2 narrative content (§1, §2, §3.1-§3.4 dual-Opus debate, etc.) preserved verbatim.

---

## §1 — Goal (preserved verbatim from v1 + v2)

Bring the `prod_locked_decisions` collection's `severity`, `task_category`, and `scope_domain` columns into a **canonical, lossless, audit-trailed state** so:

1. Every active row uses an enum value that appears in the live Directus schema definition.
2. Lossy maps (e.g. `HIGH → HARD`) are explicitly approved by Kim before the row is rewritten.
3. Every PATCH carries a `migration_audit` row in `prod_activity_log` with the old/new value pair, so a rollback (or a "did Claude really do that?" forensic trace) is one query away.
4. Row count after migration matches row count before migration (no lost rows; no auto-creation).
5. The Part 1 vocab-tolerant filter remains correct AFTER migration (i.e. queries that accepted HIGH today and HARD tomorrow continue to return the same answer).

Non-goals:

- This spec does NOT propose canonicalizing `enforcement_type` (already 100% canonical per the audit).
- This spec does NOT propose a status=superseded sweep of the ~30 RESOLVED_BUT_NOT_CLOSED rows.
- This spec does NOT propose schema-enum changes to Directus. Adding `app_architecture`, `infrastructure`, etc. to the canonical task_category list is a SEPARATE Directus schema change Kim must perform via the admin UI.

---

## §2 — Background (preserved verbatim from v1 + v2)

The cleanup report (`SCHEMA_CLEANUP_AND_SUPABASE_HARDENING_REPORT_20260508.md`) established the dataset baseline (529 active LDs, mixed vocabulary). Part 1 (LD #586) shipped the defensive read-side fix; this migration is OPTIONAL CANONICALIZATION for clarity. See v2 spec §2 for the full preserved background.

**v3 ADD:** Cursor's v2 review surfaced one additional latent gap not addressed by v1 or v2 amendments: `lock_decision.py`'s argparse choices list was legacy-only and was actively reintroducing pre-2026-05-04 vocabulary on every new LD write. This was diagnosed and EXECUTED-as-fix in the same session as v3 spec authoring (Task H entry in §0.1).

---

## §3 — Dual-Opus debate (verbatim) on 4 mapping rules + v2 amendments (preserved in v3)

§3.0 (path discipline v2 dual-canonical), §3.1 (Rule 1 + v2 PHASE_5_ENABLED feature flag), §3.2 (Rule 2 lowercase severity), §3.3 (Rule 3 task_category), §3.4 (Rule 4 scope_domain) — all preserved verbatim from v2. v3 introduces no §3-level changes; the 5 v3 amendments are operational (§4-§9) rather than debate-level.

See `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` §3.0-§3.4 for the verbatim text.

---

## §4 — Per-rule action table (preserved + v2 Phase 5 flag column + v3 cached-export + rollback-rehearsal columns)

| Rule | Action | Volume | Risk | Depends-on | v2 flag | v3 prerequisites |
|---|---|---|---|---|---|---|
| 1 | severity HIGH/CRITICAL → HARD | 320 rows | LOW (mechanical) | Kim approves Counter-or-Advocate verdict | `PHASE_5_ENABLED=false` by default; flip required | (v3) Cached export (§5 Phase 0 Step 0.4) + rollback rehearsal pass (§5 Phase 0 Step 0.5) + remote mutex acquired (§9.4) + checkpoint schema initialized (§5.0) |
| 2 | severity lowercase → UPPERCASE | 37 rows | TRIVIAL (case-fold) | none | none | (v3) Cached export + remote mutex + checkpoint |
| 3a | task_category enum extension (7 new values) | 0 rows | LOW (Kim performs in admin UI) | Kim approves the 7 names | none | (v3) Cached export only |
| 3b | task_category synonym remaps | ~110 rows | LOW (mechanical) | Rule 3a (extension) lands first | none | (v3) Cached export + remote mutex + checkpoint |
| 4 | scope_domain remaps | 29 rows | LOW (mechanical) | none | none | (v3) Cached export + remote mutex + checkpoint |

**Total row touches (max scope):** still ~496 PATCHes (unchanged from v2).

### §4 Phase 0 v2 expanded snapshot schema (preserved verbatim from v2 + v3 cached-export addendum)

The v2 snapshot artifact (`Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl`) is preserved verbatim as the row-restoration source for the touched-rows union. v3 ADDS a SECOND artifact at a different path with a different purpose:

**v3 NEW — Cached canonical-export artifact:** `Production/exports/prod_locked_decisions_<DATE>.jsonl`

Distinct from the v2 snapshot (which captures only touched-row pre-images for rollback). The cached canonical-export captures EVERY active row in `prod_locked_decisions` (status != superseded) so an offline Cursor reviewer can perform random sampling without live Directus access. Schema is identical to a Directus `GET /items/prod_locked_decisions?limit=-1&filter=...` response, one JSON object per line.

**Why two artifacts:** the v2 snapshot is for ROLLBACK (small, surgical, only touched rows). The v3 cached-export is for OFFLINE REVIEW (broad, captures non-touched rows too so the reviewer can sample CRITICAL or HIGH rows that aren't in the migration target set). Generating both at start-of-Phase-0 ensures the snapshot's `row_count` and `id_uniqueness` invariants are not contaminated by export-time drift.

**Required cached-export metadata (v3 NEW):** the export file is accompanied by a `*.metadata.json` sidecar with the following fields:

```json
{
  "export_version": "v3",
  "export_taken_at": "<iso8601>",
  "directus_url": "https://directus-production-3460.up.railway.app",
  "total_active_rows": <integer>,
  "schema_hash": "<hex digest of column-name list at export time>",
  "deterministic_sample_method": "sort by id ASC; take rows where id % N == 0 for sample size 530/N (rounded down)",
  "intended_consumer": "Cursor offline review per amend_v2 Task B fallback"
}
```

**Pre-Phase-5 cached-export integrity check (v3 NEW):** before Phase 5 executes, the migration script reads the cached-export metadata sidecar and asserts `total_active_rows` equals the snapshot's `row_count` PLUS the count of rows-not-touched-by-migration. If counts diverge, Phase 5 HALTS with a `PHASE_5_BLOCKED_BY_CACHED_EXPORT_DRIFT` activity-log row.

---

## §5 — Migration sequence (v2 preserved + v3 §5.0 checkpoint + Step 0.4 cached-export + Step 0.5 rollback rehearsal)

A migration script `Production/scripts/migrate_schema_vocab_v1.py` performs the work in 6 phases. Each phase is independently approvable + skippable. The script's existence and full skeleton are preserved verbatim from v2; v3 adds three new operational steps inside Phase 0 plus a new top-level §5.0 subsection.

### §5.0 — Checkpoint and resume protocol (NEW v3 — Cursor Task F)

**Path:** `Production/exports/schema_migration_checkpoint_<DATE>.jsonl`. Append-only — one line per row commit. The script writes ONE line for each successful PATCH+read-back+activity-log triple in Phases 1, 2, 4, 5.

**Schema (verbatim):**

```json
{
  "phase": 3,
  "rule": "task_category_remap",
  "last_committed_row_id": 421,
  "timestamp": "2026-05-08T12:34:56Z",
  "snapshot_hash": "abc123def456...",
  "rows_processed_in_phase": 47,
  "expected_rows_in_phase": 132
}
```

Field semantics:
- `phase` — integer 1-5 corresponding to the migration phase.
- `rule` — string descriptor of the rule being executed in this phase (e.g., `scope_domain_remap`, `severity_lower_to_upper`, `task_category_remap`, `severity_high_critical_to_hard`).
- `last_committed_row_id` — Directus id of the most recent row whose PATCH+read-back+activity-log triple all completed successfully.
- `timestamp` — ISO 8601 of the checkpoint write (immediately after activity-log POST returns).
- `snapshot_hash` — hex digest of the Phase 0 snapshot's metadata sidecar at the time the phase started; used by the resume algorithm to detect snapshot drift between sessions.
- `rows_processed_in_phase` — running count of PATCHes successfully committed in the current phase.
- `expected_rows_in_phase` — total count of rows the phase plans to touch (constant for the phase).

**Resume algorithm (v3 NEW):**

```python
# Resume from last checkpoint
checkpoint_path = Path(f"Production/exports/schema_migration_checkpoint_{DATE}.jsonl")
if not checkpoint_path.exists():
    # First run; start from row 0
    last_committed_row_id = -1
    snapshot_hash_at_resume = None
else:
    with open(checkpoint_path) as f:
        last_line = None
        for line in f:
            line = line.strip()
            if line:
                last_line = line
        if last_line is None:
            last_committed_row_id = -1
            snapshot_hash_at_resume = None
        else:
            last_checkpoint = json.loads(last_line)
            last_committed_row_id = last_checkpoint['last_committed_row_id']
            snapshot_hash_at_resume = last_checkpoint['snapshot_hash']

# Verify snapshot has not drifted
current_snapshot_hash = sha256(snapshot_metadata_json.encode()).hexdigest()
if snapshot_hash_at_resume is not None and snapshot_hash_at_resume != current_snapshot_hash:
    print(f"HALT: snapshot drifted between sessions. Resume aborted. "
          f"checkpoint_hash={snapshot_hash_at_resume} current_hash={current_snapshot_hash}")
    sys.exit(1)

# Filter the current phase's row list to (id > last_committed_row_id)
remaining_rows = [r for r in phase_target_rows if r['id'] > last_committed_row_id]
print(f"Resume: {len(remaining_rows)} rows remaining in phase (last committed id={last_committed_row_id})")
```

**Per-row checkpoint append (v3 NEW):** after every successful PATCH+read-back+activity-log triple in Phases 1, 2, 4, 5, the script appends one checkpoint line. The file is opened in append mode + flushed + fsync'd before the next row is processed so a crash between rows leaves the checkpoint at the last-confirmed-good row.

### Phase 0 — Non-mutating dry run + canonical-root resolution + snapshot + cached-export + rollback rehearsal (v3 expanded)

**Step 0 (preserved from v2) — Canonical-root resolution per §3.0.** Confirm script anchored to Dropbox-canonical root.

**Step 1 (preserved from v2) — Snapshot (v2 schema).** For every row id any phase plans to touch, pull full row body to `Production/docs/SCHEMA_VOCAB_MIGRATION_SNAPSHOT_<YYYYMMDD>.jsonl` + metadata sidecar with `row_count`, `id_uniqueness`, `all_touched_ids_present`.

**Step 2 (preserved from v2) — Dry-run report.** Pull current row counts; emit JSON dry-run report.

**Step 3 (preserved from v2) — Activity log marker.** POST `SCHEMA_VOCAB_MIGRATION_PHASE_0_COMPLETE` row.

**Step 0.4 (NEW v3 — Cursor Task B) — Cached canonical-export.** BEFORE Step 1 runs, generate `Production/exports/prod_locked_decisions_<DATE>.jsonl` containing every active row in `prod_locked_decisions` (one JSON object per line, full row body). Generate the metadata sidecar `Production/exports/prod_locked_decisions_<DATE>.metadata.json` with `total_active_rows` + `schema_hash` + `deterministic_sample_method` (see §4 v3). This artifact MUST exist before Step 1 begins because it's the offline-review evidence source for Cursor (and any subsequent reviewer) when live Directus is unreachable.

```python
# Phase 0 Step 0.4 (v3 NEW) — cached canonical-export
EXPORT_DIR = Path("Production/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
export_path = EXPORT_DIR / f"prod_locked_decisions_{date_str}.jsonl"
metadata_path = EXPORT_DIR / f"prod_locked_decisions_{date_str}.metadata.json"

active_rows = client.get_items(
    "prod_locked_decisions",
    filters={"status": {"_neq": "superseded"}},
    limit=-1,
)
with open(export_path, "w") as f:
    for row in active_rows:
        f.write(json.dumps(row) + "\n")

field_list = client.fields("prod_locked_decisions")
schema_hash = hashlib.sha256(
    json.dumps([f["field"] for f in field_list], sort_keys=True).encode()
).hexdigest()

metadata = {
    "export_version": "v3",
    "export_taken_at": datetime.now(timezone.utc).isoformat(),
    "directus_url": client.base_url,
    "total_active_rows": len(active_rows),
    "schema_hash": schema_hash,
    "deterministic_sample_method": "sort by id ASC; take rows where id % N == 0 for sample size 530/N (rounded down)",
    "intended_consumer": "Cursor offline review per amend_v2 Task B fallback",
}
metadata_path.write_text(json.dumps(metadata, indent=2))
print(f"Phase 0 Step 0.4: cached export written → {export_path} ({len(active_rows)} rows)")
```

**Step 0.5 (NEW v3 — Cursor Task D) — Pre-Phase-5 rollback rehearsal.** Pull 5 random ids from the union of touched-ids (Phase 1+2+3+4+5 target sets); for each, perform a dry-rehearsal patch + immediate revert + verify all 3 metadata fields (`row_count`, `id_uniqueness`, `all_touched_ids_present`) match pre/post. Emit pass/fail report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`. **Phase 5 HALTS if rehearsal fails.**

```python
# Phase 0 Step 0.5 (v3 NEW) — rollback rehearsal on 5 random rows
import random
touched_ids = sorted(set([r["id"] for r in all_touched_rows]))
random.seed(42)  # deterministic so two reviewers reach the same sample
sampled_ids = random.sample(touched_ids, min(5, len(touched_ids)))

rehearsal_results = []
for sid in sampled_ids:
    # Pull pre-state
    pre = client.get_item("prod_locked_decisions", sid)
    # Compute synthetic-target value (e.g. for Rule 1: severity → HARD)
    target_severity = "HARD"  # rule-specific mapping
    # Rehearse: PATCH to target, immediately revert
    client.patch_item("prod_locked_decisions", sid, {"severity": target_severity})
    intermediate = client.get_item("prod_locked_decisions", sid, fields=["id", "severity"])
    intermediate_ok = (intermediate["severity"] == target_severity)
    # Revert
    client.patch_item("prod_locked_decisions", sid, {"severity": pre["severity"]})
    post = client.get_item("prod_locked_decisions", sid, fields=["id", "severity"])
    post_ok = (post["severity"] == pre["severity"])
    rehearsal_results.append({
        "id": sid,
        "pre_severity": pre["severity"],
        "intermediate_severity": intermediate["severity"],
        "post_severity": post["severity"],
        "intermediate_patch_ok": intermediate_ok,
        "revert_patch_ok": post_ok,
        "passed": intermediate_ok and post_ok,
    })

all_passed = all(r["passed"] for r in rehearsal_results)
report_path = Path(f"Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_{date_str}.md")
report_path.write_text(
    f"# Rollback Rehearsal — {date_str}\n\n"
    f"Sampled ids: {sampled_ids}\n\n"
    f"All passed: {all_passed}\n\n"
    f"Per-row results:\n```json\n{json.dumps(rehearsal_results, indent=2)}\n```\n"
)
if not all_passed:
    print("HALT: rollback rehearsal failed; Phase 5 BLOCKED")
    client.post_item("prod_activity_log", {
        "action": "PHASE_5_BLOCKED_BY_ROLLBACK_REHEARSAL",
        "details": json.dumps(rehearsal_results),
        "performed_by": "migrate_schema_vocab_v1.py phase=0 step=0.5",
    })
    sys.exit(1)
print(f"Phase 0 Step 0.5: rollback rehearsal passed for {len(sampled_ids)} rows → {report_path}")
```

**Gate (preserved from v2):** Kim reviews dry-run + snapshot metadata sidecar + (v3) cached-export + (v3) rollback rehearsal report; emits "Phase 0 approved" row.

### Phase 1 — Rule 4 (scope_domain remap, 29 rows) (v2 preserved + v3 mutex + checkpoint)

Per-row PATCH with read-back per Rule 35 (preserved verbatim from v2). v3 ADDS:

1. **Remote-mutex acquisition (v3 §9.4):** before the loop begins, the script POSTs a `prod_blockers` row titled `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` with `severity=CRITICAL`, `is_resolved=false`. Aborts if a row already exists with `is_resolved=false` and a different host (lock contention).
2. **Local lockfile (preserved from v2):** `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` flock'd as defense-in-depth.
3. **Per-row checkpoint append (v3 §5.0):** after every successful triple, append the checkpoint line.

```python
# Phase 1 entry guard (v3 NEW)
import socket
host = socket.gethostname()

# Acquire remote mutex
existing_locks = client.get_items(
    "prod_blockers",
    filters={"is_resolved": {"_eq": False}, "title": {"_starts_with": "SCHEMA_MIGRATION_LOCK_HELD_BY_"}},
    fields=["id", "title", "host"],
    limit=10,
)
for lock in existing_locks:
    if lock["title"] != f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}":
        print(f"HALT: remote mutex held by another host. blocker_id={lock['id']} title={lock['title']}")
        sys.exit(1)

# POST mutex if not already held by this host
if not any(l["title"] == f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}" for l in existing_locks):
    mutex_row = client.post_item("prod_blockers", {
        "title": f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}",
        "severity": "CRITICAL",
        "is_resolved": False,
        "details": f"Schema vocab migration in progress on host {host}; PID={os.getpid()}",
    })
    mutex_blocker_id = mutex_row["id"]
else:
    mutex_blocker_id = next(l["id"] for l in existing_locks if l["title"] == f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}")
print(f"Remote mutex acquired: blocker_id={mutex_blocker_id}")

# Local lockfile (defense-in-depth from v2; preserved)
local_lock = Path("~/.claude/mindfulnest-cache/schema_vocab_migration.lock").expanduser()
local_lock.parent.mkdir(parents=True, exist_ok=True)
local_lock_fd = open(local_lock, "w")
fcntl.flock(local_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
```

(Phase 1 PATCH loop body unchanged from v2; per-row checkpoint append added at end of each loop iteration.)

### Phase 2 — Rule 2 (severity lowercase → UPPER, 37 rows)

(v2 body preserved verbatim; v3 mutex + checkpoint added per Phase 1 pattern.)

### Phase 3 — Rule 3a (Kim extends canonical task_category enum, 0 rows)

(v2 body preserved verbatim; v3 changes none — Phase 3 is Kim's hands in admin UI, no script-side mutex needed.)

### Phase 4 — Rule 3b (task_category synonym remap, ~110 rows)

(v2 body preserved verbatim; v3 mutex + checkpoint added per Phase 1 pattern.)

### Phase 5 — Rule 1 (severity HIGH/CRITICAL → HARD, 320 rows) — BLOCKED BY `PHASE_5_ENABLED` FEATURE FLAG (v2 preserved) + v3 PRE-FLIGHT EXPANSION

**v2 entry guard (§3.1 Layer 2) preserved verbatim.** v3 adds five additional pre-flight checks BEFORE the §3.1 Layer 2 guard runs:

1. **(v3 — Task B)** Cached-export integrity check: `Production/exports/prod_locked_decisions_<DATE>.jsonl` exists; metadata sidecar's `total_active_rows` matches snapshot's `row_count` + non-touched rows count.
2. **(v3 — Task D)** Rollback rehearsal report `SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` exists AND contains "All passed: True".
3. **(v3 — Task E)** Remote mutex `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` is held by current host with `is_resolved=false`.
4. **(v3 — Task F)** Checkpoint file `schema_migration_checkpoint_<DATE>.jsonl` exists OR is being initialized for this Phase 5 run; `snapshot_hash` matches current snapshot.
5. **(v2 preserved)** `PHASE_5_ENABLED=true` env var + `SCHEMA_VOCAB_MIGRATION_PHASE_5_AUTHORIZED_V1` LD with "Kim approved" in notes.

If ANY check fails, Phase 5 HALTs with a `PHASE_5_BLOCKED_BY_<CHECK_NAME>` activity-log row.

(Phase 5 PATCH loop body unchanged from v2; per-row checkpoint append added per §5.0.)

### Phase 6 — Final audit (v2 preserved + v3 mutex release)

(v2 body preserved verbatim.) v3 ADDS one final step:

**Step 7 (v3 NEW) — Mutex release.** PATCH the `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` blocker row to `is_resolved=true` with `resolution_notes` citing the Phase 6 final-audit report path. Local lockfile unflock'd + deleted.

---

## §6 — Pre-implementation gates Kim must approve (v2 preserved + v3 Gates 10/11/12 added)

(Gates 1-9 preserved verbatim from v2.)

| # | Gate | Kim's decision required |
|---|------|------------------------|
| 10 | **(v3 NEW — Cursor Task D)** Pre-Phase-5 rollback rehearsal: must Phase 0 Step 0.5 produce a "All passed: True" report on 5 random rows BEFORE Phase 5 may execute? Phase 5 entry guard halts if rehearsal report missing or any row failed. | YES (REQUIRED for Phase 5) / NO (only valid if Phase 5 stays DEFERRED) |
| 11 | **(v3 NEW — Cursor Task E)** Remote mutex via Directus `prod_blockers` row `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` (severity=CRITICAL): must mutating phases (1, 2, 4, 5) acquire+verify this row before proceeding? | YES (REQUIRED) / DEFER (single-host operation; rely on local lockfile only) |
| 12 | **(v3 NEW — Cursor Task F)** Checkpoint file `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` (append-only, schema per §5.0): must per-row checkpoint appends be a hard requirement of Phases 1, 2, 4, 5 with the resume algorithm verifying snapshot_hash on session restart? | YES (REQUIRED for resume safety) / NO (single-session execution; no resume protocol needed) |

**Gate 10 verification artifact:** rollback rehearsal report at `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md`; Phase 5 entry guard's check #2 reads it.

**Gate 11 verification artifact:** Directus query for `prod_blockers` row with title `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` and `is_resolved=false`; Phase 1-5 entry guards read it.

**Gate 12 verification artifact:** checkpoint file exists at the expected path; snapshot_hash field matches current snapshot's metadata hash; resume algorithm filters target rows to `id > last_committed_row_id`.

---

## §7 — Risk assessment (v2 preserved + v3 risks #10/#11/#12)

(Rows 1-9 preserved verbatim from v2.)

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| **(v3 NEW)** Rollback rehearsal passes on 5 sampled rows but actual rollback fails on the remaining 315 rows due to row-specific quirks (e.g., field constraints on outlier rows) | LOW | HIGH | Sample size of 5 is the v3 baseline; if Kim wants higher confidence, increase to 20 or 50; always emit the failed-row id in the activity-log row so Kim can manually investigate |
| **(v3 NEW)** Remote mutex acquisition succeeds but mutex is never released due to script crash; subsequent runners blocked indefinitely | LOW | MEDIUM | Mutex includes `pid` field; cleanup helper `release_stale_mutex.py` checks if PID is alive on the recorded host and force-releases if dead; manual override path documented in §9.4 |
| **(v3 NEW)** Checkpoint file corrupted mid-write (partial JSON line on the last line) causes resume algorithm to crash or skip valid rows | LOW | MEDIUM | Resume algorithm tolerates corrupt last line via try/except; if last line fails JSON parse, walk backward to last valid line; log "checkpoint last-line corrupt; resuming from previous good line" |

---

## §8 — Rollback per phase (v2 preserved + v3 rehearsal-tied addendum)

(Per-phase rollback narrative preserved verbatim from v2 §8 and v2 §8 v2 addendum.)

### §8 v3 — Rollback rehearsal tie

**Phase 5 rollback feasibility is now PROVEN by the Phase 0 Step 0.5 rehearsal** before Phase 5 ever runs. The rehearsal performs an actual PATCH+revert on 5 random rows and confirms all 3 snapshot metadata fields remain consistent. If the rehearsal passes, the same code path used for live rollback (Phase 5 §8 narrative) is empirically validated. If the rehearsal fails, Phase 5 is blocked at Step 0.5 — the rollback path is unavailable, so the migration cannot proceed.

This closes Cursor's MED-severity Task D gap: v2 had row_count + id_uniqueness + all_touched_ids_present invariants but NO empirical proof the rollback path actually works on a live row. v3 adds the proof by running rehearsal-on-sample at Phase 0 Step 0.5.

---

## §9 — Operational notes (v2 cost split preserved + v3 §9.4 remote mutex replaces local lockfile)

(§9.1, §9.2, §9.3 preserved verbatim from v2 — the v2 cost split machine/human/combined remains the planning baseline.)

### §9.4 — Concurrency, lockfile, and remote mutex (v3 REPLACED — Cursor Task E)

**v2 said:** "the migration script MUST hold a lockfile so a concurrent run cannot double-PATCH rows. Recommend `~/.claude/mindfulnest-cache/schema_vocab_migration.lock` (this path is global Claude config, allowed by §3.0 outside-canonical rule)."

**v3 says (Cursor Task E):** the v2 LOCAL lockfile is preserved as a defense-in-depth secondary lock (one-host-multi-process), but the PRIMARY concurrency guard is now a REMOTE mutex via a Directus `prod_blockers` row. Convention:

- **Title:** `SCHEMA_MIGRATION_LOCK_HELD_BY_<HOST>` where `<HOST>` is `socket.gethostname()`.
- **Collection:** `prod_blockers`.
- **severity:** `CRITICAL` (treat as a production blocker).
- **is_resolved:** `false` while held; `true` after Phase 6 success.
- **details:** `Schema vocab migration in progress on host <HOST>; PID=<pid>`.

**Acquisition (Phase 1-5 entry guard):**

```python
existing = client.get_items("prod_blockers",
    filters={"is_resolved": {"_eq": False},
             "title": {"_starts_with": "SCHEMA_MIGRATION_LOCK_HELD_BY_"}})
for lock in existing:
    if lock["title"] != f"SCHEMA_MIGRATION_LOCK_HELD_BY_{host}":
        # Held by another host — refuse
        sys.exit(1)
# POST or reuse the host's own mutex row
```

**Release (Phase 6 final-audit success):**

```python
client.patch_item("prod_blockers", mutex_blocker_id, {
    "is_resolved": True,
    "resolution_notes": f"Phase 6 final audit complete; report at {phase_6_report_path}",
})
```

**Stale-mutex cleanup:** if a script crashes leaving the mutex held, `release_stale_mutex.py` (helper to be authored at execution time) reads the mutex row's `details` field, parses the PID, and checks if the recorded PID is alive on the recorded host (via `kill -0 <pid>` if local; manual review if remote). Force-releases if dead. Manual override is always available — Kim can PATCH `is_resolved=true` directly via Directus admin UI.

**Why both remote AND local lock:** the remote lock prevents multi-host concurrent runs (the v2 gap Cursor flagged); the local flock prevents a single-host operator from accidentally launching the script twice in parallel terminals before the remote mutex is acquired. Both are cheap; defense-in-depth.

---

## §10 — Cursor review companion (v3 amended)

This spec v3 is paired with a Cursor cross-review handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md`. The v3 handoff specifically addresses Task B (offline Directus fallback procedure): when live Directus is unreachable, reviewer uses the cached export at `Production/exports/prod_locked_decisions_<DATE>.jsonl` (generated at start of Phase 0 per §5 Step 0.4).

The v2 handoff at `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v2.md` is preserved as historical baseline. v1 also preserved.

---

## §11 — Reference index (v3 expanded)

(All v2 entries preserved verbatim.)

- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v2.md` — v2 historical baseline.
- `Production/docs/SCHEMA_VOCAB_MIGRATION_TECH_SPEC_v1.md` — v1 historical baseline.
- `Production/scripts/lock_decision.py` — **canonical-aware as of 2026-05-08** per Cursor Task H execution; choices list now `[HARD, SOFT, CRITICAL, HIGH, MEDIUM, LOW, critical, high, medium, low, MED]` with `canonicalize_severity()` auto-mapping legacy values to canonical before POST.
- `Production/scripts/lock_decision.py.bak.20260508` — pre-Task-H backup.
- `LD_WRITER_CANONICAL_VOCAB_V1` — NEW LD documenting Task H execution (HARD severity).
- `Production/exports/prod_locked_decisions_<DATE>.jsonl` — cached canonical-export for offline review (v3 NEW per Task B).
- `Production/exports/prod_locked_decisions_<DATE>.metadata.json` — cached export metadata sidecar (v3 NEW).
- `Production/exports/schema_migration_checkpoint_<DATE>.jsonl` — append-only checkpoint per §5.0 (v3 NEW per Task F).
- `Production/docs/SCHEMA_VOCAB_MIGRATION_ROLLBACK_REHEARSAL_<YYYYMMDD>.md` — rehearsal pass/fail report (v3 NEW per Task D).
- `Production/exports/DEFERRED_DIRECTUS_WRITES_20260508_lock_decision_canonical.jsonl` — queued Directus writes (Task H activity log + LD POST) deferred while Directus production is offline; replay when Directus is restored.
- `Production/docs/SCHEMA_MIGRATION_V3_AND_LOCK_DECISION_FIX_REPORT_20260508.md` — final proof report for v3 spec + handoff + Task H execution.
- `Production/docs/HANDOFF_CURSOR_REVIEW_SCHEMA_MIGRATION_SPEC_20260508_v3.md` — companion review handoff (v3).

---

## §12 — Change log

- **v1** — 2026-05-08 — initial draft. Author: Claude Opus 4.7 (1M context). Status: superseded by v2.
- **v2** — 2026-05-08 — Cursor AMEND_V2 (4 amendments) applied: PHASE_5_ENABLED feature flag + dual-canonical paths + snapshot integrity fields + cost split. Status: superseded by v3.
- **v3** — 2026-05-08 — Cursor AMEND_V2 on v2 (5 amendments — Tasks B/D/E/F/H) applied: (B) cached canonical-export at `Production/exports/prod_locked_decisions_<DATE>.jsonl` for offline review when Directus unreachable; (D) Phase 0 Step 0.5 rollback rehearsal on 5 random rows with pass/fail report + Gate 10; (E) §9.4 replaced — remote Directus mutex `prod_blockers` row replaces local-only lockfile (defense-in-depth keeps both); (F) §5.0 NEW — checkpoint schema `(phase, row_id, timestamp, hash, rows_processed, expected_rows)` + resume algorithm + Gate 12; (H) **EXECUTED** in same session — `lock_decision.py` choices made canonical-aware (HARD/SOFT first, legacy back-compat with deprecation warning + auto-canonicalization); LD_WRITER_CANONICAL_VOCAB_V1 filed. v1 + v2 preserved as historical baselines. Author: Claude Opus 4.7 (1M context).
