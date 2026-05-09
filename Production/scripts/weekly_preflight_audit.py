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

from dateutil.relativedelta import relativedelta

# Policy-lock date for the 14-day RARE_NEVER SHORTCUT closure cap (Kim directive 2026-05-07).
# LDs locked BEFORE this date predate the policy and emit a softer GRANDFATHER_REVIEW
# finding once for one-time triage; once triaged (CLOSE / AMEND / re-classify) they
# never re-fire. LDs locked ON or AFTER this date get the normal 14-day cap.
SHORTCUT_CAP_POLICY_LOCK_DATE = date(2026, 5, 7)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.normpath(os.path.join(THIS_DIR, "..", "tools"))
sys.path.insert(0, TOOLS_DIR)

from credentials_lib.credentials import load_credentials  # noqa: E402
from credentials_lib.directus import DirectusClient, DirectusError  # noqa: E402


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
    249: "PERIODIC",       # SHORTCUT_IDENTITY_PLATFORM_EVALUATION_20260418 — PERIODIC class per PERIODIC_CLASS_TECH_SPEC_v3 §B5 (quarterly identity-platform review). Directus MUST set review_cadence + next_review_date; NULL cadence surfaces PERIODIC_INVALID_CONFIGURATION.
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


def _normalize_review_cadence(cadence: str) -> str:
    return (cadence or "").strip().lower().replace(" ", "").replace("_", "-")


def _relativedelta_for_review_cadence(cadence: str) -> relativedelta:
    """§B4 / §B5 — calendar-aware step (replaces fixed +30-day approximations)."""
    c = _normalize_review_cadence(cadence)
    if c == "monthly":
        return relativedelta(months=1)
    if c == "quarterly":
        return relativedelta(months=3)
    if c in ("semi-annually", "semiannually"):
        return relativedelta(months=6)
    if c == "annually":
        return relativedelta(years=1)
    raise ValueError(f"not a calendar review_cadence: {cadence!r}")


def add_review_cadence_to_date(base: date, cadence: str) -> date:
    """Return ``base`` advanced by one review period for ``cadence`` (PERIODIC §A1)."""
    return base + _relativedelta_for_review_cadence(cadence)


def is_audit_eligible_periodic_row(classification: str, ld_row: dict) -> bool:
    """§B1(b) — explicit two-arg predicate; never reads ld_row['classification']."""
    if classification != "PERIODIC":
        return False
    cadence = ld_row.get("review_cadence")
    if cadence is None:
        return False
    if _normalize_review_cadence(str(cadence)) in ("none", "event-driven"):
        return False
    try:
        _relativedelta_for_review_cadence(str(cadence))
    except ValueError:
        return False
    return True


def _finding_severity_str(finding: dict) -> str:
    """§B3 — canonical string severity with boolean back-compat."""
    return finding.get("severity") or (
        "critical" if finding.get("critical") else "warn"
    )


def check_shortcut_ld_closure_dates(client, dry_run=False):
    """Scan active SHORTCUT_*_V1 LDs and surface those approaching their closure cap.

    Triggered weekly via cron. Cap policy (Kim directive 2026-05-07):

      - RARE_NEVER LDs (no scheduled trigger event): hard cap = date_locked + 14 days.
        Audit warns within 30 days of cap, criticals at <=7 days. (For 14-day-cap
        rows, that means the row goes critical the day it is locked or shortly after.)
      - EVENT_DRIVEN LDs (gated on a named event/PR/cutover): primary closure path
        is the LD-defined event. 120-day backstop retained as a safety surface so
        these don't silently age forever if the event never lands.
      - PERIODIC LDs (PERIODIC_CLASS_TECH_SPEC_v3): review_cadence + next_review_date
        drive calendar surfacing; NULL cadence on PERIODIC is a critical
        PERIODIC_INVALID_CONFIGURATION finding (never silent skip).

    Prospective-only cap (meta-fix B + C, 2026-05-07):
      - The 14-day RARE_NEVER cap applies ONLY to LDs locked on/after
        SHORTCUT_CAP_POLICY_LOCK_DATE (2026-05-07).
      - LDs locked BEFORE that date AND classified RARE_NEVER are GRANDFATHERED:
        on first audit run after the policy-lock they emit ONE softer
        GRANDFATHER_REVIEW finding (severity tag 'GRANDFATHER_REVIEW' — neither
        WARN nor CRITICAL) prompting one-time triage (CLOSE / AMEND /
        re-classify). Once triaged in Directus (status=closed OR re-classified
        to EVENT_DRIVEN), they drop out of the active query OR fall under
        EVENT_DRIVEN's 120-day backstop and stop re-firing under the cap.
      - EVENT_DRIVEN LDs use the 120-day backstop regardless of date_locked.

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
        fields=[
            "id",
            "decision_key",
            "date_locked",
            "decision_text",
            "notes",
            "review_cadence",
            "next_review_date",
            "last_reviewed_date",
        ],
    )

    findings = []
    for ld in rows:
        date_locked_raw = ld.get("date_locked")
        ld_id = ld.get("id")
        ld_key = ld.get("decision_key")
        classification = SHORTCUT_LD_CLASSIFICATION.get(ld_id, "UNCLASSIFIED")
        if classification == "UNCLASSIFIED":
            findings.append({
                "ld_id": ld_id,
                "key": ld_key,
                "error": (
                    f"UNCLASSIFIED SHORTCUT LD: id={ld_id} key={ld_key!r} has no entry "
                    f"in SHORTCUT_LD_CLASSIFICATION. Add PERIODIC, EVENT_DRIVEN, or "
                    f"RARE_NEVER to weekly_preflight_audit.py before next audit run."
                ),
            })
            continue

        # §B1 — stamp registry-derived class before any predicate reads it.
        ld["_classification"] = classification

        # §4.2 v3 — PERIODIC branch (calendar review surfacing; skips closure-cap path).
        if classification == "PERIODIC":
            cadence = ld.get("review_cadence")
            if cadence is None:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": "PERIODIC",
                    "finding_type": "PERIODIC_INVALID_CONFIGURATION",
                    "issue": "PERIODIC_INVALID_CONFIGURATION",
                    "critical": True,
                    "severity": "critical",
                    "message": (
                        f"PERIODIC SHORTCUT LD id={ld_id} ({ld_key}) has "
                        f"review_cadence=NULL — invalid for PERIODIC class. "
                        f"Set review_cadence ∈ {{monthly, quarterly, semi-annually, "
                        f"annually, none, event-driven}} per PERIODIC_CLASS_TECH_SPEC_v3 "
                        f"§A4, then re-run audit. NULL is reserved for non-PERIODIC LDs."
                    ),
                })
                continue

            cadence_norm = _normalize_review_cadence(str(cadence))
            if cadence_norm in ("none", "event-driven"):
                continue

            try:
                _relativedelta_for_review_cadence(str(cadence))
            except ValueError:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": "PERIODIC",
                    "finding_type": "PERIODIC_INVALID_CADENCE_VALUE",
                    "issue": "PERIODIC_INVALID_CADENCE_VALUE",
                    "critical": True,
                    "severity": "critical",
                    "message": (
                        f"PERIODIC SHORTCUT LD id={ld_id} ({ld_key}) has unknown "
                        f"review_cadence={cadence!r}. Expected monthly, quarterly, "
                        f"semi-annually, or annually (or opt-out none/event-driven)."
                    ),
                })
                continue

            next_review = ld.get("next_review_date")
            if not next_review:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": "PERIODIC",
                    "finding_type": "PERIODIC_MISSING_NEXT_REVIEW_DATE",
                    "issue": "PERIODIC_MISSING_NEXT_REVIEW_DATE",
                    "critical": True,
                    "severity": "critical",
                    "message": (
                        f"PERIODIC SHORTCUT LD id={ld_id} ({ld_key}) missing required "
                        f"next_review_date for cadence={cadence!r}. Set this field "
                        f"before next audit run."
                    ),
                })
                continue

            try:
                next_review_date = datetime.strptime(str(next_review)[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError) as e:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": "PERIODIC",
                    "finding_type": "PERIODIC_INVALID_NEXT_REVIEW_DATE",
                    "issue": "PERIODIC_INVALID_NEXT_REVIEW_DATE",
                    "critical": True,
                    "severity": "critical",
                    "value": next_review,
                    "error": str(e),
                    "message": (
                        f"PERIODIC SHORTCUT LD id={ld_id} ({ld_key}) has unparseable "
                        f"next_review_date={next_review!r}: {e}. Fix the field then re-run."
                    ),
                })
                continue

            days_until_review = (next_review_date - today).days
            if days_until_review <= 0:
                days_overdue = abs(days_until_review)
                is_crit = days_overdue >= 7
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": "PERIODIC",
                    "next_review": next_review_date.isoformat(),
                    "days_overdue": days_overdue,
                    "critical": is_crit,
                    "severity": "critical" if is_crit else "warn",
                    "message": (
                        f"PERIODIC LD {ld_key} (id={ld_id}) review OVERDUE by "
                        f"{days_overdue} days "
                        f"[{'CRITICAL' if is_crit else 'WARN'}]. "
                        f"Next-review-date was {next_review_date.isoformat()}."
                    ),
                })
            elif days_until_review <= 7:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": "PERIODIC",
                    "next_review": next_review_date.isoformat(),
                    "days_until_review": days_until_review,
                    "critical": False,
                    "severity": "warn",
                    "message": (
                        f"PERIODIC LD {ld_key} (id={ld_id}) review due in "
                        f"{days_until_review} days ({next_review_date.isoformat()})."
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

            # Prospective-only cap (meta-fix B + C, 2026-05-07): the 14-day
            # RARE_NEVER cap applies only to LDs locked ON or AFTER the policy
            # lock date. RARE_NEVER LDs locked before the policy date emit a
            # softer GRANDFATHER_REVIEW finding once for one-time triage,
            # rather than the standard cap CRITICAL. EVENT_DRIVEN LDs use the
            # 120-day backstop regardless of date_locked.
            policy_age = (locked - SHORTCUT_CAP_POLICY_LOCK_DATE).days
            if classification == "RARE_NEVER" and policy_age < 0:
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": classification,
                    "date_locked": locked.isoformat(),
                    "policy_age_days": policy_age,
                    "grandfather_review": True,
                    "message": (
                        f"SHORTCUT LD {ld_key} (id={ld_id}) is RARE_NEVER but "
                        f"predates the 14-day cap policy "
                        f"(policy locked {SHORTCUT_CAP_POLICY_LOCK_DATE.isoformat()}, "
                        f"date_locked={locked.isoformat()}, policy_age={policy_age} days). "
                        f"One-time triage required: CLOSE / AMEND / re-classify. "
                        f"Once triaged, this finding will not re-fire."
                    ),
                })
                continue

            cap_days = (
                RARE_NEVER_CAP_DAYS if classification == "RARE_NEVER"
                else EVENT_DRIVEN_BACKSTOP_DAYS
            )
            cap = locked + timedelta(days=cap_days)
            days_until_cap = (cap - today).days
            if days_until_cap <= warn_threshold_days:
                is_cap_crit = days_until_cap <= critical_threshold_days
                findings.append({
                    "ld_id": ld_id,
                    "key": ld_key,
                    "classification": classification,
                    "cap_days": cap_days,
                    "date_locked": locked.isoformat(),
                    "cap": cap.isoformat(),
                    "days_until_cap": days_until_cap,
                    "critical": is_cap_crit,
                    "severity": "critical" if is_cap_crit else "warn",
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
        elif f.get("grandfather_review"):
            print(f"[shortcut-audit] GRANDFATHER_REVIEW {f['message']}")
        else:
            # §B3 — string severity canonical; boolean critical retained for back-compat.
            tag = _finding_severity_str(f).upper()
            print(f"[shortcut-audit] {tag} {f['message']}")

    # If any finding is severity critical, write a prod_blockers row
    # (de-duped by title prefix to avoid stacking on weekly reruns).
    for f in findings:
        if _finding_severity_str(f) != "critical":
            continue
        if f.get("classification") == "PERIODIC":
            title = f"SHORTCUT PERIODIC audit critical: {f['key']} (id={f['ld_id']})"
        else:
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


# ---------------------------------------------------------------------------
# PR-merge auto-close sub-check (LD 576 MERGE_CLEANUP_AUTO_CLOSE_PROTOCOL_V1).
#
# Scans active EVENT_DRIVEN SHORTCUT_*_V1 LDs whose closure event mentions
# a PR merge. For each, queries `gh pr list --state merged` on the resolved
# repo and matches recently-merged PRs against the LD's identifying tokens.
# On match: PATCHes the LD to status='superseded' (idempotent) and logs the
# auto-close. Failure modes documented in LD 576 decision_text.
#
# Repository resolution heuristic (in priority order):
#   1. Explicit `<owner>/<repo>` in LD notes (regex)
#   2. decision_key contains TOOLING -> kimhyla/mindfulnest-tooling
#   3. decision_key contains RN or MAIN_APP -> RN repo (TBD)
#   4. else: WARN, no auto-close
# ---------------------------------------------------------------------------

# PR-merge phrasing that indicates the closure event is keyed on a PR merging
# to main (vs. e.g. "production cycle" or "post-launch traffic").
_PR_MERGE_PATTERNS = [
    re.compile(r"\bPR\s+#?\d+\b", re.IGNORECASE),
    re.compile(r"\bPR\s+merges?\s+to\s+main\b", re.IGNORECASE),
    re.compile(r"\bgap[-\s]?fix\s+PR\b", re.IGNORECASE),
    re.compile(r"\bmerges?\s+to\s+main\b", re.IGNORECASE),
]
_REPO_PATTERN = re.compile(r"\b([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)(?:\s+repo|\s+repository)?\b")
# Compound-identifier shape: must start uppercase and contain at least one
# underscore. Used INSIDE structured closure-event hint patterns only — never
# scraped freely from decision_text/notes (LD-576-amend-1, see below).
_COMPOUND_IDENT = r"([A-Z][A-Z0-9]+(?:_[A-Za-z0-9]+)+)"
# Structured closure-event hint patterns — phrases that explicitly name the
# closure event in the LD's notes/decision_text. Only identifiers captured
# INSIDE one of these patterns are used as match tokens; arbitrary UPPER_SNAKE
# in the LD's prose is NEVER mined.
#
# 2026-05-09 amendment (LD-576-amend-1, LD-565 false-close incident):
# Previously, _ld_identifier_tokens() scraped EVERY UPPER_SNAKE token from
# the LD's decision_text/notes via _IDENTIFIER_TOKEN_PATTERN. That caused
# LD-565 (SHORTCUT_TOOLING_REPO_PUBLIC_FOR_CODESCAN_V1) to false-close on
# 2026-05-09 when kimhyla/mindfulnest-tooling#8 merged: the LD's
# decision_text mentioned `API_KEYS_MASTER` (related-context reference, not
# a closure event), PR #8's body also mentioned `API_KEYS_MASTER.md`, and
# the matcher reported `body:API_KEYS_MASTER`. Closure criteria for LD-565
# (tooling private flip OR Enterprise CodeQL OR 2026-09-07 hard cap) were
# NOT met. The close was reverted manually.
_CLOSURE_EVENT_HINT_PATTERNS = [
    re.compile(rf"\bgates?\s+on\s+{_COMPOUND_IDENT}\s+(?:PR\s+merge|merges?)\b", re.IGNORECASE),
    re.compile(rf"\bcloses?\s+(?:on|when)\s+{_COMPOUND_IDENT}\s+(?:PR\s+)?merges?\b", re.IGNORECASE),
    re.compile(rf"\bclosure\s+event\s*[:\-]\s*{_COMPOUND_IDENT}\s+PR\s+merges?\b", re.IGNORECASE),
    re.compile(rf"\b{_COMPOUND_IDENT}\s+PR\s+merges?\s+to\s+main\b", re.IGNORECASE),
]
# Explicit PR reference in LD notes/decision_text — e.g. "kimhyla/mindfulnest-tooling#8".
# A PR matching this exact (repo, number) is treated as a strong closure signal.
_EXPLICIT_PR_REF_PATTERN = re.compile(
    r"\b([a-zA-Z][a-zA-Z0-9_-]{2,38}/[a-zA-Z0-9_.-]+)#(\d+)\b"
)
# Repo hints in LD notes/decision_text that map to specific repos. Order matters:
# more-specific phrases first.
_REPO_HINT_PATTERNS = [
    (re.compile(r"V59_CICD_GAP_FIX|gap[-\s]?fix\s+PR|tooling\s+repo\s+PR|storyboard\s+(?:fix|bug)", re.IGNORECASE), "kimhyla/mindfulnest-tooling"),
    (re.compile(r"mindfulnest[-_]?ios|RN\s+repo|main\s+app\s+repo", re.IGNORECASE), "kimhyla/mindfulnest-ios"),
]


def _has_pr_merge_signal(text):
    """Return True if any _PR_MERGE_PATTERNS matches the given text."""
    if not text:
        return False
    return any(p.search(text) for p in _PR_MERGE_PATTERNS)


def _resolve_repo_for_ld(ld):
    """Best-effort repo resolution. Returns owner/repo string or None."""
    notes = (ld.get("notes") or "")
    decision_text = (ld.get("decision_text") or "")
    decision_key = (ld.get("decision_key") or "")
    haystack = f"{notes}\n{decision_text}"
    # Strategy 1: explicit owner/repo in notes/decision_text. Filter out path-like
    # matches (Production/docs/foo.md) by checking the owner segment looks like a
    # GitHub user/org (no dots, no leading/trailing punctuation, length 3-39).
    for m in _REPO_PATTERN.finditer(haystack):
        candidate = m.group(1)
        owner, repo = candidate.split("/", 1)
        # GitHub owner constraint: 1-39 chars, alphanumeric + hyphens (no dots).
        if "." in owner or not (3 <= len(owner) <= 39) or "/" in repo:
            continue
        # Exclude common path-prefix false positives.
        if owner in {"Production", "docs", "Canon", "App", "Arc", "Storyboards"}:
            continue
        # Require a MindfulNest-flavored signal in the candidate to avoid
        # picking up unrelated github-style strings buried in notes.
        cand_l = candidate.lower()
        if "mindfulnest" in cand_l or "mn-" in cand_l or owner.lower().startswith("kimhyla"):
            return candidate
    # Strategy 2: hint patterns (LD notes/decision_text mention an identifier
    # that's known to map to a specific repo, e.g. "V59_CICD_GAP_FIX" -> tooling).
    for pat, repo in _REPO_HINT_PATTERNS:
        if pat.search(haystack):
            return repo
    # Strategy 3: decision_key heuristic.
    upper_key = decision_key.upper()
    if "TOOLING" in upper_key:
        return "kimhyla/mindfulnest-tooling"
    if ("MAIN_APP" in upper_key or "RN_REPO" in upper_key or "_RN_" in upper_key):
        return "kimhyla/mindfulnest-ios"
    return None


def _list_recently_merged_prs(repo, limit=30):
    """Run `gh pr list --state merged` for repo. Returns list of dicts.

    Returns [] on any error (network, auth, repo not found). Errors logged
    but never raise — the sub-check must not crash the main audit.
    """
    import subprocess
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--repo", repo,
                "--state", "merged",
                "--limit", str(limit),
                "--json", "number,title,body,headRefName,mergedAt,mergeCommit",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            print(f"[pr-merge-audit] gh CLI error for {repo}: {result.stderr.strip()[:200]}")
            return []
        return json.loads(result.stdout) if result.stdout.strip() else []
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[pr-merge-audit] gh query failed for {repo}: {type(e).__name__}: {e}")
        return []


def _ld_closure_signals(ld):
    """Extract STRUCTURED closure-event signals from an LD.

    Returns a dict with three lists:
      - decision_keys: literals (decision_key + de-suffixed _V<N> form) that, if
        found in PR title/body/branch, indicate a closure match.
      - explicit_pr_refs: list of (owner_repo, pr_number) tuples extracted from
        LD notes/decision_text via the ``owner/repo#NN`` pattern. A PR matching
        this exact (repo, number) is treated as a strong closure signal.
      - structured_event_tokens: identifier tokens parsed from designated phrase
        patterns such as ``gates on X PR merge`` or ``closure event: X``. Only
        identifiers captured inside one of those phrases qualify.

    CRITICAL (LD-576-amend-1, 2026-05-09): this function does NOT return
    arbitrary UPPER_SNAKE tokens scraped from the LD's prose. The previous
    `_ld_identifier_tokens` did, which caused the LD-565 false-close when
    PR-#8's body shared an incidental `API_KEYS_MASTER` substring with LD-565's
    decision_text. The matcher must only act on signals that the LD author
    deliberately put in the closure-event grammar.
    """
    signals = {
        "decision_keys": [],
        "explicit_pr_refs": [],
        "structured_event_tokens": [],
    }
    decision_key = ld.get("decision_key") or ""
    if decision_key:
        signals["decision_keys"].append(decision_key)
        stripped = re.sub(r"_V\d+$", "", decision_key, flags=re.IGNORECASE)
        if stripped and stripped != decision_key:
            signals["decision_keys"].append(stripped)

    haystack = f"{ld.get('notes') or ''}\n{ld.get('decision_text') or ''}"

    for m in _EXPLICIT_PR_REF_PATTERN.finditer(haystack):
        owner_repo = m.group(1)
        try:
            pr_number = int(m.group(2))
        except (TypeError, ValueError):
            continue
        owner = owner_repo.split("/", 1)[0]
        # Same path-prefix guard used in _resolve_repo_for_ld — exclude things
        # like "Production/docs#5" that aren't real GitHub refs.
        if "." in owner or not (3 <= len(owner) <= 39):
            continue
        if owner in {"Production", "docs", "Canon", "App", "Arc", "Storyboards"}:
            continue
        signals["explicit_pr_refs"].append((owner_repo, pr_number))

    for pat in _CLOSURE_EVENT_HINT_PATTERNS:
        for m in pat.finditer(haystack):
            tok = m.group(1)
            if tok and tok not in signals["structured_event_tokens"]:
                signals["structured_event_tokens"].append(tok)

    return signals


def _match_pr_to_ld(pr, repo, signals):
    """Return matched_field (str) if PR matches one of the LD's closure signals.

    Match precedence:
      1. explicit_pr_refs        — strongest; LD literally cited this repo#NN.
      2. decision_keys           — PR title/body/branch contains the LD's
                                   decision_key (or its _V<N>-stripped form).
      3. structured_event_tokens — PR title/body/branch contains an identifier
                                   the LD designated as the closure-event token
                                   (parsed from `gates on X PR merge` etc.).

    Returns None if no signal matches. Critically, this function NEVER falls
    through to scraping arbitrary tokens from the LD's prose — the signals dict
    is the sole source of match material.
    """
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    branch = pr.get("headRefName") or ""

    pr_number = pr.get("number")
    if pr_number is not None:
        try:
            pr_number_int = int(pr_number)
        except (TypeError, ValueError):
            pr_number_int = None
        if pr_number_int is not None:
            for ref_repo, ref_num in signals.get("explicit_pr_refs", []):
                if ref_repo == repo and ref_num == pr_number_int:
                    return f"explicit_pr_ref:{ref_repo}#{ref_num}"

    title_l = title.lower()
    body_l = body.lower()
    branch_l = branch.lower()

    for dk in signals.get("decision_keys", []):
        dk_l = dk.lower()
        if dk_l in title_l:
            return f"title:{dk}"
        if dk_l in body_l:
            return f"body:{dk}"
        if dk_l in branch_l:
            return f"headRefName:{dk}"

    for tok in signals.get("structured_event_tokens", []):
        if tok in title:
            return f"title:{tok}"
        if tok in body:
            return f"body:{tok}"
        if tok.lower() in branch_l:
            return f"headRefName:{tok}"

    return None


def check_pr_merge_closure_events(client, dry_run=False):
    """Auto-close active EVENT_DRIVEN SHORTCUT LDs whose PR-merge closure event has fired.

    Per LD 576 MERGE_CLEANUP_AUTO_CLOSE_PROTOCOL_V1. Triggered weekly via cron.

    For each active SHORTCUT_*_V1 LD classified EVENT_DRIVEN whose notes or
    decision_text mention a PR merge:
      1. Resolve target GitHub repo (notes-explicit or decision_key heuristic).
      2. Query `gh pr list --state merged --limit 30` for recently-merged PRs.
      3. Match PR title/body/branch against LD identifier tokens (decision_key
         and UPPER_SNAKE identifiers extracted from LD text).
      4. On match: PATCH the LD to status='superseded' (idempotent re-read first)
         and POST an app_activity_log row recording the auto-close.

    Returns:
        dict summary with keys: scanned, eligible, matched, closed, warns, errors.
    """
    today = datetime.now(timezone.utc).date()

    rows = client.get(
        "prod_locked_decisions",
        filters={
            "decision_key": {"_starts_with": "SHORTCUT_"},
            "status": {"_eq": "active"},
        },
        fields=["id", "decision_key", "date_locked", "decision_text", "notes"],
    )

    summary = {
        "scanned": len(rows),
        "eligible": 0,
        "matched": 0,
        "closed": 0,
        "warns": [],
        "errors": [],
        "matches": [],
        "dry_run": dry_run,
    }

    for ld in rows:
        ld_id = ld.get("id")
        ld_key = ld.get("decision_key")
        classification = SHORTCUT_LD_CLASSIFICATION.get(ld_id)
        if classification != "EVENT_DRIVEN":
            continue
        notes = ld.get("notes") or ""
        decision_text = ld.get("decision_text") or ""
        if not _has_pr_merge_signal(notes + "\n" + decision_text):
            continue
        summary["eligible"] += 1

        repo = _resolve_repo_for_ld(ld)
        if not repo:
            warn = (
                f"ld_id={ld_id} key={ld_key}: PR-merge signal present but repo "
                f"could not be resolved from notes or decision_key heuristic"
            )
            summary["warns"].append(warn)
            print(f"[pr-merge-audit] WARN {warn}")
            continue

        prs = _list_recently_merged_prs(repo, limit=30)
        if not prs:
            # Either no recent merges or gh failure; both are non-fatal.
            continue

        ld_signals = _ld_closure_signals(ld)
        # Eligibility hard-stop: if the LD has no structured closure signals at
        # all (no decision_key match material, no explicit PR ref, no parsed
        # `gates on X PR merge` hint), skip auto-close entirely. This is the
        # post-LD-576-amend-1 backstop — a PR-merge signal in prose alone is
        # not enough; the LD must declare a structured closure event for the
        # matcher to have anything to work with.
        if not (
            ld_signals["decision_keys"]
            or ld_signals["explicit_pr_refs"]
            or ld_signals["structured_event_tokens"]
        ):
            warn = (
                f"ld_id={ld_id} key={ld_key}: PR-merge signal present in prose "
                f"but no structured closure-event grammar (no `gates on X PR "
                f"merge`, no explicit `repo#NN`); skipping auto-close per "
                f"LD-576-amend-1."
            )
            summary["warns"].append(warn)
            print(f"[pr-merge-audit] WARN {warn}")
            continue
        matches = []
        for pr in prs:
            matched_field = _match_pr_to_ld(pr, repo, ld_signals)
            if matched_field:
                matches.append({"pr": pr, "matched_field": matched_field})

        if not matches:
            continue
        summary["matched"] += 1

        # Multiple matches: log all but act on the most-recent merge.
        if len(matches) > 1:
            warn = (
                f"ld_id={ld_id} key={ld_key}: {len(matches)} PRs matched in repo "
                f"{repo}; using most recent."
            )
            summary["warns"].append(warn)
            print(f"[pr-merge-audit] WARN {warn}")
        # Sort by mergedAt descending; pick first.
        matches.sort(key=lambda m: m["pr"].get("mergedAt") or "", reverse=True)
        chosen = matches[0]
        chosen_pr = chosen["pr"]
        merge_sha = (chosen_pr.get("mergeCommit") or {}).get("oid", "")
        merged_at = chosen_pr.get("mergedAt", "")
        pr_number = chosen_pr.get("number")
        matched_field = chosen["matched_field"]

        match_record = {
            "ld_id": ld_id,
            "key": ld_key,
            "repo": repo,
            "pr_number": pr_number,
            "pr_title": chosen_pr.get("title", "")[:200],
            "merge_sha": merge_sha,
            "merged_at": merged_at,
            "matched_field": matched_field,
        }
        summary["matches"].append(match_record)
        # Surface the match tier (explicit_pr_ref / decision_key / structured_event_token)
        # so ad-hoc reviewers can verify the signal class before PATCH lands.
        match_tier = matched_field.split(":", 1)[0] if ":" in matched_field else matched_field
        print(
            f"[pr-merge-audit] MATCH ld_id={ld_id} key={ld_key} -> "
            f"{repo}#{pr_number} (merged {merged_at}; matched via {matched_field}; "
            f"tier={match_tier})"
        )
        print(
            f"[pr-merge-audit]   ld_signals: decision_keys={ld_signals['decision_keys']} "
            f"explicit_pr_refs={ld_signals['explicit_pr_refs']} "
            f"structured_event_tokens={ld_signals['structured_event_tokens']}"
        )

        if dry_run:
            print(f"[pr-merge-audit] [DRY-RUN] would PATCH ld_id={ld_id} status=superseded")
            continue

        # Idempotency: re-read status before PATCH.
        try:
            current = client.get(
                "prod_locked_decisions",
                filters={"id": {"_eq": ld_id}},
                fields=["id", "status"],
                limit=1,
            )
            if current and current[0].get("status") != "active":
                print(
                    f"[pr-merge-audit] dedupe: ld_id={ld_id} status="
                    f"{current[0].get('status')} (not active); skipping PATCH."
                )
                continue
        except Exception as e:
            err = f"ld_id={ld_id}: idempotency re-read failed: {e!r}"
            summary["errors"].append(err)
            print(f"[pr-merge-audit] ERROR {err}")
            continue

        closure_note = (
            f"\n\n[AUTO-CLOSE 2026-{today.month:02d}-{today.day:02d} via "
            f"weekly_preflight_audit.py::check_pr_merge_closure_events per LD 576] "
            f"Closure event fired: {repo}#{pr_number} merged {merged_at} "
            f"(commit {merge_sha[:12]}). Matched signal: {matched_field}."
        )
        existing_notes = (ld.get("notes") or "")
        try:
            client.update(
                "prod_locked_decisions",
                ld_id,
                {
                    "status": "superseded",
                    "date_superseded": today.isoformat(),
                    "notes": existing_notes + closure_note,
                },
            )
            summary["closed"] += 1
            print(f"[pr-merge-audit] CLOSED ld_id={ld_id} key={ld_key}")
        except DirectusError as e:
            err = f"ld_id={ld_id}: PATCH failed: {e}"
            summary["errors"].append(err)
            print(f"[pr-merge-audit] ERROR {err}")
            continue

        # Activity log row (best-effort).
        try:
            client._request("POST", "/items/app_activity_log", data={
                "feature_id": 5,
                "action": "auto-close SHORTCUT LD via PR-merge match",
                "details": json.dumps({
                    "ld_id": ld_id,
                    "decision_key": ld_key,
                    "repo": repo,
                    "pr_number": pr_number,
                    "merge_sha": merge_sha,
                    "merged_at": merged_at,
                    "matched_field": matched_field,
                    "protocol_ld": 576,
                }),
                "performed_by": "weekly_preflight_audit.py::check_pr_merge_closure_events",
            })
        except DirectusError as e:
            err = f"ld_id={ld_id}: activity log write failed (non-fatal): {e}"
            summary["errors"].append(err)
            print(f"[pr-merge-audit] WARN {err}")

    print(
        f"[pr-merge-audit] DONE — scanned={summary['scanned']} "
        f"eligible={summary['eligible']} matched={summary['matched']} "
        f"closed={summary['closed']} warns={len(summary['warns'])} "
        f"errors={len(summary['errors'])} dry_run={dry_run}"
    )
    return summary


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

    # Sub-check: PR-merge auto-close (LD 576 MERGE_CLEANUP_AUTO_CLOSE_PROTOCOL_V1).
    # Scans active EVENT_DRIVEN SHORTCUT_*_V1 LDs whose closure event mentions
    # a PR merge; runs `gh pr list --state merged` per resolved repo; matches
    # on PR title/body/branch against LD identifier tokens; on match, PATCHes
    # the LD to status='superseded' (idempotent re-read first) and writes an
    # app_activity_log row. Best-effort: never fails the main audit.
    try:
        pr_merge_summary = check_pr_merge_closure_events(client, dry_run=dry_run)
        summary["pr_merge_closures"] = pr_merge_summary
    except Exception as e:  # pragma: no cover
        print(f"[audit] WARNING: check_pr_merge_closure_events sub-check failed: {e!r}")
        summary["pr_merge_closures"] = {"error": repr(e)}

    return summary


def run_pr_merge_only(dry_run):
    """Ad-hoc invocation of just check_pr_merge_closure_events. Per LD-576-amend-1
    this defaults to dry-run and requires explicit --commit to mutate, so engineers
    can inspect the matcher's behavior without risking a false-close."""
    creds = load_credentials("supabase_directus_creds.md")
    client = DirectusClient(
        url=creds["DIRECTUS_URL"],
        admin_token=creds["DIRECTUS_ADMIN_TOKEN"],
    )
    print(
        f"[pr-merge-only] invoking check_pr_merge_closure_events "
        f"dry_run={dry_run} (--commit to mutate)"
    )
    summary = check_pr_merge_closure_events(client, dry_run=dry_run)
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write blockers")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default 7)")
    parser.add_argument("--hours", type=int, default=None, help="Lookback window in hours (overrides --days if set — for session-end audits)")
    parser.add_argument(
        "--pr-merge-only",
        action="store_true",
        help="Run only the PR-merge auto-close sub-check (LD-576). Defaults to "
             "dry-run; pass --commit to actually mutate. Designed for ad-hoc "
             "matcher inspection without risking a false-close (LD-576-amend-1).",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Only relevant with --pr-merge-only: opt in to writes. Without "
             "this flag, --pr-merge-only operates in dry-run.",
    )
    args = parser.parse_args()

    if args.pr_merge_only:
        # Ad-hoc PR-merge inspection path: dry-run by default. Explicit --commit
        # required to mutate. The weekly cron path (no --pr-merge-only flag)
        # is unchanged — it still uses --dry-run as its sole opt-out.
        dry = not args.commit
        run_pr_merge_only(dry_run=dry)
        return

    if args.commit:
        print("[audit] WARN: --commit has no effect without --pr-merge-only; ignoring.")

    run_audit(days=args.days, hours=args.hours, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
