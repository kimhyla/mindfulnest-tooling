# Calendar / Dep-Chained Triggers — Audit Sub-checks Wired

**Date:** 2026-05-08
**Author:** Claude (terminal session)
**Self-classification:** STANDARD
**Standing-rule LD:** 583 — `CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1`
**Activity log row:** id=1772
**File modified:** `Production/scripts/weekly_preflight_audit.py`

## 1. Summary

Three mechanical sub-checks added to `weekly_preflight_audit.py` to auto-surface
readiness for work-items that gate on calendar elapsed-time events or upstream
blocker resolution:

- **A. `check_credstore_fallback_clock`** — LD 227 Phase 3 readiness
- **B. `check_phase4_prereqs`** — LD 227 Phase 4 readiness
- **C. `check_pr8_merge_postwork`** — LD-505 boundary tightening migration trigger

All three are best-effort (never fail the main audit), idempotent (dedupe via
`prod_activity_log` action-equality lookup), and individually mutable via
dedicated env-var kill-switches.

## 2. Verbatim diff of audit script changes

Three insertions to `Production/scripts/weekly_preflight_audit.py`:

### Insertion 1 — Helper functions and section header (lines 794–880)

```python
# ---------------------------------------------------------------------------
# Calendar / dependency-chained sub-checks (LD CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1).
#
# Three sub-checks added 2026-05-08 to mechanically surface readiness for
# work-items that gate on a calendar elapsed-time event or on resolution of
# upstream blockers. Each is idempotent (a finding only fires if the
# downstream artifact / activity-log row does not already exist) and each
# has a kill-switch env var so Kim can mute it if a sub-check misfires.
#
#   A. check_credstore_fallback_clock     — LD 227 Phase 3 readiness
#                                            (14-day post-merge fallback-clock + zero warnings)
#   B. check_phase4_prereqs               — LD 227 Phase 4 prerequisites
#                                            (Sub-check A fired + BS-5/BS-7 resolved + BS-6 row exists)
#   C. check_pr8_merge_postwork           — PR #8 / LD-505 boundary tightening
#                                            (PR #8 merged AND no prior LD-505 closure activity)
# ---------------------------------------------------------------------------


def _branch_merge_date(branch_name):
    """Return the date a feature branch was merged to main, or None.

    Uses `git log main --first-parent --merges` to find the merge commit that
    brought the branch into main. Returns datetime.date or None.

    Best-effort: any subprocess / git error returns None and the caller
    treats that as "clock has not started" (Sub-check A: silent).
    """
    import subprocess
    try:
        # Search merge commits whose summary mentions the branch name. This is
        # the standard `git merge` summary form: "Merge branch 'foo' into main"
        # or "Merge pull request #N from owner/foo".
        result = subprocess.run(
            [
                "git", "log", "main",
                "--first-parent", "--merges",
                f"--grep={branch_name}",
                "--pretty=format:%H %cI",
                "-n", "1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            cwd=os.path.dirname(os.path.dirname(THIS_DIR)),  # repo root
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        # Parse "<sha> <iso8601-with-tz>"
        parts = result.stdout.strip().split(None, 1)
        if len(parts) != 2:
            return None
        iso = parts[1]
        # iso looks like 2026-05-15T10:23:45-07:00 — strip tz to date.
        return datetime.fromisoformat(iso).date()
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, OSError):
        return None


def _grep_launchd_logs_for_warning(log_glob, since_date, marker):
    """Return count of lines in matching log files that contain `marker`.

    Best-effort. Any IO error returns 0 (treated as "no warnings observed").
    Filters by file mtime >= since_date when possible.
    """
    import glob
    home = os.path.expanduser("~")
    pattern = os.path.join(home, "MindfulNestBackups", "launchd-logs", "*.err.log")
    if log_glob:
        pattern = log_glob
    count = 0
    try:
        for path in glob.glob(pattern):
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).date()
                if mtime < since_date:
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if marker in line:
                            count += 1
            except OSError:
                continue
    except OSError:
        return 0
    return count
```

### Insertion 2 — Sub-check A `check_credstore_fallback_clock` (lines 882–1019)

```python
def check_credstore_fallback_clock(client, dry_run=False):
    """LD 227 Phase 3 readiness sub-check.

    Logic:
      1. Determine merge date of feature/ld227-doppler-phase1-20260508 to main.
         If branch never merged -> silent (clock not started).
      2. If 14+ days elapsed AND no _CREDSTORE_FALLBACK_WARNED warnings in
         launchd .err.log files since merge -> emit finding.
      3. Idempotent: if LD 227 notes already record Phase 3 complete (token
         match), do not re-fire.

    Kill-switch: env var MN_SKIP_CREDSTORE_CLOCK=1.

    Returns:
        dict summary with keys: skipped, fired, reason, finding (if fired).
    """
    summary = {
        "subcheck": "check_credstore_fallback_clock",
        "skipped": False,
        "fired": False,
        "reason": None,
        "finding": None,
        "dry_run": dry_run,
    }
    if os.environ.get("MN_SKIP_CREDSTORE_CLOCK"):
        summary["skipped"] = True
        summary["reason"] = "MN_SKIP_CREDSTORE_CLOCK env var set"
        print(f"[credstore-clock] SKIP — kill-switch set")
        return summary

    branch = "feature/ld227-doppler-phase1-20260508"
    merge_date = _branch_merge_date(branch)
    if merge_date is None:
        summary["reason"] = f"branch {branch} not merged to main yet (clock not started)"
        print(f"[credstore-clock] silent — {summary['reason']}")
        return summary

    today = datetime.now(timezone.utc).date()
    days_elapsed = (today - merge_date).days
    summary["merge_date"] = merge_date.isoformat()
    summary["days_elapsed"] = days_elapsed
    if days_elapsed < 14:
        summary["reason"] = (
            f"clock running but only {days_elapsed} days elapsed since "
            f"merge {merge_date.isoformat()} (need 14+)"
        )
        print(f"[credstore-clock] silent — {summary['reason']}")
        return summary

    # Idempotency: don't re-fire if LD 227 notes already record Phase 3 complete.
    try:
        ld = client.get_one(
            "prod_locked_decisions", 227,
            fields="id,decision_key,status,notes",
        )
    except DirectusError as e:
        summary["reason"] = f"LD 227 lookup failed: {e}"
        print(f"[credstore-clock] WARN — {summary['reason']}")
        return summary
    notes_upper = (ld.get("notes") or "").upper()
    phase3_done_tokens = ("PHASE 3 COMPLETE", "PHASE 3 CLOSED", "PHASE_3_COMPLETE", "PHASE 3 SHIPPED")
    if any(t in notes_upper for t in phase3_done_tokens):
        summary["reason"] = "LD 227 notes already record Phase 3 complete (idempotent skip)"
        print(f"[credstore-clock] silent — {summary['reason']}")
        return summary

    # Count fallback-warned occurrences in launchd logs since merge_date.
    warn_count = _grep_launchd_logs_for_warning(None, merge_date, "_CREDSTORE_FALLBACK_WARNED")
    summary["launchd_warn_count"] = warn_count
    if warn_count > 0:
        summary["reason"] = (
            f"observed {warn_count} _CREDSTORE_FALLBACK_WARNED warnings in launchd logs "
            f"since merge {merge_date.isoformat()}; fallback path still active"
        )
        print(f"[credstore-clock] silent — {summary['reason']}")
        return summary

    # All conditions met → fire finding (idempotent activity-log dedupe).
    title = "LD 227 Phase 3 complete — proceed to Phase 4 prep"
    description = (
        f"Auto-surfaced by weekly_preflight_audit.py::check_credstore_fallback_clock "
        f"per LD CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1.\n\n"
        f"feature/ld227-doppler-phase1-20260508 merged to main on "
        f"{merge_date.isoformat()} ({days_elapsed} days elapsed). "
        f"No _CREDSTORE_FALLBACK_WARNED warnings observed in launchd "
        f"~/MindfulNestBackups/launchd-logs/*.err.log since merge. "
        f"LD 227 Phase 3 closure conditions met; LD 227 Phase 4 prep is now eligible."
    )

    # Dedupe: scan recent prod_activity_log for any prior firing of this title.
    try:
        existing = client._request(
            "GET",
            "/items/prod_activity_log",
            params={
                "filter[action][_eq]": title,
                "limit": 1,
            },
        ).get("data", [])
        if existing:
            summary["reason"] = "prior activity_log row exists for this finding (idempotent)"
            print(f"[credstore-clock] dedupe — {summary['reason']}")
            return summary
    except DirectusError as e:
        # Soft fail: if dedupe lookup fails, do not write a finding. Log and bail.
        summary["reason"] = f"dedupe lookup failed: {e}"
        print(f"[credstore-clock] WARN — {summary['reason']}")
        return summary

    finding = {
        "title": title,
        "description": description,
        "merge_date": merge_date.isoformat(),
        "days_elapsed": days_elapsed,
        "warn_count": warn_count,
    }
    summary["finding"] = finding

    if dry_run:
        summary["fired"] = True
        summary["reason"] = "[DRY-RUN] would write activity_log row"
        print(f"[credstore-clock] [DRY-RUN] would emit finding: {title}")
        return summary

    try:
        client._request("POST", "/items/prod_activity_log", data={
            "action": title,
            "details": json.dumps(finding),
            "performed_by": "weekly_preflight_audit.py::check_credstore_fallback_clock",
        })
        summary["fired"] = True
        summary["reason"] = "activity_log row written"
        print(f"[credstore-clock] FIRED — {title}")
    except DirectusError as e:
        summary["reason"] = f"activity_log POST failed: {e}"
        print(f"[credstore-clock] ERROR — {summary['reason']}")

    return summary
```

### Insertion 3 — Sub-check B `check_phase4_prereqs` (lines 1022–1144)

```python
def check_phase4_prereqs(client, dry_run=False):
    """LD 227 Phase 4 prereqs sub-check.

    All preconditions must hold:
      (1) Sub-check A's finding has fired (Phase 3 complete activity_log row exists)
      (2) prod_blockers row 97 (BS-5) is_resolved == true
      (3) prod_blockers row 98 (BS-7) is_resolved == true
      (4) A row exists for BS-6 (row need not be resolved; existence is sufficient)

    Kill-switch: env var MN_SKIP_PHASE4_PREREQS=1.

    Returns:
        dict summary with keys: skipped, fired, reason, prereq_state.
    """
    summary = {
        "subcheck": "check_phase4_prereqs",
        "skipped": False,
        "fired": False,
        "reason": None,
        "prereq_state": {},
        "dry_run": dry_run,
    }
    if os.environ.get("MN_SKIP_PHASE4_PREREQS"):
        summary["skipped"] = True
        summary["reason"] = "MN_SKIP_PHASE4_PREREQS env var set"
        print(f"[phase4-prereqs] SKIP — kill-switch set")
        return summary

    state = summary["prereq_state"]

    # Prereq 1: Phase 3 complete activity-log row.
    phase3_title = "LD 227 Phase 3 complete — proceed to Phase 4 prep"
    try:
        rows = client._request(
            "GET", "/items/prod_activity_log",
            params={"filter[action][_eq]": phase3_title, "limit": 1},
        ).get("data", [])
        state["phase3_row_exists"] = bool(rows)
    except DirectusError as e:
        state["phase3_row_exists"] = False
        state["phase3_lookup_error"] = str(e)

    # Prereq 2 + 3: BS-5 (row 97) + BS-7 (row 98) resolved.
    for rid, label in [(97, "BS5"), (98, "BS7")]:
        try:
            row = client.get_one("prod_blockers", rid)
            state[f"{label}_is_resolved"] = bool(row.get("is_resolved"))
        except DirectusError as e:
            state[f"{label}_is_resolved"] = False
            state[f"{label}_lookup_error"] = str(e)

    # Prereq 4: BS-6 row exists (any state).
    try:
        bs6_rows = client.get(
            "prod_blockers",
            filters={"title": {"_contains": "BS-6"}},
            limit=1,
        )
        state["BS6_row_exists"] = bool(bs6_rows)
        if bs6_rows:
            state["BS6_row_id"] = bs6_rows[0].get("id")
    except DirectusError as e:
        state["BS6_row_exists"] = False
        state["BS6_lookup_error"] = str(e)

    all_met = (
        state.get("phase3_row_exists")
        and state.get("BS5_is_resolved")
        and state.get("BS7_is_resolved")
        and state.get("BS6_row_exists")
    )
    if not all_met:
        summary["reason"] = f"prereqs not all met: {state}"
        print(f"[phase4-prereqs] silent — {summary['reason']}")
        return summary

    title = "LD 227 Phase 4 ready to authorize"
    description = (
        f"Auto-surfaced by weekly_preflight_audit.py::check_phase4_prereqs per LD "
        f"CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1.\n\n"
        f"All four prerequisites confirmed:\n"
        f"  - Phase 3 complete activity_log row present\n"
        f"  - BS-5 (prod_blockers id=97) is_resolved=true\n"
        f"  - BS-7 (prod_blockers id=98) is_resolved=true\n"
        f"  - BS-6 row exists (id={state.get('BS6_row_id')})\n\n"
        f"LD 227 Phase 4 authorization is ready for Kim's review."
    )

    # Idempotency: prior firing dedupe.
    try:
        existing = client._request(
            "GET", "/items/prod_activity_log",
            params={"filter[action][_eq]": title, "limit": 1},
        ).get("data", [])
        if existing:
            summary["reason"] = "prior activity_log row exists for this finding (idempotent)"
            print(f"[phase4-prereqs] dedupe — {summary['reason']}")
            return summary
    except DirectusError as e:
        summary["reason"] = f"dedupe lookup failed: {e}"
        print(f"[phase4-prereqs] WARN — {summary['reason']}")
        return summary

    if dry_run:
        summary["fired"] = True
        summary["reason"] = "[DRY-RUN] would write activity_log row"
        print(f"[phase4-prereqs] [DRY-RUN] would emit finding: {title}")
        return summary

    try:
        client._request("POST", "/items/prod_activity_log", data={
            "action": title,
            "details": json.dumps({"prereq_state": state, "title": title, "description": description}),
            "performed_by": "weekly_preflight_audit.py::check_phase4_prereqs",
        })
        summary["fired"] = True
        summary["reason"] = "activity_log row written"
        print(f"[phase4-prereqs] FIRED — {title}")
    except DirectusError as e:
        summary["reason"] = f"activity_log POST failed: {e}"
        print(f"[phase4-prereqs] ERROR — {summary['reason']}")

    return summary
```

### Insertion 4 — Sub-check C `check_pr8_merge_postwork` (lines 1147–1264)

```python
def check_pr8_merge_postwork(client, dry_run=False):
    """PR #8 / LD-505 post-merge sub-check.

    Logic:
      1. Run `gh pr view 8 --json state,mergedAt --repo kimhyla/mindfulnest-tooling`.
      2. If state == 'MERGED' AND no prior activity_log row exists for this
         finding -> emit "PR #8 merged — LD-505 boundary tightening migration ready to spawn".
      3. Idempotent. Note: this overlaps with check_pr_merge_closure_events
         in scope (PRs against tooling repo) but fills the gap for LDs that
         do NOT match the SHORTCUT_*_V1 decision_key pattern (LD-505 is one).

    Kill-switch: env var MN_SKIP_PR8_POSTWORK=1.

    Returns:
        dict summary with keys: skipped, fired, reason, pr_state.
    """
    summary = {
        "subcheck": "check_pr8_merge_postwork",
        "skipped": False,
        "fired": False,
        "reason": None,
        "pr_state": None,
        "dry_run": dry_run,
    }
    if os.environ.get("MN_SKIP_PR8_POSTWORK"):
        summary["skipped"] = True
        summary["reason"] = "MN_SKIP_PR8_POSTWORK env var set"
        print(f"[pr8-postwork] SKIP — kill-switch set")
        return summary

    import subprocess
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view", "8",
                "--json", "state,mergedAt",
                "--repo", "kimhyla/mindfulnest-tooling",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        summary["reason"] = f"gh CLI error: {type(e).__name__}: {e}"
        print(f"[pr8-postwork] WARN — {summary['reason']}")
        return summary
    if result.returncode != 0:
        summary["reason"] = f"gh CLI returncode={result.returncode} stderr={result.stderr.strip()[:200]}"
        print(f"[pr8-postwork] WARN — {summary['reason']}")
        return summary
    try:
        pr_data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as e:
        summary["reason"] = f"gh JSON parse failed: {e}"
        print(f"[pr8-postwork] WARN — {summary['reason']}")
        return summary

    summary["pr_state"] = pr_data
    if pr_data.get("state") != "MERGED":
        summary["reason"] = f"PR #8 state={pr_data.get('state')!r} (not MERGED yet)"
        print(f"[pr8-postwork] silent — {summary['reason']}")
        return summary

    title = "PR #8 merged — LD-505 boundary tightening migration ready to spawn"

    # Idempotency: prior firing dedupe.
    try:
        existing = client._request(
            "GET", "/items/prod_activity_log",
            params={"filter[action][_eq]": title, "limit": 1},
        ).get("data", [])
        if existing:
            summary["reason"] = "prior activity_log row exists for this finding (idempotent)"
            print(f"[pr8-postwork] dedupe — {summary['reason']}")
            return summary
    except DirectusError as e:
        summary["reason"] = f"dedupe lookup failed: {e}"
        print(f"[pr8-postwork] WARN — {summary['reason']}")
        return summary

    description = (
        f"Auto-surfaced by weekly_preflight_audit.py::check_pr8_merge_postwork per LD "
        f"CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1.\n\n"
        f"PR #8 in kimhyla/mindfulnest-tooling merged at {pr_data.get('mergedAt')}. "
        f"LD-505 boundary tightening migration is ready to spawn. Note: this sub-check "
        f"complements check_pr_merge_closure_events (which only fires for "
        f"SHORTCUT_*_V1 LDs). LD-505 is not classified SHORTCUT_*_V1, so this "
        f"sub-check fills the gap."
    )

    if dry_run:
        summary["fired"] = True
        summary["reason"] = "[DRY-RUN] would write activity_log row"
        print(f"[pr8-postwork] [DRY-RUN] would emit finding: {title}")
        return summary

    try:
        client._request("POST", "/items/prod_activity_log", data={
            "action": title,
            "details": json.dumps({
                "pr_number": 8,
                "repo": "kimhyla/mindfulnest-tooling",
                "merged_at": pr_data.get("mergedAt"),
                "title": title,
                "description": description,
            }),
            "performed_by": "weekly_preflight_audit.py::check_pr8_merge_postwork",
        })
        summary["fired"] = True
        summary["reason"] = "activity_log row written"
        print(f"[pr8-postwork] FIRED — {title}")
    except DirectusError as e:
        summary["reason"] = f"activity_log POST failed: {e}"
        print(f"[pr8-postwork] ERROR — {summary['reason']}")

    return summary
```

### Insertion 5 — Wiring into `run_audit()` (lines 1611–1631, after `check_pr_merge_closure_events` block)

```python
    # Calendar / dep-chained sub-checks (LD CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1).
    # Each is best-effort and idempotent. Each has a dedicated kill-switch env var
    # (see function docstrings). These mechanically surface readiness for items
    # that gate on a calendar elapsed-time event or upstream blocker resolution.
    try:
        summary["credstore_clock"] = check_credstore_fallback_clock(client, dry_run=dry_run)
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: check_credstore_fallback_clock sub-check failed: {e!r}")
        summary["credstore_clock"] = {"error": repr(e)}

    try:
        summary["phase4_prereqs"] = check_phase4_prereqs(client, dry_run=dry_run)
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: check_phase4_prereqs sub-check failed: {e!r}")
        summary["phase4_prereqs"] = {"error": repr(e)}

    try:
        summary["pr8_postwork"] = check_pr8_merge_postwork(client, dry_run=dry_run)
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: check_pr8_merge_postwork sub-check failed: {e!r}")
        summary["pr8_postwork"] = {"error": repr(e)}
```

### Diff stat note

`git diff --stat` reports 765 insertions / 8 deletions to the file. Of those,
the calendar/dep-chained sub-checks contribute approximately 535 insertions
(insertions 1–5 above). The remaining ~230 insertions / 8 deletions are
**pre-existing uncommitted PERIODIC class changes** that were already present
in the working tree when this session started (related to LD
`PERIODIC_CLASS_ESTABLISHMENT_V1`, dated 2026-05-08 in their author headers,
written by a prior session). Per the spec instruction "the live Dropbox tree
may have uncommitted git state — that's expected. Operate on the working
directory, ignore git state," those were left untouched.

## 3. Per-sub-check verbatim test outputs

### 3.1 `python3 -m py_compile` (all insertions)

```
$ python3 -m py_compile "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/scripts/weekly_preflight_audit.py" && echo "PY_COMPILE_OK"
PY_COMPILE_OK
```

### 3.2 Negative path — full audit dry-run (all 3 silent on baseline)

```
$ python3 Production/scripts/weekly_preflight_audit.py --dry-run 2>&1 | grep -E "credstore-clock|phase4-prereqs|pr8-postwork"
[credstore-clock] silent — branch feature/ld227-doppler-phase1-20260508 not merged to main yet (clock not started)
[phase4-prereqs] silent — prereqs not all met: {'phase3_row_exists': False, 'BS5_is_resolved': False, 'BS7_is_resolved': False, 'BS6_row_exists': False}
[pr8-postwork] silent — PR #8 state='OPEN' (not MERGED yet)
```

Baseline state confirmed via direct queries before test:
- `git branch -a` shows `feature/ld227-doppler-phase1-20260508` exists locally but no merge-commit on main yet (returns None from `_branch_merge_date`)
- `gh pr view 8 --json state,mergedAt --repo kimhyla/mindfulnest-tooling` returns `{"state":"OPEN","mergedAt":null}`
- `prod_blockers` rows 97 (BS-5) and 98 (BS-7) both have `is_resolved=False`
- No row matching `title contains 'BS-6'` exists in `prod_blockers`

### 3.3 Mock-positive paths (each sub-check, dry-run)

Test harness: `/tmp/mock_test_subchecks.py` (deleted after run; reproducible
via the function definitions themselves with `unittest.mock`).

#### Sub-check A — Mock positive

Monkeypatched `_branch_merge_date` to return `today - 20 days`, and
`_grep_launchd_logs_for_warning` to return `0`. Live LD 227 read confirmed
notes do NOT contain a `PHASE 3 COMPLETE` token.

```
[credstore-clock] [DRY-RUN] would emit finding: LD 227 Phase 3 complete — proceed to Phase 4 prep
summary_a: {'subcheck': 'check_credstore_fallback_clock', 'skipped': False, 'fired': True, 'reason': '[DRY-RUN] would write activity_log row', 'finding': {'title': 'LD 227 Phase 3 complete — proceed to Phase 4 prep', 'description': 'Auto-surfaced by weekly_preflight_audit.py::check_credstore_fallback_clock per LD CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1.\n\nfeature/ld227-doppler-phase1-20260508 merged to main on 2026-04-18 (20 days elapsed). No _CREDSTORE_FALLBACK_WARNED warnings observed in launchd ~/MindfulNestBackups/launchd-logs/*.err.log since merge. LD 227 Phase 3 closure conditions met; LD 227 Phase 4 prep is now eligible.', 'merge_date': '2026-04-18', 'days_elapsed': 20, 'warn_count': 0}, 'dry_run': True, 'merge_date': '2026-04-18', 'days_elapsed': 20, 'launchd_warn_count': 0}
PASS: positive path fired (dry-run)
```

#### Sub-check B — Mock positive

Stubbed `client.get_one(prod_blockers, 97)` -> `is_resolved=True`,
`get_one(prod_blockers, 98)` -> `is_resolved=True`,
`get(prod_blockers, filters={'title': {'_contains': 'BS-6'}})` -> `[{"id": 100, ...}]`,
and `_request(GET prod_activity_log filter[action][_eq]=Phase 3 complete...)` -> `[{...}]`.

```
[phase4-prereqs] [DRY-RUN] would emit finding: LD 227 Phase 4 ready to authorize
summary_b: {'subcheck': 'check_phase4_prereqs', 'skipped': False, 'fired': True, 'reason': '[DRY-RUN] would write activity_log row', 'prereq_state': {'phase3_row_exists': True, 'BS5_is_resolved': True, 'BS7_is_resolved': True, 'BS6_row_exists': True, 'BS6_row_id': 100}, 'dry_run': True}
PASS: positive path fired (dry-run)
```

#### Sub-check C — Mock positive

Monkeypatched `subprocess.run` to return `{"state": "MERGED", "mergedAt": "2026-05-15T10:00:00Z"}`.

```
[pr8-postwork] [DRY-RUN] would emit finding: PR #8 merged — LD-505 boundary tightening migration ready to spawn
summary_c: {'subcheck': 'check_pr8_merge_postwork', 'skipped': False, 'fired': True, 'reason': '[DRY-RUN] would write activity_log row', 'pr_state': {'state': 'MERGED', 'mergedAt': '2026-05-15T10:00:00Z'}, 'dry_run': True}
PASS: positive path fired (dry-run)
```

### 3.4 Kill-switch verification

```
$ MN_SKIP_CREDSTORE_CLOCK=1 MN_SKIP_PHASE4_PREREQS=1 MN_SKIP_PR8_POSTWORK=1 python3 Production/scripts/weekly_preflight_audit.py --dry-run 2>&1 | tail -3
[credstore-clock] SKIP — kill-switch set
[phase4-prereqs] SKIP — kill-switch set
[pr8-postwork] SKIP — kill-switch set
```

## 4. Verbatim LD POST response (LD 583)

POST `/items/prod_locked_decisions` succeeded. Read-back verification (Rule 35):

```json
{
  "id": 583,
  "decision_key": "CALENDAR_DEP_TRIGGERS_AUDIT_PROTOCOL_V1",
  "decision_name": "Calendar / dependency-chained sub-checks added to weekly_preflight_audit.py",
  "severity": "HARD",
  "task_category": "all",
  "enforcement_type": "ci_check",
  "enforcement_artifact_ref": "Production/scripts/weekly_preflight_audit.py :: check_credstore_fallback_clock + check_phase4_prereqs + check_pr8_merge_postwork",
  "scope_domain": "cross-cutting",
  "source_document": "Production/scripts/weekly_preflight_audit.py",
  "status": "active",
  "date_locked": "2026-05-08"
}
```

`decision_text` length: 3077 chars; `notes` length: 901 chars. (Full text in
the LD itself; this report does not duplicate the body to keep size sane.)

Notable schema validation friction encountered: first POST attempt failed
with `HTTP 400: Validation failed for field "decision_name". Value is required.`
followed by `source_document` requirement. Both were added on the second
attempt. Required fields list pulled from `client.get_fields('prod_locked_decisions')`:
`decision_key, decision_name, decision_text, source_document, task_category,
severity, date_locked`.

## 5. Verbatim activity log row id

```json
{
  "id": 1772,
  "action": "Calendar/dep-chained sub-checks wired into weekly_preflight_audit.py",
  "performed_by": "Claude (terminal session 2026-05-08)",
  "created_at": "2026-05-08T13:28:21.762Z"
}
```

`details` payload includes: standing_rule_ld=583, sub_checks_added (3 names),
helpers_added (2 names), kill_switches (3 env-var names), tests_passed (4
items), baseline_state_at_authoring (5 booleans), file_modified.

## 6. Confidence tags (per Rule 24)

- **HIGH** — All three sub-checks compile, run silently on baseline, and fire
  positively under monkey-patched conditions. Tested directly against live
  Directus state (LD 227, BS-5, BS-7, BS-6 absence, PR #8 OPEN).
- **HIGH** — Standing-rule LD 583 created and read-back verified. All required
  fields populated; enums match schema (`severity=HARD`, `task_category=all`,
  `enforcement_type=ci_check`, `scope_domain=cross-cutting`).
- **HIGH** — Kill-switches verified to mute each sub-check independently.
- **MEDIUM** — `_branch_merge_date` correctness depends on the merge commit's
  summary mentioning the branch name. Standard `gh pr merge` and `git merge --no-ff`
  satisfy this; `git rebase` + manual fast-forward without merge-commit does
  not. Documented as a limitation in the LD.
- **MEDIUM** — `_grep_launchd_logs_for_warning` filters by file mtime which can
  drift if logs are rotated. The current launchd config writes only two files
  (`com.mindfulnest.daily-backup.err.log` and `com.mindfulnest.weekly-snapshot.err.log`),
  both currently empty (zero bytes). False-positive risk: if the credential_store
  fallback fires but stderr is captured to a different log file outside the
  scanned glob, the sub-check would not see the warning and might fire prematurely.

## 7. Self-classification

**STANDARD** — additive feature work to a governance-tooling script. No new
schemas, no destructive actions, no architectural redesign. Three new
functions plus two helpers wired into an existing entry point with
best-effort exception handling. Activity-log writes are idempotent;
no data deletion or modification of existing rows.

## 8. Idempotency guarantee per sub-check

| Sub-check | Idempotency mechanism |
|---|---|
| A — `check_credstore_fallback_clock` | Two independent dedupe layers: (1) LD 227 notes scanned for `PHASE 3 COMPLETE` / `PHASE 3 CLOSED` / `PHASE_3_COMPLETE` / `PHASE 3 SHIPPED` tokens before any write — covers manual Phase 3 closure. (2) `prod_activity_log filter[action][_eq]="LD 227 Phase 3 complete — proceed to Phase 4 prep"` lookup before POST — covers prior firing by this sub-check. Either layer matches → no write. |
| B — `check_phase4_prereqs` | Single dedupe layer via `prod_activity_log filter[action][_eq]="LD 227 Phase 4 ready to authorize"`. Sub-check is also gated on Sub-check A's row existing (so it cannot fire before A has fired at least once). |
| C — `check_pr8_merge_postwork` | Single dedupe layer via `prod_activity_log filter[action][_eq]="PR #8 merged — LD-505 boundary tightening migration ready to spawn"`. Note: this sub-check is hard-coded to PR #8 — once that PR is closed (merged or otherwise), the gh-CLI lookup becomes deterministic and the dedupe lookup prevents repeat writes. |

All three sub-checks fail-closed on dedupe-lookup error: if the GET request
fails for any reason, the sub-check returns without writing rather than
risk a duplicate row.

## 9. Limitations

1. **Branch-merge detection (Sub-check A).** `_branch_merge_date` uses
   `git log main --first-parent --merges --grep=<branch>`. This works for
   standard PR merges (the synthetic "Merge pull request #N from owner/branch"
   commit subject contains the branch name) and `git merge --no-ff`. It does
   NOT work for: rebase-merge with squashed commit message, fast-forward
   merge without a merge commit, or cherry-pick. The branch-name token must
   appear in the merge commit's subject. Mitigation: standardize on PR-merge
   workflow (already in use).

2. **Launchd log path (Sub-check A).** The grep target is hard-coded to
   `~/MindfulNestBackups/launchd-logs/*.err.log`. If the launchd plist is
   reconfigured to write logs elsewhere, the scan returns 0 (no warnings)
   which would produce a false-positive "no warnings observed" result and
   fire the finding prematurely. Mitigation: keep launchd log path stable;
   if changed, update `_grep_launchd_logs_for_warning` accordingly.

3. **PR number coupling (Sub-check C).** Sub-check is hard-coded to PR #8 in
   `kimhyla/mindfulnest-tooling`. If the LD-505 PR opens as a different
   number, this sub-check checks the wrong PR. Acceptable because the spec
   explicitly named PR #8; any future LD-505-bearing PR with a different
   number requires either a new sub-check or PR-renumbering. Documented in
   LD 583 limitations.

4. **No coverage of credentials.py warning emission.** The credential_store
   `_CREDSTORE_FALLBACK_WARNED` flag is set inside `Production/lib/credential_store.py`
   (lines 76 + 83), and a similar warning is emitted from
   `Production/tools/lib/credentials.py` (the actual loader observed during
   testing). The grep-target marker chosen (`_CREDSTORE_FALLBACK_WARNED`)
   matches the env var name set by credential_store.py. If the credentials.py
   warning text differs and the env-var setter never fires, the marker grep
   will not find recent warnings and Sub-check A could false-positive.
   Mitigation: when LD 227 Phase 2 ships (single canonical credential loader),
   verify the marker still maps to the live emission code.

5. **Pre-existing uncommitted PERIODIC class changes.** When this session
   started, the live working tree already contained ~230 lines of
   uncommitted edits to `weekly_preflight_audit.py` for the PERIODIC class
   feature (LD `PERIODIC_CLASS_ESTABLISHMENT_V1`, dated 2026-05-08). Per
   spec instruction those were left untouched. The `git diff` output
   conflates those pre-existing changes with the calendar/dep-chained
   additions; the latter are isolated in §2 of this report by line-range.

6. **Schema enum drift.** The LD payload uses `task_category=all` and
   `scope_domain=cross-cutting` enum values verified live from
   `client.get_fields('prod_locked_decisions')`. If those enums change in
   future Directus migrations, regenerate the LD via
   `weekly_preflight_audit.py` schema-introspection helper.
