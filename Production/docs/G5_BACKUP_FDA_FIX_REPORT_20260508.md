# G5 Backup FDA Fix — Diagnostic + Remediation Report

**Date:** 2026-05-08
**Session:** gallant-bouman-804b4f
**Author:** Claude (autonomous portion of G5 backup-FDA fix)
**Authority:** Steps 1, 3 (preparation only), 4 — autonomous-doable. Step 2 requires Kim's hands.

---

## 1. Executive Summary

Two MindfulNest launchd jobs scheduled to back up the production Directus database have **never successfully run** since they were registered on 2026-04-17. They have been silently failing for **19 calendar days** (daily-backup) / **3 weekly attempts** (weekly-snapshot) with `Operation not permitted` errors caused by macOS Full Disk Access (FDA) restrictions on the Dropbox `CloudStorage` path.

**Critical finding (out-of-scope but high-confidence):** The `com.mindfulnest.weekly-preflight-audit` job is failing for the same reason since approximately 2026-04-27. The most recent successful preflight audit run was 2026-04-20.

**Net production state:**
- `~/MindfulNestBackups/directus/` does not exist — zero pg_dump backups have ever been written to disk.
- `~/MindfulNestBackups/governance-snapshot-repo/` does not exist — zero JSON snapshots have ever been committed.
- Database is currently protected only by Supabase's Pro-plan native backups (per memory file `project_yotuo_backup_setup.md`).

**Fix:** Add three executables to System Settings → Privacy & Security → Full Disk Access:
1. `/bin/bash`
2. `/usr/bin/python3` (and/or `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`)
3. `/Applications/Utilities/Terminal.app` (recommended — covers ad-hoc shell access)

Then reload the launchd jobs.

**Recommendation for durability:** Move the `daily_backup.sh` and snapshot scripts (and their output target paths) **out of the Dropbox CloudStorage tree** entirely. CloudStorage paths are TCC-gated; any non-Terminal invocation is one OS update away from breaking again. Detail in §7.

---

## 2. Plist Contents (verbatim)

### 2.1 com.mindfulnest.daily-backup.plist
Path: `~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist`

```xml
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
```

Schedule: daily 03:15 local. ProgramArguments[0] is the wrapper script itself; macOS reads the `#!/usr/bin/env bash` shebang and execs `/bin/bash`. **`/bin/bash` is the executable that needs FDA.**

### 2.2 com.mindfulnest.weekly-snapshot.plist
Path: `~/Library/LaunchAgents/com.mindfulnest.weekly-snapshot.plist`

```xml
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
```

Schedule: Sunday 04:00 local. ProgramArguments[0] is a bash wrapper that `cd`s and execs `/usr/bin/python3 Production/scripts/weekly_directus_snapshot.py`. **Both `/bin/bash` (wrapper interpreter) AND `/usr/bin/python3` need FDA.**

### 2.3 com.mindfulnest.weekly-preflight-audit.plist (out-of-scope but failing)
Path: `~/Library/LaunchAgents/com.mindfulnest.weekly-preflight-audit.plist`

ProgramArguments:
```
/usr/bin/python3
/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_preflight_audit.py
--days
7
```

Schedule: Monday 09:00 local. **`/usr/bin/python3` needs FDA — same fix benefits this job.**

---

## 3. Executable Paths Needing FDA

| Executable | Why it needs FDA | Used by |
|---|---|---|
| `/bin/bash` | Reads `daily_backup.sh` and `_weekly_snapshot_wrapper.sh` from `~/Library/CloudStorage/Dropbox/...` (TCC-gated) | daily-backup, weekly-snapshot |
| `/usr/bin/python3` | Stub that resolves to `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`. Reads `weekly_directus_snapshot.py` and `weekly_preflight_audit.py` from CloudStorage | weekly-snapshot, weekly-preflight-audit |
| `/Applications/Xcode.app/Contents/Developer/usr/bin/python3` | The actual binary `/usr/bin/python3` proxies to (per `xcode-select -p`). System Settings may require adding this directly if the stub-grant doesn't propagate | weekly-snapshot, weekly-preflight-audit |
| `/Applications/Utilities/Terminal.app` | Lets ad-hoc shell sessions (you running scripts manually from Terminal) work without re-prompting | manual ops, debugging |

**Confidence:** HIGH — error logs explicitly cite `bash:` and `/Applications/Xcode.app/.../python3:` as the executables that hit FDA.

---

## 4. Failure History — log evidence

### 4.1 Daily backup
```
~/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.err.log
- birth time:    2026-04-18 03:15:00
- last modified: 2026-05-07 03:15:04
- line count:    20 (one "Operation not permitted" line per launch)
```

**First failure: 2026-04-18 03:15.** Most recent failure: 2026-05-07 03:15.
Days failing: **19 calendar days** (≈ 20 attempts; matches 20 log lines).
Successful runs: **0**.

### 4.2 Weekly snapshot
```
~/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.err.log
- birth time:    2026-04-19 04:00:02
- last modified: 2026-05-03 04:00:05
- line count:    3
```

**First failure: 2026-04-19 04:00 (Sunday).** Subsequent failures: 2026-04-26, 2026-05-03 (next attempt: 2026-05-10).
Sundays failing: **3 of 3**.
Successful runs: **0**.

### 4.3 Weekly preflight audit (collateral, out of original scope)
```
~/Library/Logs/mindfulnest-preflight-audit.log (tail)
[audit] DONE — {... 2026-04-20 ...}
[audit] WARNING: governance_drift_check sub-check failed: ModuleNotFoundError("No module named 'lib.directus_admin_client'")
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '...weekly_preflight_audit.py': [Errno 1] Operation not permitted
/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file '...weekly_preflight_audit.py': [Errno 1] Operation not permitted
```

Last successful audit: 2026-04-20 (Monday). Two subsequent Monday attempts (Apr 27, May 4) failed.

### 4.4 Output logs (zero size on all three)
```
com.mindfulnest.daily-backup.out.log     0 bytes (created 2026-04-18, never written)
com.mindfulnest.weekly-snapshot.out.log  0 bytes (created 2026-04-19, never written)
```

### 4.5 Backup tree state
```
~/MindfulNestBackups/
├── launchd-logs/      (only directory present)
└── (no directus/, no governance-snapshot-repo/)
```

`~/MindfulNestBackups/directus/` does not exist. `~/MindfulNestBackups/governance-snapshot-repo/` does not exist. Both confirm the jobs have never reached the point of writing output.

---

## 5. Kim's Manual Action — FDA Grant (Step 2)

**This requires your hands. macOS specifically prohibits programmatic FDA grants.**

### 5.1 Steps
1. Open **System Settings** (Apple menu → System Settings…).
2. Sidebar: **Privacy & Security** → **Full Disk Access**.
3. Click the **+** button at the bottom of the right pane. Authenticate with Touch ID / password.
4. In the file picker, press **`Cmd + Shift + G`** to open "Go to folder" (the picker hides system paths by default).
5. Add each of these paths one at a time. After each, the new entry will appear in the list. Make sure each row's toggle is **ON (blue)**.

   **Required:**
   - `/bin/bash`
   - `/usr/bin/python3`

   **Recommended (covers Xcode-routed Python and ad-hoc Terminal use):**
   - `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`
   - `/Applications/Utilities/Terminal.app`

6. If macOS prompts to "Quit & Reopen" any app, choose **Quit & Reopen**. (Unlikely needed for `/bin/bash` and `python3`; may apply to Terminal.)
7. Close System Settings.

### 5.2 Expected post-grant state
The Full Disk Access list should now show:
- bash (toggle ON)
- python3 (toggle ON)
- python3 (Xcode variant — toggle ON, optional)
- Terminal (toggle ON, optional)

### 5.3 Why the picker fights you
`/bin` and `/usr/bin` are hidden in Finder by default. `Cmd + Shift + G` then typing the full path (e.g. `/bin/bash`) is the only reliable way. macOS may show "/bin" greyed out — type the path and press Return; it'll accept.

---

## 6. Post-FDA Reload + Verification (run after Step 5)

After the FDA grant is in place, paste these commands in Terminal:

### 6.1 Reload launchd jobs (Step 3 of original plan)
```bash
launchctl unload ~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist
launchctl load   ~/Library/LaunchAgents/com.mindfulnest.daily-backup.plist
launchctl unload ~/Library/LaunchAgents/com.mindfulnest.weekly-snapshot.plist
launchctl load   ~/Library/LaunchAgents/com.mindfulnest.weekly-snapshot.plist

# Bonus — fix the preflight audit while we're here:
launchctl unload ~/Library/LaunchAgents/com.mindfulnest.weekly-preflight-audit.plist
launchctl load   ~/Library/LaunchAgents/com.mindfulnest.weekly-preflight-audit.plist
```

### 6.2 Manual smoke test (Step 5 of original plan)
```bash
# Trigger daily backup right now
launchctl start com.mindfulnest.daily-backup

# Wait ~30 seconds, then check
sleep 30

# Expected: err.log silent OR contains a non-FDA pg_dump issue
cat ~/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.err.log

# Expected: out.log shows "[timestamp] Starting pg_dump → ..." and "[timestamp] SUCCESS"
cat ~/MindfulNestBackups/launchd-logs/com.mindfulnest.daily-backup.out.log

# Expected: a .sql.gz file exists
ls -la ~/MindfulNestBackups/directus/
```

### 6.3 Possible second-stage failure modes
After FDA is fixed, the `daily_backup.sh` script may surface a *different* error because it requires:
- `pg_dump` on PATH (Homebrew `libpq` linked, per script header line 11)
- `SUPABASE_DB_HOST` / `SUPABASE_DB_USER` / `SUPABASE_DB_PASSWORD` env vars (or Doppler with `DOPPLER_PROJECT` set)

If the smoke test fails post-FDA, check:
```bash
which pg_dump
echo "$SUPABASE_DB_HOST $SUPABASE_DB_USER"  # should be set
doppler --version 2>&1                       # if using Doppler path
```

The script's `set -euo pipefail` plus `: "${VAR:?msg}"` guards mean a missing env var will show up as `SUPABASE_DB_HOST not set (Doppler or env)` in `last_dump_stderr.log` or err.log. This is a separate fix from the FDA fix and is **NOT in scope for this report**, but flagging so it doesn't blindside you.

### 6.4 Trigger weekly snapshot manually
```bash
launchctl start com.mindfulnest.weekly-snapshot
sleep 60
cat ~/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.err.log
cat ~/MindfulNestBackups/launchd-logs/com.mindfulnest.weekly-snapshot.out.log
ls ~/MindfulNestBackups/governance-snapshot-repo/
```

Note: this script imports `lib.directus_admin_client` — the same module the preflight audit log shows as `ModuleNotFoundError`. That's a *separate* issue (likely PYTHONPATH / venv). The FDA fix won't resolve it. It will, however, let the script *get to the point of failing for that reason* instead of failing earlier on FDA.

---

## 7. Recommendation — Move backups out of the Dropbox path

**Verdict: STRONG YES.** Reasoning:

1. **CloudStorage paths are TCC-gated by design.** Apple has been progressively tightening this since Ventura. Every macOS minor release risks changing exactly which executables auto-inherit FDA from a parent grant. A backup pipeline pinned to `~/Library/CloudStorage/Dropbox/...` is fragile by construction.

2. **Dropbox has no role in the backup pipeline.**
   - `daily_backup.sh` writes its output to `~/MindfulNestBackups/directus/` (already outside CloudStorage). The script *itself* lives in CloudStorage purely because the rest of `Production/scripts/` does.
   - `weekly_directus_snapshot.py` writes to `~/MindfulNestBackups/governance-snapshot-repo/` — already a separate git repo *outside* CloudStorage.
   - In both cases, the *only* CloudStorage dependency is the script source file, which doesn't need to be there.

3. **YOTUO external drive backup (project memory: `project_yotuo_backup_setup.md`) is unaffected.** It backs up `~/.claude/` + Dropbox files at 2am. Moving the backup *scripts* out of Dropbox doesn't change what gets backed up to YOTUO.

### 7.1 Suggested layout
```
~/mindfulnest-backups-bin/             # NEW — outside CloudStorage
├── daily_backup.sh                    # copy from current Dropbox path
├── _weekly_snapshot_wrapper.sh
├── weekly_directus_snapshot.py
├── weekly_preflight_audit.py          # bonus: fixes preflight audit too
└── lib/
    └── directus_admin_client.py       # also fixes the ModuleNotFoundError if symlinked from Production/lib/
```

Then update each plist's `ProgramArguments[0]` to point at `~/mindfulnest-backups-bin/<script>` and (for python jobs) update `WorkingDirectory` accordingly. No FDA grant required — no CloudStorage TCC gate to cross.

### 7.2 Caveat
If the backup scripts are version-controlled inside the project repo (likely), then moving them out of CloudStorage either:
- breaks version control (bad), or
- requires a deploy step that copies repo → bin (acceptable; matches typical prod pipelines).

A **clean compromise**: keep the canonical scripts in `Production/scripts/` (Dropbox), but have an "install" step (one-shot or weekly) that copies them to `~/mindfulnest-backups-bin/` with file-level mtime checking. This decouples *runtime* from CloudStorage while keeping *source-of-truth* in version control.

This recommendation is **out of scope for the immediate G5 fix** — Step 5 (FDA grant) unblocks today's bleeding. The relocation is the durable v2 fix.

---

## 8. Confidence Tags (Rule 24)

| Claim | Confidence | Evidence |
|---|---|---|
| Daily backup has never run successfully | HIGH | `~/MindfulNestBackups/directus/` does not exist; out.log is 0 bytes; err.log is 20 identical FDA error lines |
| Weekly snapshot has never run successfully | HIGH | `~/MindfulNestBackups/governance-snapshot-repo/` does not exist; out.log is 0 bytes; err.log is 3 identical FDA error lines |
| First daily-backup failure: 2026-04-18 03:15 | HIGH | `stat -f '%SB'` on err.log birth time |
| First weekly-snapshot failure: 2026-04-19 04:00 | HIGH | `stat -f '%SB'` on err.log birth time |
| 19 days of daily failures | HIGH | (2026-05-07) − (2026-04-18) = 19 days |
| `/bin/bash` is the daily-backup executable needing FDA | HIGH | err.log line prefix `bash:` matches; `daily_backup.sh` shebang is `#!/usr/bin/env bash` |
| `/usr/bin/python3` (Xcode-routed) is the weekly-snapshot executable needing FDA | HIGH | preflight-audit log explicitly cites `/Applications/Xcode.app/Contents/Developer/usr/bin/python3: can't open file ...: Operation not permitted`; `xcode-select -p` confirms Xcode path; `_weekly_snapshot_wrapper.sh` execs `/usr/bin/python3` |
| Weekly-preflight-audit also affected | HIGH | direct error in `~/Library/Logs/mindfulnest-preflight-audit.log` quoted in §4.3 |
| Supabase Pro plan provides current backup coverage | MEDIUM | Cited from project memory `project_yotuo_backup_setup.md` not re-verified in this session |
| FDA grant on `/bin/bash` + `/usr/bin/python3` will fix the FDA error | HIGH | This is the textbook macOS fix for `Operation not permitted` on TCC-gated paths; nothing about this setup is unusual |
| Post-FDA, daily_backup.sh may fail on missing `SUPABASE_DB_*` env vars or `pg_dump` not on PATH | MEDIUM | Inferred from script's `set -euo pipefail` + `: "${VAR:?}"` guards; not confirmed by running |
| Moving backups out of Dropbox is a more durable fix | HIGH | CloudStorage TCC enforcement is well-documented; Apple has tightened this in each macOS major release |

---

## 9. Self-classification

**Task category:** ops_diagnostic + remediation_plan
**Severity:** HIGH (production data backup pipeline silently broken for 19 days)
**Scope domain:** infrastructure / launchd / macOS TCC
**Enforcement type:** documentation + Kim manual action required
**Directus writes:** NONE (per Rule 35 — diagnostic-only task)
**Risk class (per Stream B+F doctrine):** silent-failure (job runs on schedule, exits non-zero, no alarm fires; classic 6-layer verification gap — UI shell of a backup system without backend persistence)

---

## 10. Quick-reference checklist for Kim

Copy/paste this when you sit down at the Mac:

```
[ ] System Settings → Privacy & Security → Full Disk Access → +
[ ] Add /bin/bash                                              (Cmd+Shift+G to type path)
[ ] Add /usr/bin/python3                                       (Cmd+Shift+G to type path)
[ ] (Optional) Add /Applications/Xcode.app/Contents/Developer/usr/bin/python3
[ ] (Optional) Add /Applications/Utilities/Terminal.app
[ ] Verify all toggles ON (blue)
[ ] Open Terminal, run reload commands from §6.1
[ ] Manual smoke test: launchctl start com.mindfulnest.daily-backup
[ ] Wait 30s, check ~/MindfulNestBackups/directus/ for a new .sql.gz file
[ ] If missing env vars surface (§6.3), file follow-up Directus blocker
[ ] Future durability fix: relocate scripts out of CloudStorage path (§7)
```

---

## End of report

All autonomous diagnosis complete. Step 2 (FDA grant) and Steps 3/5 verification (reload + smoke) gated on Kim's hands. No Directus writes performed; no plist files modified; no launchd jobs reloaded in this session.
