# Backup Chain Hardening — Followups Closeout Report (2026-05-08)

**Anchor commit:** `d05dfe0` on `feature/ld227-doppler-phase1-20260508`
**Sister report:** `BACKUP_CHAIN_BLOCKERS_FIX_REPORT_20260508.md` (the original Option B fix)
**Session scope:** four bundled followups closing out the Supabase backup chain work
**No commits made this session** (per explicit instruction; all artifacts staged for Kim review)

---

## Executive summary

Four out-of-scope-of-d05dfe0 followups executed in dependency order (DS-28):

| # | Task | Outcome | Artifact |
|---|---|---|---|
| 4 | prod_blockers row for historical backup gap | DONE | `prod_blockers id=100` |
| 2 | LD SUPABASE_DB_USER_DIRECT_OPTION_B_V1 | DONE | `prod_locked_decisions id=590` |
| 3 | Pooler endpoint region lookup | DONE | `aws-1-us-east-1.pooler.supabase.com` confirmed; Doppler `SUPABASE_POOLER_HOST` set; `API_KEYS_MASTER.md` updated |
| 1 | Sync mechanism for daily_backup.sh | DONE | `Production/scripts/sync_ops_scripts.sh` + `.git/hooks/post-commit` |
| — | Activity log | DONE | `prod_activity_log id=1787` |

All Directus writes followed Rule 35 (read-back-after-write). Confidence tags per Rule 24 inline below.

---

## Task 1 — Sync mechanism for daily_backup.sh (STANDARD)

### Decision rationale (rejected Option a, accepted Option b)

- **Option a — point launchd at canonical CloudStorage path:** REJECTED. Re-introduces the TCC/Full-Disk-Access issue that earlier in this session forced moving scripts OUT of CloudStorage. Regression risk on a known failure mode. [CONFIRMED]
- **Option b — sync hook + manual script:** ACCEPTED. Mirror at `~/MindfulNestOps/scripts/daily_backup.sh` stays as launchd's invocation target (TCC-friendly). Canonical at `Production/scripts/daily_backup.sh` stays in git. A post-commit hook auto-syncs after every commit; a standalone helper script supports manual runs. [CONFIRMED]

### Artifacts

| Path | Size | Mode | Purpose |
|---|---|---|---|
| `Production/scripts/sync_ops_scripts.sh` | 3391 B | 755 | One-way pull from canonical → mirror; SHA-compared, idempotent, atomic-rename, executable-bit-preserving |
| `.git/hooks/post-commit` | 1660 B | 755 | Calls sync script after every commit; best-effort (warns and exits 0 if sync script missing on branch) |

### Sync script design

- Resolves canonical via `BASH_SOURCE`-relative dirname (no env vars required).
- SHA-256 compares canonical vs mirror; silent no-op if equal; verbose if `--verbose` flag passed.
- Atomic write: copy to `${MIRROR}.tmp.$$`, `chmod +x`, then `mv` into place.
- Post-write SHA verification (Rule 35 spirit applied to filesystem write).
- Exit codes: 0 in-sync/synced, 1 canonical missing, 2 mirror dir creation failed, 3 copy failed.

### post-commit hook design

- `set +e` — never aborts caller's workflow.
- Resolves worktree root via `git rev-parse --show-toplevel`; gracefully skips with WARN if `Production/scripts/sync_ops_scripts.sh` is absent on the current branch (DS-27 dual-path safety: hook lives in shared `.git/common-dir/hooks/` and fires for ALL worktrees).
- Hook lives at `.git/hooks/post-commit` (resolved via `git rev-parse --git-common-dir` → `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/.git`); shared across all worktrees by git design.

### Verbatim test transcript

```
=== TEST 1: pre-state SHAs ===
e5a029624b7812fc06d2602e03d4e2bc25c3fdab34010b4f1b765db6947df64d  Production/scripts/daily_backup.sh
e5a029624b7812fc06d2602e03d4e2bc25c3fdab34010b4f1b765db6947df64d  ~/MindfulNestOps/scripts/daily_backup.sh

=== TEST 2: invoke sync script (in-sync expected) ===
[no output — silent no-op]
EXIT=0

=== TEST 3: --verbose ===
[sync_ops_scripts] in sync (sha=e5a029624b78...)
EXIT=0

=== TEST 4: induce drift ===
ORIG_MIRROR_SHA=e5a02962...
DRIFTED_MIRROR_SHA=645a92f6...
DRIFT_INDUCED_OK

=== TEST 5: run sync ===
[sync_ops_scripts] drift detected — canonical=e5a029624b78... mirror=645a92f692f1... — syncing
[sync_ops_scripts] synced canonical → mirror (sha=e5a029624b78..., +x preserved)
EXIT=0

=== TEST 6: post-state SHAs ===
e5a029624b7812fc06d2602e03d4e2bc25c3fdab34010b4f1b765db6947df64d  canonical
e5a029624b7812fc06d2602e03d4e2bc25c3fdab34010b4f1b765db6947df64d  mirror
SYNC_RESTORED_OK

=== TEST 7: executable bit preserved ===
-rwxr-xr-x@ ... daily_backup.sh
MIRROR_EXECUTABLE_OK

=== TEST 8: drift marker removed ===
DRIFT_MARKER_REMOVED_OK

=== TEST 9: invoke post-commit hook from worktree (sync script absent on branch) ===
[post-commit] WARN: <worktree>/Production/scripts/sync_ops_scripts.sh missing or not executable; skipping ops-script sync
EXIT=0   ← never aborts caller

=== TEST 10: hook on branch without sync script — drift unchanged (graceful skip) ===
HOOK_FAILED_TO_SYNC ← intentional: hook can't sync if script not on branch; warns instead

=== TEST 11: invoke post-commit hook from main repo (branch with sync script) ===
[sync_ops_scripts] drift detected — canonical=e5a029624b78... mirror=6aa16e248d3f... — syncing
[sync_ops_scripts] synced canonical → mirror (sha=e5a029624b78..., +x preserved)
EXIT=0
HOOK_SYNC_OK
```

11/11 expected outcomes observed.

### Caveat surfaced for Kim

The post-commit hook lives in the shared `.git/hooks/` and fires after every commit on every worktree. On worktree branches that **do not contain** `Production/scripts/sync_ops_scripts.sh` (e.g., the current `claude/gallant-bouman-804b4f` worktree which is on a different feature branch), the hook will emit a one-line `WARN: ... missing or not executable` to stderr after each commit. This is intentional graceful degradation — the hook never aborts the commit. Once `Production/scripts/sync_ops_scripts.sh` lands on `main`, every branch derived from main will pick it up and the warning stops. [CONFIRMED]

### Self-classification

**STANDARD.** Real script + hook + 11 tests + caveat surfacing.

---

## Task 2 — LD SUPABASE_DB_USER_DIRECT_OPTION_B_V1 (TRIVIAL)

### POST response

```json
{
  "data": {
    "id": 590,
    "decision_key": "SUPABASE_DB_USER_DIRECT_OPTION_B_V1",
    "decision_name": "Daily backup uses new SUPABASE_DB_USER_DIRECT key (Option B); pooler-form SUPABASE_DB_USER preserved for other consumers",
    "severity": "HARD",
    "scope_domain": "infra",
    "task_category": "tech_stack",
    "enforcement_type": "code_invariant",
    "date_locked": "2026-05-08",
    "supersedable": true,
    "is_current": true,
    "status": "active",
    "schema_version": 2
  }
}
```

### Read-back (Rule 35)

```json
{
  "data": {
    "id": 590,
    "decision_key": "SUPABASE_DB_USER_DIRECT_OPTION_B_V1",
    "severity": "HARD",
    "scope_domain": "infra",
    "task_category": "tech_stack",
    "enforcement_type": "code_invariant",
    "date_locked": "2026-05-08",
    "supersedable": true,
    "is_current": true,
    "status": "active"
  }
}
```

### Notes

- `source_document` field is NOT NULL (not surfaced in original prompt); set to `Production/scripts/daily_backup.sh + Production/docs/BACKUP_CHAIN_HARDENING_FOLLOWUPS_REPORT_20260508.md`. [INFERRED — required by schema, not by prompt]
- `decision_text` includes the full multi-paragraph context per spec (mismatch / diagnostic / Option B rationale / affected scripts / Doppler keys added / preserved consumers / commit reference / related blocker / invariant). [CONFIRMED]
- `related_files` populated with the 5 affected paths.
- `keyword_synonyms` populated for governance-drift discovery.
- Schema_version=2 default applied. `is_current=true`, `status=active`. [CONFIRMED]

### Self-classification

**TRIVIAL.** Single Directus POST with read-back.

---

## Task 3 — Pooler endpoint region lookup (STANDARD)

### Probe results — `aws-0-${region}` prefix (per spec)

| Region | Host | Result |
|---|---|---|
| us-east-1 | aws-0-us-east-1.pooler.supabase.com | `FATAL: Tenant or user not found` |
| us-east-2 | aws-0-us-east-2.pooler.supabase.com | `FATAL: Tenant or user not found` |
| us-west-1 | aws-0-us-west-1.pooler.supabase.com | `FATAL: Tenant or user not found` |
| us-west-2 | aws-0-us-west-2.pooler.supabase.com | `FATAL: (ENOTFOUND) tenant/user postgres.ugjpauwozlruyctrygby not found` |

Verbatim:

```
psql: error: connection to server at "aws-0-us-east-1.pooler.supabase.com" (44.216.29.125), port 6543 failed: FATAL:  Tenant or user not found
psql: error: connection to server at "aws-0-us-east-2.pooler.supabase.com" (13.59.95.192), port 6543 failed: FATAL:  Tenant or user not found
psql: error: connection to server at "aws-0-us-west-1.pooler.supabase.com" (54.177.55.191), port 6543 failed: FATAL:  Tenant or user not found
psql: error: connection to server at "aws-0-us-west-2.pooler.supabase.com" (44.238.118.41), port 6543 failed: FATAL:  (ENOTFOUND) tenant/user postgres.ugjpauwozlruyctrygby not found
```

All 4 `aws-0` regions failed — Supabase appears to have migrated this project's tenant routing off the legacy `aws-0` prefix. [CONFIRMED]

### Probe results — `aws-1-${region}` prefix (extended search)

| Region | Host | Result |
|---|---|---|
| **us-east-1** | **aws-1-us-east-1.pooler.supabase.com** | **SUCCESS** — `current_user=postgres`, PostgreSQL 17.6 |
| us-east-2 | aws-1-us-east-2.pooler.supabase.com | `FATAL: Tenant or user not found` |
| us-west-1 | aws-1-us-west-1.pooler.supabase.com | `FATAL: Tenant or user not found` |
| us-west-2 | aws-1-us-west-2.pooler.supabase.com | `FATAL: (ENOTFOUND) tenant/user postgres.ugjpauwozlruyctrygby not found` |

Verbatim success:

```
=== CONFIRMING: aws-1-us-east-1.pooler.supabase.com (us-east-1) ===
 current_user | current_database |                                      version
--------------+------------------+------------------------------------------------------------------------------------
 postgres     | postgres         | PostgreSQL 17.6 on aarch64-unknown-linux-gnu, compiled by gcc (GCC) 15.2.0, 64-bit
(1 row)

=== Also test transaction-mode port 5432 same host ===
 current_user
--------------
 postgres
```

Both ports 5432 (transaction mode) and 6543 (session mode) authenticate cleanly. Note: pooler auth showed `current_user=postgres` rather than `postgres.ugjpauwozlruyctrygby` — the pooler internally maps the namespaced user to the underlying role. [CONFIRMED]

### HALT-check (per spec rule)

> "HALT if any pooler region returns auth-success but Doppler password rejects (would indicate pooler has separate creds — surface for Kim)"

**No halt triggered.** The single auth-success (aws-1-us-east-1) used the same `SUPABASE_DB_PASSWORD` from Doppler that the direct-host `daily_backup.sh` uses successfully. Pooler shares credentials with direct host, as expected. [CONFIRMED]

### Doppler write

```
Doppler Error: Could not find requested secret: SUPABASE_POOLER_HOST   ← pre-state (key did not exist)

doppler secrets set SUPABASE_POOLER_HOST="aws-1-us-east-1.pooler.supabase.com" --project mindfulnest --config dev
┌──────────────────────┬────────────────────────────┬──────┐
│ NAME                 │ VALUE                      │ NOTE │
├──────────────────────┼────────────────────────────┼──────┤
│ SUPABASE_POOLER_HOST │ aws-1-us-east-1.pooler.sup │      │
│                      │ abase.com                  │      │
└──────────────────────┴────────────────────────────┴──────┘

doppler secrets get SUPABASE_POOLER_HOST --project mindfulnest --config dev --plain
aws-1-us-east-1.pooler.supabase.com   ← read-back confirms
```

### API_KEYS_MASTER.md update

New row inserted after the existing Supabase rows (line 67):

| Service | Credential | Value | Notes |
|---|---|---|---|
| **Supabase** | Pooler Host | `aws-1-us-east-1.pooler.supabase.com` | Verified 2026-05-08 via psql probe (LD `SUPABASE_DB_USER_DIRECT_OPTION_B_V1` follow-up). Ports: 5432 (transaction-mode), 6543 (session-mode). Use with pooler-form user `postgres.ugjpauwozlruyctrygby`. Doppler key: `SUPABASE_POOLER_HOST`. Note: legacy `aws-0-us-east-1.pooler.supabase.com` returns "Tenant or user not found" — Supabase migrated tenants off the aws-0 prefix. No script currently uses pooler; this is informational/recovery. |

`API_KEYS_MASTER.md` is gitignored (confirmed via `git check-ignore -v`); change does not appear in `git status`. [CONFIRMED]

### Self-classification

**STANDARD.** 8 hosts probed, prefix migration discovered, Doppler write, doc update.

---

## Task 4 — prod_blockers row for historical backup gap (TRIVIAL)

### POST response

```json
{
  "data": {
    "id": 100,
    "module_id": null,
    "severity": "medium",
    "title": "Audit historical backup gap — daily Supabase backup was broken for >=22 days before 2026-05-08 fix",
    "description": "First successful daily-backup ever in ~/MindfulNestBackups/directus/ was 2026-05-08T16:59 (commit d05dfe0 — daily_backup.sh fix swapping SUPABASE_DB_USER->SUPABASE_DB_USER_DIRECT, plus SUPABASE_DB_NAME and SUPABASE_DB_PORT additions). Directory existed prior with zero successful .sql.gz files. Auth gap (Doppler held mismatched direct-host db.<ref>.supabase.co + pooler-form-user postgres.<ref> combo) pre-dated this session. Worth a one-time audit: when was last known-good backup taken? Are there earlier backup directories or external backup destinations? If gap is genuinely 22+ days, surface as a recovery-readiness concern. Session reference: feature/ld227-doppler-phase1-20260508 branch, commit d05dfe0.",
    "is_resolved": false,
    "created_at": "2026-05-08T17:50:21.371Z",
    "resolved_at": null
  }
}
```

### Read-back (Rule 35)

Verified — `id=100` returns identical data via `GET /items/prod_blockers/100`.

### Self-classification

**TRIVIAL.** Single Directus POST with read-back.

---

## Activity log

| Field | Value |
|---|---|
| `id` | 1787 |
| `action` | `backup_chain_hardening_followups_executed` |
| `performed_by` | `claude` |
| `created_at` | `2026-05-08T17:55:43.792Z` |
| `details` | Full task-by-task summary (see Directus row) |

Read-back confirmed via `GET /items/prod_activity_log/1787`.

---

## Confidence tags (Rule 24)

| Claim | Tag |
|---|---|
| Both daily_backup.sh copies SHA-equal at `e5a02962...` | [CONFIRMED via shasum] |
| Canonical SHA differs from prompt's stated `1d4c1a1a` | [CONFIRMED — prompt was stale; actual file SHA is e5a02962] |
| Pooler at `aws-1-us-east-1.pooler.supabase.com` is the correct host | [CONFIRMED via psql SELECT 1 success on both ports 5432+6543] |
| Pooler user identity returns `postgres` not `postgres.ugjpauwozlruyctrygby` | [CONFIRMED via SELECT current_user] |
| `aws-0` prefix universally fails for this project | [CONFIRMED across 4 regions] |
| Pooler shares credentials with direct host | [CONFIRMED — same Doppler `SUPABASE_DB_PASSWORD` works for both] |
| post-commit hook fires for all worktrees from shared `.git/common-dir/hooks/` | [CONFIRMED — git documented behavior + verified `git rev-parse --git-common-dir`] |
| Hook gracefully no-ops when sync script absent on branch | [CONFIRMED via TEST 9+10] |
| Hook successfully syncs when run on branch with script | [CONFIRMED via TEST 11] |
| LD-590 / blocker-100 / activity-1787 all readback verified | [CONFIRMED via GET requests] |
| Historical gap is "22+ days" | [INFERRED — prompt's framing; not independently verified by enumerating prior backup attempts] |
| Supabase migrated tenants off aws-0 prefix | [INFERRED — based on pattern of failures; root cause not confirmed with Supabase support] |

---

## Self-classification per task (per spec)

| Task | Classification | Why |
|---|---|---|
| 4 (prod_blocker row) | TRIVIAL | Single POST, mechanical |
| 2 (LD registration) | TRIVIAL | Single POST with prescribed payload, schema-tolerant |
| 3 (pooler lookup) | STANDARD | 8 host probes, migration prefix discovered, Doppler write, MD edit |
| 1 (sync mechanism) | STANDARD | Script + hook + 11 tests + DS-27 worktree caveat surfacing |

---

## Files touched / created (none committed)

| Path | Status | Notes |
|---|---|---|
| `Production/scripts/sync_ops_scripts.sh` | NEW | 3391 B, 755, syntax-checked, 11/11 tests passed |
| `.git/hooks/post-commit` | NEW | 1660 B, 755, syntax-checked, hook fires on every commit |
| `Production/API_KEYS_MASTER.md` | EDIT | Pooler Host row added (line 67); gitignored, no `git status` entry |
| `~/MindfulNestOps/scripts/daily_backup.sh` | UNCHANGED | Currently SHA-equal to canonical |
| Doppler `mindfulnest/dev` | EDIT | `SUPABASE_POOLER_HOST=aws-1-us-east-1.pooler.supabase.com` added |

Directus rows created:
- `prod_blockers` id=100
- `prod_locked_decisions` id=590
- `prod_activity_log` id=1787

No git commits made (per explicit instruction). All artifacts staged for Kim review.

---

## Recommended Kim followups

1. Review `Production/scripts/sync_ops_scripts.sh` and `.git/hooks/post-commit`; commit when ready (sync script will land on whichever branch it's committed on; hook is global).
2. Resolve the historical-backup-gap audit (`prod_blockers id=100`) by enumerating any pre-2026-05-08 backup destinations.
3. Decide if `weekly_preflight_audit.py` and `credential_store.py` should adopt the new `SUPABASE_POOLER_HOST` Doppler key (currently they hardcode pooler hostname assumptions; LD-590 invariant is satisfied as-is, this is just a centralization opportunity).
