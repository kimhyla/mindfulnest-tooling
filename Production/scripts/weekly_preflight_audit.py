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
from datetime import date, datetime, timedelta, timezone

# Policy-lock date for the 14-day RARE_NEVER SHORTCUT closure cap (Kim directive 2026-05-07).
# LDs locked BEFORE this date predate the policy and emit a softer GRANDFATHER_REVIEW
# finding once for one-time triage; once triaged (CLOSE / AMEND / re-classify) they
# never re-fire. LDs locked ON or AFTER this date get the normal 14-day cap.
SHORTCUT_CAP_POLICY_LOCK_DATE = date(2026, 5, 7)

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


# SHORTCUT LD closure-cap classification — keyed on LD id (Directus pk).
# REPLACES the prior uniform 120-day proxy cap (Kim directive 2026-05-07).
#
# Two buckets:
#   EVENT_DRIVEN — closure waits for a specific named event (PR merge, repo
#     cutover, infrastructure availability change). The LD itself defines the
#     hard date backstop where applicable. We retain a 120-day backstop in
#     the audit only for safety; the EVENT trigger is the primary closure path.
#   RARE_NEVER — no triggering event scheduled; closure is "if/when we
#     happen to refactor" or "if/when an upstream tool changes". These ride
#     the 14-day SHORTCUT closure cap mandated by Kim 2026-05-07.
#
# Adding a new SHORTCUT_*_V1 LD? You MUST add it here with an explicit
# classification — the audit raises an UNCLASSIFIED warning if a row is
# missing. This forces conscious classification at LD-creation time.
SHORTCUT_LD_CLASSIFICATION = {
    # EVENT_DRIVEN — closure event is named; literal cap (if any) is in the LD.
    227: "EVENT_DRIVEN",   # SHORTCUT_CREDSTORE_MD_FALLBACK_20260418 — gates on doppler-only cutover ("once all launch scripts / cron jobs / CLI sites have been verified running under `doppler run --` for one full production cycle, remove the MD file fallback").
    237: "EVENT_DRIVEN",   # SHORTCUT_STAGING_PITR_WINDOW_20260418 — gates on S3-POLISH-retention CF ship + Firestore TTL GA + Google PITR-per-collection control.
    247: "EVENT_DRIVEN",   # SHORTCUT_EMAIL_VERIFICATION_DEFERRED_20260418 — gates on S3-AUTH-consent ship.
    248: "EVENT_DRIVEN",   # SHORTCUT_FORGOT_PASSWORD_DEFERRED_20260418 — gates on S3-AUTH-recovery row ship "before first external beta user".
    269: "EVENT_DRIVEN",   # SHORTCUT_COIN_REWARDS_HARDCODED_ARC1_20260418 — gates on Arc 2 start OR 3+ Kim-tunes OR A/B testing.
    270: "EVENT_DRIVEN",   # SHORTCUT_AUDIT_BEST_EFFORT_WRITES_20260418 — gates on S3-POLISH-audit-retry follow-up "before external beta user onboarding".
    273: "EVENT_DRIVEN",   # SHORTCUT_RN_COMPONENT_TEST_INFRA_DEFERRED_20260418 — gates on S3-TEST-rn-component-setup ship "before first external beta user".
    277: "EVENT_DRIVEN",   # SHORTCUT_APP_CHECK_SDK_DEFERRED_20260418 — gates on S3-POLISH-appcheck ship.
    278: "EVENT_DRIVEN",   # SHORTCUT_AUTH_IN_MEMORY_PERSISTENCE_20260418 — gates on S3-AUTH-persistence follow-up row "before external beta".
    408: "EVENT_DRIVEN",   # SHORTCUT_THERAPIST_DASHBOARD_V1_1 — gates on V1 launch + production traffic ("therapist dashboard codebase begins immediately post-launch").
    416: "EVENT_DRIVEN",   # SHORTCUT_PHASE_BOUNDARIES_CACHE_HIT_CF_V1 — gates on V1.1 cutover ("store phaseBoundaries in CacheEntry in V1.1").
    545: "EVENT_DRIVEN",   # SHORTCUT_STORYBOARD_FIX_BEFORE_GAPFIX_V1 — gates on V59_CICD_GAP_FIX PR merge.
    565: "EVENT_DRIVEN",   # SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN_V1 — gates on tooling private flip OR Enterprise tier OR 2026-09-07 hard cap (in LD).
    567: "EVENT_DRIVEN",   # SHORTCUT_RN_REPO_PUBLIC_FOR_CODESCAN_V1 — gates on RN private flip OR TestFlight upload OR COPPA commit OR 2026-09-07 hard cap (in LD).
    # 199 SHORTCUT_ARCH_WEIGHT_PCT_COLLAPSED_TO_ENUM — closed 2026-05-07 (status=closed); v2 inventory closure trigger met. Removed from active classification dict; status='active' filter excludes it from query. Kept here as a comment for traceability.
    200: "EVENT_DRIVEN",   # SHORTCUT_LD_LINKAGE_SNAPSHOT_ONLY — re-classified 2026-05-07 RARE_NEVER → EVENT_DRIVEN. Trigger events: (a) Stage 4 kickoff OR (b) second contributor added to prod_locked_decisions writes; quarterly audit cadence in LD notes.
    # 201 SHORTCUT_PARTIAL_STATUS_NO_PCT_FIELD — closed 2026-05-07 (status=closed); v2 inventory (5→2 PARTIAL drop) closure trigger met. Removed from active classification dict; status='active' filter excludes it from query. Kept here as a comment for traceability.
    249: "EVENT_DRIVEN",   # SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418 — re-classified 2026-05-07 RARE_NEVER → PERIODIC+EVENT_DRIVEN per LD notes. INTERIM mapping: PERIODIC class does not exist yet (deferred — needs tech spec); pragmatic interim treats quarterly review as event trigger. Promote to PERIODIC class once landed.
    569: "RARE_NEVER",     # SHORTCUT_CODEQL_LOCK_FILE_0644_ACCEPT_V1 — "if/when refactored to 0o600 or CodeQL rule changes".
    570: "RARE_NEVER",     # SHORTCUT_CODEQL_REDOS_BOUNDED_INPUT_ACCEPT_V1 — "if/when regex refactored or CodeQL ReDoS rule gains length modeling".
    571: "RARE_NEVER",     # SHORTCUT_CODEQL_FILES_EXISTENCE_TEST_ACCEPT_V1 — "if/when endpoints validate against allowlist".
    572: "RARE_NEVER",     # SHORTCUT_CODEQL_LOCALHOST_FFMPEG_LIST_FORM_ACCEPT_V1 — "if/when ffmpeg paths validated upstream".
    # 573 SHORTCUT_CODEQL_VITE_BUILD_ARTIFACT_POSTMESSAGE_V1 closed 2026-05-08 (status=superseded);
    #     closure event fired in PR #8 commits f2b8eb7 (origin-allowlist) + b4c199f (bundle rebuild).
    574: "RARE_NEVER",     # SHORTCUT_CODEQL_REALPATH_SINK_INSIDE_CHECK_V1 — "if/when CodeQL py/path-injection gains sanitizer-recognition for resolve()-inside-containment-check idiom OR code refactored to helper".
    575: "RARE_NEVER",     # SHORTCUT_CODEQL_HTTP_RESPONSE_SPLITTING_TYPED_REBUILD_V1 — "if/when CodeQL py/http-response-splitting gains recognition for typed urllib.parse component rebuild OR response uses server-controlled origin".
}

RARE_NEVER_CAP_DAYS = 14
EVENT_DRIVEN_BACKSTOP_DAYS = 120  # safety net only; primary closure path is the named event.


def check_shortcut_ld_closure_dates(client, dry_run=False):
    """Scan active SHORTCUT_*_V1 LDs and surface those approaching their closure cap.

    Triggered weekly via cron. Cap policy (Kim directive 2026-05-07):

      - RARE_NEVER LDs (no scheduled trigger event): hard cap = date_locked + 14 days.
        Audit warns within 30 days of cap, criticals at <=7 days. (For 14-day-cap
        rows, that means the row goes critical the day it is locked or shortly after.)
      - EVENT_DRIVEN LDs (gated on a named event/PR/cutover): primary closure path
        is the LD-defined event. 120-day backstop retained as a safety surface so
        these don't silently age forever if the event never lands.

    Per LD 561 MASTER_ROADMAP_LIVING_DOC_V1's closure-surfacing requirement.
    Classification mapping enumerated in SHORTCUT_LD_CLASSIFICATION at module top.

    Returns:
        list of finding dicts (one per active SHORTCUT_*_V1 LD that triggers a warning).
    """
    today = datetime.now(timezone.utc).date()
    warn_threshold_days = 30
    critical_threshold_days = 7

    rows = client.get(
        "prod_locked_decisions",
        filters={
            "decision_key": {"_starts_with": "SHORTCUT_"},
            "status": {"_eq": "active"},
        },
        fields=["id", "decision_key", "date_locked", "decision_text", "notes"],
    )

    findings = []
    for ld in rows:
        date_locked_raw = ld.get("date_locked")
        ld_id = ld.get("id")
        ld_key = ld.get("decision_key")
        classification = SHORTCUT_LD_CLASSIFICATION.get(ld_id)
        if classification is None:
            findings.append({
                "ld_id": ld_id,
                "key": ld_key,
                "error": (
                    f"UNCLASSIFIED SHORTCUT LD: id={ld_id} key={ld_key!r} has no entry "
                    f"in SHORTCUT_LD_CLASSIFICATION. Add EVENT_DRIVEN or RARE_NEVER "
                    f"to weekly_preflight_audit.py before next audit run."
                ),
            })
            continue
        if not date_locked_raw:
            findings.append({
                "ld_id": ld_id,
                "key": ld_key,
                "error": "Missing date_locked field",
            })
            continue
        try:
            # Accept either YYYY-MM-DD or full ISO timestamp
            locked = datetime.strptime(str(date_locked_raw)[:10], "%Y-%m-%d").date()
            cap_days = (
                RARE_NEVER_CAP_DAYS if classification == "RARE_NEVER"
                else EVENT_DRIVEN_BACKSTOP_DAYS
            )
            cap = locked + timedelta(days=cap_days)
            days_until_cap = (cap - today).days
            if days_until_cap <= warn_threshold_days:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": classification,
                    "cap_days": cap_days,
                    "date_locked": locked.isoformat(),
                    "cap": cap.isoformat(),
                    "days_until_cap": days_until_cap,
                    "critical": days_until_cap <= critical_threshold_days,
                    "message": (
                        f"SHORTCUT LD {ld_key} (id={ld_id}) [{classification}, "
                        f"{cap_days}-day cap] approaches closure cap {cap.isoformat()} "
                        f"in {days_until_cap} days. Review per LD's closure mechanism."
                    ),
                })
        except (ValueError, TypeError) as e:
            findings.append({
                "ld_id": ld_id,
                "key": ld_key,
                "error": f"Could not parse date_locked={date_locked_raw!r}: {e}",
            })

    # Print findings
    print(f"[shortcut-audit] Active SHORTCUT_*_V1 LDs scanned: {len(rows)}")
    print(f"[shortcut-audit] Findings (within {warn_threshold_days}-day warn window or errored): {len(findings)}")
    for f in findings:
        if "error" in f:
            print(f"[shortcut-audit] WARN ld_id={f['ld_id']} key={f['key']}: {f['error']}")
        else:
            tag = "CRITICAL" if f.get("critical") else "WARN"
            print(f"[shortcut-audit] {tag} {f['message']}")

    # If any finding has days_until_cap <= 7, write a CRITICAL prod_blockers row
    # (de-duped by title prefix to avoid stacking on weekly reruns).
    for f in findings:
        if not f.get("critical"):
            continue
        title = f"SHORTCUT LD closure imminent: {f['key']} (id={f['ld_id']})"
        # Dedupe
        try:
            existing = client.get(
                "prod_blockers",
                filters={
                    "title": {"_eq": title},
                    "is_resolved": {"_eq": "false"},
                },
                limit=1,
            )
            if existing:
                print(f"[shortcut-audit] dedupe: blocker already exists for {f['key']}")
                continue
        except Exception as e:
            print(f"[shortcut-audit] WARN dedupe lookup failed: {e!r}")

        if dry_run:
            print(f"[shortcut-audit] [DRY-RUN] would create blocker: {title}")
            continue

        try:
            client._request("POST", "/items/prod_blockers", data={
                "title": title,
                "description": f["message"] + "\n\nAuto-surfaced by weekly_preflight_audit.py::check_shortcut_ld_closure_dates() per LD 561.",
                "severity": "critical",
                "is_resolved": False,
            })
            print(f"[shortcut-audit] CREATED blocker: {title}")
        except DirectusError as e:
            print(f"[shortcut-audit] ERROR creating blocker for {f['key']}: {e}")

    return findings


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

    # Sub-check: SHORTCUT_*_V1 closure-cap surfacing (LD 561 MASTER_ROADMAP_LIVING_DOC_V1).
    # Reads active SHORTCUT_*_V1 LDs, computes cap per SHORTCUT_LD_CLASSIFICATION
    # (RARE_NEVER = 14 days, EVENT_DRIVEN = 120-day backstop), surfaces findings
    # within 30 days. If any are within 7 days, creates a CRITICAL prod_blockers
    # row (de-duped). Best-effort: never fails the main audit. Cap policy locked
    # 2026-05-07 (Kim directive — replaces uniform 120-day proxy).
    try:
        shortcut_findings = check_shortcut_ld_closure_dates(client, dry_run=dry_run)
        summary["shortcut_ld_findings"] = shortcut_findings
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: check_shortcut_ld_closure_dates sub-check failed: {e!r}")
        summary["shortcut_ld_findings"] = {"error": repr(e)}

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
