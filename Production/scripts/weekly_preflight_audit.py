#!/usr/bin/env python3
"""
Weekly Pre-Flight Audit — Meta-Enforcement Detection Loop

Part 1E of Meta-Enforcement Institution (indexed-riding-lake plan).
Locked decision: PREFLIGHT_PROTOCOL_STEP_0 (Directus prod_locked_decisions ID 124).

Detects tasks that bypassed `zero-error-qa` Phase 0 (Pre-Flight Protocol)
by scanning `app_activity_log` for architectural-looking entries from the
past 7 days that have NO corresponding `prod_preflight_reviews` row.

For each miss, writes a CRITICAL entry to `app_blockers`. Blockers surface
at next session start (dashboard-gate skill), making skips visible without
Kim having to be the detective.

Safe to run repeatedly: de-dupes against existing unresolved blockers so
reruns don't create duplicate alerts.

Schedule: weekly Monday 00:00 UTC (scheduled-tasks MCP or system cron).

Usage:
    python3 Production/scripts/weekly_preflight_audit.py            # run audit
    python3 Production/scripts/weekly_preflight_audit.py --dry-run  # report only
    python3 Production/scripts/weekly_preflight_audit.py --days 14  # custom window
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from lib.credentials import load_credentials  # noqa: E402
from lib.directus import DirectusClient, DirectusError  # noqa: E402


# Heuristic keywords — if an app_activity_log.action or details field
# contains any of these, the entry is presumed "architectural" and requires
# a matching prod_preflight_reviews row. Conservative: false positives
# create a blocker Kim can dismiss; false negatives hide real skips.
ARCHITECTURAL_KEYWORDS = [
    "firestore.rules",
    "security rule",
    "new collection",
    "created collection",
    "schema change",
    "skill file",
    "SKILL.md",
    "CLAUDE.md",
    "rule 19",
    "locked decision",
    "package.json",
    "auth flow",
    "workflow",
    "phase 0",
    "preflight",
    "institution",
    "governance",
]

# Trivial markers — if present, the entry is skipped (typo fixes etc.)
TRIVIAL_MARKERS = [
    "typo",
    "rename variable",
    "update comment",
    "audit run",  # self-log of this script
]


def looks_architectural(entry):
    details = entry.get("details")
    details_str = details if isinstance(details, str) else (json.dumps(details) if details else "")
    haystack = f"{entry.get('action', '')} {details_str}".lower()
    if any(t in haystack for t in TRIVIAL_MARKERS):
        return False
    return any(k.lower() in haystack for k in ARCHITECTURAL_KEYWORDS)


def extract_task_id(entry):
    """Pull a task_id from details text. Supports patterns:
    - "task_id=xxx"
    - "task_id: xxx"
    - JSON details with a task_id key
    Returns None if no task_id found.
    """
    details = entry.get("details")
    if not details:
        return None
    # Directus may return JSON fields pre-parsed as dict/list
    if isinstance(details, dict) and "task_id" in details:
        return str(details["task_id"])
    if isinstance(details, str):
        # Try JSON first
        try:
            parsed = json.loads(details)
            if isinstance(parsed, dict) and "task_id" in parsed:
                return str(parsed["task_id"])
        except (json.JSONDecodeError, TypeError):
            pass
        # Fall back to text regex
        match = re.search(r"task_id\s*[:=]\s*([\w\-]+)", details)
        if match:
            return match.group(1)
    return None


def run_audit(days=7, hours=None, dry_run=False):
    creds = load_credentials()
    client = DirectusClient(
        creds["directus_url"], creds["directus_email"], creds["directus_password"]
    )
    client.authenticate()

    # hours takes precedence over days if both specified
    if hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        window_label = f"past {hours} hours"
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        window_label = f"past {days} days"
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")

    print(f"[audit] Window: {window_label} (>= {cutoff_iso})")

    # 1. Pull recent activity log entries
    resp = client._request(
        "GET",
        "/items/app_activity_log",
        params={
            "filter[created_at][_gte]": cutoff_iso,
            "limit": 1000,
            "sort": "created_at",
        },
    )
    activities = resp.get("data", [])
    print(f"[audit] app_activity_log entries in window: {len(activities)}")

    # 2. Pull all preflight reviews in the same window (plus buffer)
    resp = client._request(
        "GET",
        "/items/prod_preflight_reviews",
        params={
            "filter[created_at][_gte]": cutoff_iso,
            "limit": 1000,
        },
    )
    reviews = resp.get("data", [])
    review_log_ids = {r.get("related_activity_log_id") for r in reviews if r.get("related_activity_log_id")}
    review_task_ids = {r.get("task_id") for r in reviews if r.get("task_id")}
    print(f"[audit] prod_preflight_reviews entries in window: {len(reviews)} "
          f"({len(review_log_ids)} with log_id FK, {len(review_task_ids)} with task_id)")

    # 3. Classify each activity entry.
    # Priority order (BS2 hardening — zero-error-qa Phase 0 Step 8):
    #   A. EXACT match via related_activity_log_id FK → definitively covered
    #   B. EXACT match via embedded task_id → definitively covered
    #   C. Architectural-keyword heuristic → fallback signal only
    # A miss is: (architectural-looking) AND NOT (A) AND NOT (B).
    misses = []
    covered_exact = 0
    for entry in activities:
        entry_id = entry.get("id")
        task_id = extract_task_id(entry)
        exact_match = (
            entry_id in review_log_ids
            or (task_id is not None and task_id in review_task_ids)
        )
        if exact_match:
            covered_exact += 1
            continue
        # No exact match. Was it architectural? If not, presumed non-governed.
        if not looks_architectural(entry):
            continue
        misses.append({"entry": entry, "task_id": task_id})

    print(f"[audit] Covered by EXACT FK/task_id match: {covered_exact}")
    print(f"[audit] Architectural-looking activity without preflight: {len(misses)}")

    # 4. De-dupe against existing unresolved blockers
    resp = client._request(
        "GET",
        "/items/app_blockers",
        params={
            "filter[is_resolved][_eq]": "false",
            "filter[title][_starts_with]": "Pre-flight audit violation",
            "limit": 1000,
        },
    )
    existing_blockers = resp.get("data", [])
    existing_titles = {b["title"] for b in existing_blockers}
    print(f"[audit] Existing unresolved preflight blockers: {len(existing_blockers)}")

    # 5. Write blockers (or print if dry-run)
    created, deduped = 0, 0
    for miss in misses:
        entry = miss["entry"]
        entry_id = entry.get("id")
        action = entry.get("action", "(no action)")
        title = f"Pre-flight audit violation: activity #{entry_id} had no preflight review"
        if title in existing_titles:
            deduped += 1
            continue

        description = (
            f"Weekly preflight audit found app_activity_log entry #{entry_id} "
            f"with architectural signal but no matching prod_preflight_reviews row.\n\n"
            f"Action: {action}\n"
            f"Created: {entry.get('created_at')}\n"
            f"Task ID (extracted): {miss['task_id'] or '(none found in details)'}\n"
            f"Performed by: {entry.get('performed_by', 'unknown')}\n\n"
            f"This may be a true skip of zero-error-qa Phase 0, or a false positive "
            f"from the architectural-keyword heuristic. Review the activity entry "
            f"and either (a) resolve this blocker if it was a non-architectural task, "
            f"or (b) retroactively run a preflight review if a skip is confirmed."
        )

        if dry_run:
            print(f"[audit] [DRY-RUN] would create blocker: {title}")
            created += 1
            continue

        payload = {
            "feature_id": entry.get("feature_id"),
            "title": title,
            "description": description,
            "severity": "critical",
            "is_resolved": False,
        }
        try:
            client._request("POST", "/items/app_blockers", data=payload)
            print(f"[audit] CREATED blocker: {title}")
            created += 1
        except DirectusError as e:
            print(f"[audit] ERROR creating blocker for entry {entry_id}: {e}")

    # 6. Log the audit run itself
    summary = {
        "days": days,
        "activities_scanned": len(activities),
        "preflight_reviews_found": len(reviews),
        "misses_detected": len(misses),
        "blockers_created": created,
        "already_existing": deduped,
        "dry_run": dry_run,
    }
    log_payload = {
        "feature_id": 5,  # security rules — closest feature for governance audit runs
        "action": "weekly_preflight_audit run",
        "details": json.dumps(summary),
        "performed_by": "weekly_preflight_audit.py",
    }
    if not dry_run:
        try:
            client._request("POST", "/items/app_activity_log", data=log_payload)
        except DirectusError as e:
            print(f"[audit] WARNING: could not log audit run: {e}")

    print(f"[audit] DONE — {summary}")

    # Sub-check: governance drift (overnight deliverable G, 2026-04-19).
    # Surfaces LDs that no Production/governance/*.md file cites. Best-effort:
    # never lets the main weekly audit fail on a sub-check exception.
    try:
        from importlib import import_module
        gd = import_module("governance_drift_check")
        gd_summary = gd.run_drift_check(min_severity="HIGH", dry_run=dry_run, as_json=False)
        summary["governance_drift"] = gd_summary
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: governance_drift_check sub-check failed: {e!r}")
        summary["governance_drift"] = {"error": repr(e)}

    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write blockers")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default 7)")
    parser.add_argument("--hours", type=int, default=None, help="Lookback window in hours (overrides --days if set — for session-end audits)")
    args = parser.parse_args()

    run_audit(days=args.days, hours=args.hours, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
