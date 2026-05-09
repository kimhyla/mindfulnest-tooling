# CloudStorage → MindfulNestOps Move Report

**Date:** 2026-05-08
**Session:** gallant-bouman-804b4f (continuation of G5 backup-FDA fix)
**Author:** Claude (autonomous worktree agent)
**Self-classification:** STANDARD — file move + plist edit + launchd reload. No behavioral change beyond execution location.
**Authority:** Steps 1–7 autonomous-doable; Step 8 (this report) autonomous.

---

## 1. Executive summary

**Outcome: (a) SUCCESS — TCC layer eliminated for both backup launchd jobs.** Both jobs now spawn from `~/MindfulNestOps/scripts/`, a non-CloudStorage path with no TCC gates. Live launchctl-start trigger produced:

- **Daily backup:** progressed past TCC; failed only on missing `SUPABASE_DB_*` env vars (downstream LD-227 G3/G4 issue, **out of scope**).
- **Weekly snapshot:** progressed past TCC; **fully ran the Python script**; pulled 561 locked decisions, 207 preflight reviews, 343 blockers, 2 app stages, 379 activity log rows from Directus; **wrote 2.4 MB of JSON snapshot files** to `~/MindfulNestBackups/governance-snapshot-repo/2026-05-08/`; failed only at `git commit` due to unset `git config --global user.email` (downstream, **out of scope**).

This is the first time ANY backup data has been written to disk by these jobs since they were registered 2026-04-17.

The G5 report's recommendation in §7 (move out of CloudStorage entirely) is now executed. Originals remain in CloudStorage as rollback (per Hard rules).

---

## 2. Verbatim before-state

### 2.1 com.mindfulnest.daily-backup.plist (BEFORE)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mindfulnest.daily-backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/daily_backup.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>15</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.out.log</string>
  <key>StandardErrorPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

### 2.2 com.mindfulnest.weekly-snapshot.plist (BEFORE)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mindfulnest.weekly-snapshot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/_weekly_snapshot_wrapper.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>4</integer>
    <key>Minute</key><integer>0</integer>
    <key>Weekday</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.out.log</string>
  <key>StandardErrorPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

### 2.3 daily_backup.sh (UNCHANGED — copied byte-identical)
- Source: `Production/scripts/daily_backup.sh` (2573 bytes, mtime 2026-04-17 21:55)
- All paths inside the script are absolute (`${HOME}/MindfulNestBackups/...`) or runtime-resolved (PATH-lookups for `pg_dump`, `doppler`)
- No `cd` calls. No relative paths. No sibling references. **Safe to relocate without edits.**

### 2.4 _weekly_snapshot_wrapper.sh (UNCHANGED — copied byte-identical)
- Source: `Production/scripts/_weekly_snapshot_wrapper.sh` (596 bytes, mtime 2026-05-08 01:35)
- The single `cd` line uses absolute `${HOME}/Library/CloudStorage/...` — resolves correctly regardless of the wrapper's own location.
- Then execs `/opt/homebrew/bin/doppler run -- /usr/bin/python3 Production/scripts/weekly_directus_snapshot.py` (the .py is read RELATIVE to the post-cd CloudStorage cwd). **Safe to relocate without edits.**

### 2.5 weekly_directus_snapshot.py (NOT MOVED — stays in CloudStorage)
**Reason:** the script does `_HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(_HERE.parent)); from lib.directus_admin_client import DirectusAdminClient`. `_HERE.parent` resolves to `Production/lib/` — a sibling of `scripts/`. Moving the .py to `~/MindfulNestOps/scripts/` would break the import (no sibling `lib/` directory). Since the wrapper already `cd`s to CloudStorage and `python3` is a non-CloudStorage executable that already has read access to CloudStorage from launchd context (proved by the smoke test below), leaving the .py in CloudStorage is correct.

---

## 3. Move plan executed

| File | Source | Destination | Action |
|---|---|---|---|
| `daily_backup.sh` | `Production/scripts/` (CloudStorage) | `~/MindfulNestOps/scripts/` | **Copy** (originals retained for rollback) |
| `_weekly_snapshot_wrapper.sh` | `Production/scripts/` (CloudStorage) | `~/MindfulNestOps/scripts/` | **Copy** (originals retained for rollback) |
| `weekly_directus_snapshot.py` | `Production/scripts/` (CloudStorage) | (NOT MOVED) | Stays in CloudStorage — `lib.directus_admin_client` sibling import |
| `com.mindfulnest.daily-backup.plist` | `~/Library/LaunchAgents/` | (same) | **Edit ProgramArguments** |
| `com.mindfulnest.weekly-snapshot.plist` | `~/Library/LaunchAgents/` | (same) | **Edit ProgramArguments** |

**Confidence:** HIGH — every action verified post-execution.

---

## 4. Verbatim after-state

### 4.1 com.mindfulnest.daily-backup.plist (AFTER)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mindfulnest.daily-backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/kimberlysmith/MindfulNestOps/scripts/daily_backup.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>15</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.out.log</string>
  <key>StandardErrorPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

`plutil -lint` → `OK`.

### 4.2 com.mindfulnest.weekly-snapshot.plist (AFTER)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.mindfulnest.weekly-snapshot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/kimberlysmith/MindfulNestOps/scripts/_weekly_snapshot_wrapper.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>4</integer>
    <key>Minute</key><integer>0</integer>
    <key>Weekday</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.out.log</string>
  <key>StandardErrorPath</key><string>/Users/kimberlysmith/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

`plutil -lint` → `OK`.

### 4.3 ~/MindfulNestOps/scripts/ tree
```
total 16
drwxr-xr-x@ 4 kimberlysmith  staff   128 May  8 01:36 .
drwxr-xr-x@ 3 kimberlysmith  staff    96 May  8 01:36 ..
-rwxr-xr-x@ 1 kimberlysmith  staff   596 May  8 01:36 _weekly_snapshot_wrapper.sh
-rwxr-xr-x@ 1 kimberlysmith  staff  2573 May  8 01:36 daily_backup.sh
```

`diff -u` against CloudStorage source → both files identical (verified by `DAILY_IDENTICAL` and `WRAPPER_IDENTICAL` markers).

---

## 5. Test outputs

### 5.1 Manual shell smoke (pre-launchd reload)

`bash /Users/kimberlysmith/MindfulNestOps/scripts/daily_backup.sh`:
```
exit=1
/Users/kimberlysmith/MindfulNestOps/scripts/daily_backup.sh: line 46: SUPABASE_DB_HOST: SUPABASE_DB_HOST not set (Doppler or env)
```

`bash /Users/kimberlysmith/MindfulNestOps/scripts/_weekly_snapshot_wrapper.sh`:
```
exit=1
Traceback (most recent call last):
  File "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_directus_snapshot.py", line 90, in <module>
    sys.exit(main())
  File "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_directus_snapshot.py", line 51, in ensure_repo
    run(["git", "commit", "-m", "init"], cwd=REPO_DIR)
RuntimeError: git commit -m init failed: Author identity unknown
```

**Reading the output:** zero TCC errors. Both scripts ran their interpreter past the OS gate. Exit 1 is from downstream (env vars, git config).

### 5.2 launchd reload + list
```
launchctl unload ~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist
launchctl unload ~/Library/LaunchAgents/com.mindfulnest.weekly-snapshot.plist
launchctl load ~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist
launchctl load ~/Library/LaunchAgents/com.mindfulnest.weekly-snapshot.plist

launchctl list | grep mindfulnest:
-	0	com.mindfulnest.daily-backup
-	0	com.mindfulnest.weekly-snapshot
-	2	com.mindfulnest.weekly-preflight-audit
```

Both jobs loaded; last-exit-status = 0 (no triggers since reload). The third row is the unrelated weekly-preflight-audit job (still failing per G5 §1; not in scope here).

### 5.3 Live launchd-start (TCC layer proof)

After truncating logs, ran:
```
launchctl start com.mindfulnest.daily-backup
launchctl start com.mindfulnest.weekly-snapshot
```

Waited 30 s. Inspected logs.

#### Daily backup err log:
```
/Users/kimberlysmith/MindfulNestOps/scripts/daily_backup.sh: line 46: SUPABASE_DB_HOST: SUPABASE_DB_HOST not set (Doppler or env)
```
**Decisive proof:** the err log now cites `/Users/kimberlysmith/MindfulNestOps/scripts/daily_backup.sh` (NOT the CloudStorage path), and there is **no `Operation not permitted`**. This is the first time daily-backup has emitted anything other than a TCC denial.

#### Weekly snapshot err log:
```
Traceback (most recent call last):
  File "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_directus_snapshot.py", line 90, in <module>
    sys.exit(main())
  File "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_directus_snapshot.py", line 82, in main
    run(["git", "commit", "-m", f"Weekly snapshot {today} — {summary}"], cwd=REPO_DIR)
RuntimeError: git commit -m Weekly snapshot 2026-05-08 — prod_locked_decisions=561, prod_preflight_reviews=207, app_blockers=343, prod_app_stages=2, app_activity_log=379 failed: Author identity unknown
```
**Decisive proof:** the Python script (in CloudStorage) was successfully READ and EXECUTED by launchd-spawned `/usr/bin/python3`. It opened a network connection to Directus, retrieved 1492 records across five collections, wrote five JSON files (2.4 MB), and only failed at the final `git commit` because `git config --global user.email` is not set.

### 5.4 Backup data on disk (FIRST TIME EVER)
```
/Users/kimberlysmith/MindfulNestBackups/governance-snapshot-repo/2026-05-08/:
  app_activity_log_last90d.json   252K
  app_blockers.json               260K
  prod_app_stages.json            4.0K
  prod_locked_decisions.json      1.1M
  prod_preflight_reviews.json     780K
```

**Confidence:** HIGH — files visible via `ls` and `du`; sizes consistent with the row counts in the commit message (561 LDs, 343 blockers, 207 preflight reviews, etc.).

---

## 6. Outcome classification

**Outcome: (a) SUCCESS — backups now run from outside CloudStorage.** Per §7, two non-TCC follow-up errors persist (env vars, git config); both are recognized as out-of-scope per mission spec.

| Layer | Status |
|---|---|
| TCC `Operation not permitted` from CloudStorage | **RESOLVED** — eliminated by file move |
| launchd job loads | **RESOLVED** — both load with exit 0 |
| Manual `bash` smoke | **RESOLVED** — runs past TCC |
| launchd-spawned bash | **RESOLVED** — runs past TCC |
| launchd-spawned python3 (reads CloudStorage .py) | **RESOLVED** — reads + executes, performs Directus pull, writes 2.4 MB to disk |
| `pg_dump` env vars (`SUPABASE_DB_HOST` etc.) | **OUT OF SCOPE** (LD-227 G3/G4) |
| `git config --global user.email` for snapshot repo | **OUT OF SCOPE** (new finding — surfaced in §9) |

---

## 7. Rollback procedure

If anything regresses, revert in this order:

1. Edit `~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist` line 8: replace `/Users/kimberlysmith/MindfulNestOps/scripts/daily_backup.sh` with `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/daily_backup.sh`.
2. Edit `~/Library/LaunchAgents/com.mindfulnest.weekly-snapshot.plist` line 8: replace `/Users/kimberlysmith/MindfulNestOps/scripts/_weekly_snapshot_wrapper.sh` with `/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/_weekly_snapshot_wrapper.sh`.
3. Run `plutil -lint` on both plists to verify validity.
4. `launchctl unload` then `launchctl load` both plists.
5. Originals at `Production/scripts/daily_backup.sh` and `Production/scripts/_weekly_snapshot_wrapper.sh` are unchanged and ready to receive launchd traffic.
6. Optionally `rm -rf ~/MindfulNestOps/` once rollback is confirmed clean.

The Python script `weekly_directus_snapshot.py` was never moved — no rollback step needed there.

---

## 8. Confidence tags (per Rule 24)

| Claim | Confidence | Evidence |
|---|---|---|
| TCC layer eliminated for both jobs | **HIGH** | err logs no longer cite `Operation not permitted`; cite new `~/MindfulNestOps/...` path |
| Daily backup blocked only on env vars | **HIGH** | err log line 1: `SUPABASE_DB_HOST: SUPABASE_DB_HOST not set (Doppler or env)` |
| Weekly snapshot pulled live data | **HIGH** | 2.4 MB JSON on disk + commit message containing per-collection row counts |
| Plists are well-formed | **HIGH** | `plutil -lint` returned `OK` on both |
| `weekly_directus_snapshot.py` should NOT move | **HIGH** | sibling-import `lib.directus_admin_client` via `_HERE.parent` — verified by reading lines 28–30 of the .py |
| Originals in CloudStorage are untouched | **HIGH** | only `cp` (not `mv`) used; `diff -u` confirmed identical |
| `git commit` env-var failure is out-of-scope | **MEDIUM-HIGH** | not listed in mission Hard rules but logically downstream of TCC fix; trivial 2-line fix |
| `git init` empty repo created during smoke is harmless | **HIGH** | `weekly_directus_snapshot.py` lines 45–51 guard with `if not REPO_DIR.exists()`; subsequent runs idempotent |

---

## 9. Out-of-scope items surfaced

1. **`SUPABASE_DB_HOST` / `SUPABASE_DB_USER` / `SUPABASE_DB_PASSWORD` env vars not set.** Daily backup will not produce a `pg_dump` until these are sourced from Doppler (per LD-227 G3/G4) OR set via `EnvironmentVariables` in the daily-backup plist OR sourced from a wrapper that does `doppler run --` (analogous to the weekly wrapper). This is the next layer of work and was already identified in the mission spec as out of scope.

2. **`pg_dump` not on default PATH.** `which pg_dump` returns nothing in default shell; `daily_backup.sh` will need either `brew link --force libpq` (per the script's own header comment) or an explicit `/opt/homebrew/opt/libpq/bin/pg_dump` in the script.

3. **`git config --global user.email` not set.** Weekly snapshot's `git commit` step fails on a fresh shell. NEW finding from this session — was not visible in G5 because the script never reached the `git commit` step before. Trivial 2-command fix:
   ```
   git config --global user.email "kim@mindfulnest.dev"   # or whatever Kim prefers
   git config --global user.name  "Kim Smith"
   ```

4. **`weekly_preflight_audit.py` (third launchd job)** is still failing per G5 §1. NOT touched per mission spec. Its move requires deeper dependency analysis because it reads governance/* files THROUGHOUT the CloudStorage tree by design. Recommend separate session.

5. **Doppler `DOPPLER_PROJECT` env var not exported in default shell.** `daily_backup.sh` line 42 guards with `[ -n "${DOPPLER_PROJECT:-}" ]` so the doppler block silently skips without it. Either set globally, set in the plist, or wrap daily_backup.sh in `doppler run --` (consistent with the weekly wrapper pattern).

---

## 10. Summary

The infrastructural durability fix is in place. Both backup launchd jobs now spawn from a non-CloudStorage path (`~/MindfulNestOps/scripts/`) and have proven they can execute past macOS's TCC layer — the blocker that prevented every single one of the ~20 attempts since 2026-04-18. The weekly snapshot has produced its first-ever JSON dataset on disk. The daily backup is blocked only on `pg_dump` env vars (a separate, well-scoped LD-227 issue).

Originals remain in CloudStorage and the rollback path is documented. Plists pass `plutil -lint`. No production code in `Production/scripts/` was modified.
