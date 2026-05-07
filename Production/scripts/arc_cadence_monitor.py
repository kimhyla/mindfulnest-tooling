#!/usr/bin/env python3
"""
Arc Release Cadence Monitor — Stream F Item 7

Checks whether each arc (2-10) is CDN-live in time for the fastest-possible
family (3×/week by default per LD-352) to need it.

CDN-live signal: Firestore `arc_manifests/{arcId}` document existence
(written by `upload_module.py arc-manifest` command per LD-406).

Algorithm:
1. Read launch date from prod_locked_decisions (key LAUNCH_DATE_V1).
   If not found → print info message and exit 0 (inert before launch locks).
2. Read schedule parameters from prod_arc_release_schedule (falls back to
   generate_arc_release_schedule.py defaults if migration not yet applied).
3. For each arc 2-10: check Firestore arc_manifests/{arcId}.
4. For arcs NOT yet live that are within (production_lead + buffer) weeks of
   their CDN deadline: create/update CRITICAL app_blockers row.
5. For arcs that ARE live and have an open blocker: resolve it.
6. Print summary table. Write prod_activity_log entry.

Exit codes:
    0 — ran cleanly (whether or not blockers were filed)
    1 — exception; stderr has details, prod_activity_log WARN entry written

Usage:
    python3 arc_cadence_monitor.py [--dry-run] [--verbose]
    python3 arc_cadence_monitor.py --dry-run   # no writes; shows what would happen
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROD_DIR = os.path.normpath(os.path.join(THIS_DIR, ".."))
LIB_DIR = os.path.join(PROD_DIR, "lib")
sys.path.insert(0, LIB_DIR)

from directus_admin_client import DirectusAdminClient  # noqa: E402

# ─── Constants ────────────────────────────────────────────────────────────────

FIREBASE_PROJECT = "mindfulnestkids"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}"
    f"/databases/(default)/documents"
)

# Arc 1 is bundled at install (LD-282); schedule covers Arcs 2-10.
ARCS_TO_MONITOR = list(range(2, 11))

# Module counts per arc (LD-358: Arc 10 = 5 modules, all others = 6).
MODULES_PER_ARC: dict[int, int] = {
    1: 6, 2: 6, 3: 6, 4: 6, 5: 6,
    6: 6, 7: 6, 8: 6, 9: 6, 10: 5,
}

# Defaults (used if prod_arc_release_schedule migration not yet applied).
DEFAULT_CADENCE_FAST = 3.0   # modules/week — fastest-family worst-case (LD-352)
DEFAULT_BUFFER_WEEKS = 2
DEFAULT_PRODUCTION_LEAD = 4  # weeks Kim needs from "start production" to "CDN-live"

# Arc IDs used in Firestore and app_blockers feature_id.
ARC_ID_MAP = {
    2: "arc2", 3: "arc3", 4: "arc4", 5: "arc5",
    6: "arc6", 7: "arc7", 8: "arc8", 9: "arc9", 10: "arc10",
}

LAUNCH_DATE_LD_KEY = "LAUNCH_DATE_V1"


# ─── Firestore helpers ────────────────────────────────────────────────────────

def _gcloud_token() -> str:
    import subprocess
    try:
        token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if not token:
            raise RuntimeError("empty token")
        return token
    except Exception as e:
        sys.exit(
            f"ERROR: gcloud auth failed — {e}\n"
            "Run: gcloud auth login --account kimhyla11@gmail.com"
        )


def _firestore_doc_exists(collection: str, doc_id: str, token: str) -> bool:
    """Returns True if the Firestore document exists."""
    url = f"{FIRESTORE_BASE}/{collection}/{doc_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


# ─── Directus helpers ─────────────────────────────────────────────────────────

def _get_launch_date(client: DirectusAdminClient) -> Optional[date]:
    """
    Look up LAUNCH_DATE_V1 in prod_locked_decisions.
    Returns None if not found.
    """
    rows = client.get_items(
        "prod_locked_decisions",
        filters={"decision_key": {"_eq": LAUNCH_DATE_LD_KEY}},
        fields=["id", "decision_key", "decision_text"],
        limit=1,
    )
    if not rows:
        return None
    text = rows[0].get("decision_text", "")
    # decision_text is expected to contain ISO date like "2026-06-01"
    for word in text.replace(",", " ").split():
        try:
            return date.fromisoformat(word.strip())
        except ValueError:
            continue
    return None


def _get_schedule_params(client: DirectusAdminClient) -> dict:
    """
    Read schedule params from prod_arc_release_schedule if the migration has
    been applied.  Falls back to hardcoded defaults.
    Returns dict with keys: cadence, buffer_weeks, production_lead_weeks.
    """
    try:
        rows = client.get_items(
            "prod_arc_release_schedule",
            fields=["arc_number", "cadence_assumed", "production_lead_weeks_assumed"],
            limit=1,
        )
        if rows:
            return {
                "cadence": float(rows[0].get("cadence_assumed", DEFAULT_CADENCE_FAST)),
                "buffer_weeks": DEFAULT_BUFFER_WEEKS,
                "production_lead_weeks": float(
                    rows[0].get("production_lead_weeks_assumed", DEFAULT_PRODUCTION_LEAD)
                ),
            }
    except Exception:
        pass
    return {
        "cadence": DEFAULT_CADENCE_FAST,
        "buffer_weeks": DEFAULT_BUFFER_WEEKS,
        "production_lead_weeks": DEFAULT_PRODUCTION_LEAD,
    }


def _modules_before_arc(arc_n: int) -> int:
    return sum(MODULES_PER_ARC[a] for a in range(1, arc_n))


def _cdn_deadline_weeks(arc_n: int, cadence: float, buffer: int) -> float:
    return math.ceil(_modules_before_arc(arc_n) / cadence) + buffer


def _get_open_blocker(
    client: DirectusAdminClient, feature_id: str
) -> Optional[dict]:
    rows = client.get_items(
        "app_blockers",
        filters={
            "feature_id": {"_eq": feature_id},
            "is_resolved": {"_eq": False},
        },
        fields=["id", "title", "description", "severity"],
        limit=1,
    )
    return rows[0] if rows else None


def _create_blocker(
    client: DirectusAdminClient, arc_n: int, arc_id: str,
    cdn_deadline_date: Optional[date], weeks_until_cdn: float,
    dry_run: bool,
) -> None:
    feature_id = f"arc_cadence_{arc_id}"
    date_str = cdn_deadline_date.isoformat() if cdn_deadline_date else "TBD (launch date not locked)"
    description = (
        f"Arc {arc_n} ({arc_id}) must be CDN-live by {date_str} "
        f"({weeks_until_cdn:.1f} weeks from launch) to avoid paying families "
        f"hitting a hard wall with no content available. "
        f"CDN-live signal: Firestore arc_manifests/{arc_id}. "
        f"Written by arc_cadence_monitor.py (Stream F Item 7)."
    )
    if dry_run:
        print(f"  [DRY RUN] Would create CRITICAL blocker: {feature_id}")
        print(f"    {description[:120]}...")
        return
    client.post_item("app_blockers", {
        "feature_id": feature_id,
        "title": f"Arc {arc_n} CDN deadline approaching — not yet live",
        "description": description,
        "severity": "critical",
        "is_resolved": False,
    })
    print(f"  ✓ CRITICAL blocker created: {feature_id}")


def _update_blocker(
    client: DirectusAdminClient, blocker_id: int, arc_n: int, arc_id: str,
    cdn_deadline_date: Optional[date], weeks_until_cdn: float,
    dry_run: bool,
) -> None:
    date_str = cdn_deadline_date.isoformat() if cdn_deadline_date else "TBD"
    description = (
        f"Arc {arc_n} ({arc_id}) still NOT CDN-live. Deadline: {date_str} "
        f"({weeks_until_cdn:.1f} weeks from launch). "
        f"Updated by arc_cadence_monitor.py run {datetime.now(timezone.utc).date().isoformat()}."
    )
    if dry_run:
        print(f"  [DRY RUN] Would update existing blocker id={blocker_id}: {arc_id}")
        return
    client.patch_item("app_blockers", blocker_id, {"description": description})
    print(f"  ✓ Blocker id={blocker_id} updated: {arc_id}")


def _resolve_blocker(
    client: DirectusAdminClient, blocker_id: int, arc_id: str, dry_run: bool
) -> None:
    if dry_run:
        print(f"  [DRY RUN] Would resolve blocker id={blocker_id} for {arc_id}")
        return
    client.patch_item("app_blockers", blocker_id, {"is_resolved": True})
    print(f"  ✓ Blocker id={blocker_id} resolved: {arc_id} is CDN-live")


def _write_activity_log(
    client: DirectusAdminClient, summary: str, arcs_live: list[int],
    arcs_at_risk: list[int], dry_run: bool
) -> None:
    if dry_run:
        print(f"\n[DRY RUN] Would write prod_activity_log: {summary[:80]}")
        return
    try:
        client.post_item("prod_activity_log", {
            "action": f"arc_cadence_monitor_run_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "details": json.dumps({
                "summary": summary,
                "arcs_live": arcs_live,
                "arcs_at_risk": arcs_at_risk,
                "stream": "F",
                "task_id": "stream-f-item-7-cadence-monitor",
                "run_at": datetime.now(timezone.utc).isoformat(),
            }),
        })
    except Exception as e:
        print(f"WARNING: prod_activity_log write failed — {e}", file=sys.stderr)


def _write_warn_activity_log(client: DirectusAdminClient, error_msg: str) -> None:
    try:
        client.post_item("prod_activity_log", {
            "action": "arc_cadence_monitor_error",
            "details": json.dumps({
                "level": "WARN",
                "error": error_msg[:500],
                "stream": "F",
                "task_id": "stream-f-item-7-cadence-monitor",
                "run_at": datetime.now(timezone.utc).isoformat(),
            }),
        })
    except Exception:
        pass  # best-effort; already erroring


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, verbose: bool = False) -> None:
    client = DirectusAdminClient()

    # Step 1: Read launch date.
    launch_date = _get_launch_date(client)
    if launch_date is None:
        print(
            "INFO: Launch date not locked (LAUNCH_DATE_V1 not found in "
            "prod_locked_decisions). Arc cadence monitor is inert until "
            "launch date is locked. Exit 0."
        )
        return

    today = date.today()
    weeks_since_launch = (today - launch_date).days / 7.0
    print(f"Launch date: {launch_date} | Today: {today} | Weeks since launch: {weeks_since_launch:.1f}")

    # Step 2: Read schedule parameters.
    params = _get_schedule_params(client)
    cadence = params["cadence"]
    buffer_weeks = params["buffer_weeks"]
    production_lead = params["production_lead_weeks"]
    print(
        f"Params: cadence={cadence}/wk, buffer={buffer_weeks}wk, "
        f"production_lead={production_lead}wk\n"
    )

    # Step 3: Check Firestore for each arc.
    try:
        fs_token = _gcloud_token()
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"ERROR: Cannot get gcloud token — {e}")

    arcs_live: list[int] = []
    arcs_at_risk: list[int] = []
    rows: list[dict] = []

    # Warning threshold: alert when within (production_lead + buffer) weeks of CDN deadline.
    alert_horizon_weeks = production_lead + buffer_weeks

    for arc_n in ARCS_TO_MONITOR:
        arc_id = ARC_ID_MAP[arc_n]
        cdn_deadline_wk = _cdn_deadline_weeks(arc_n, cadence, buffer_weeks)

        cdn_deadline_date: Optional[date] = None
        if launch_date:
            cdn_deadline_date = launch_date + timedelta(weeks=cdn_deadline_wk)

        prod_start_wk = cdn_deadline_wk - production_lead
        weeks_until_cdn = cdn_deadline_wk - weeks_since_launch

        # CDN-live check via Firestore.
        try:
            is_live = _firestore_doc_exists("arc_manifests", arc_id, fs_token)
        except Exception as e:
            print(
                f"  WARNING: Firestore check failed for {arc_id} — {e}. Skipping.",
                file=sys.stderr,
            )
            is_live = False

        status_str = "CDN-LIVE" if is_live else f"NOT LIVE (T+{cdn_deadline_wk:.0f}wk deadline)"
        row = {
            "arc": arc_n,
            "arc_id": arc_id,
            "is_live": is_live,
            "cdn_deadline_wk": cdn_deadline_wk,
            "cdn_deadline_date": cdn_deadline_date,
            "prod_start_wk": prod_start_wk,
            "weeks_until_cdn": weeks_until_cdn,
            "status": status_str,
        }
        rows.append(row)

        if is_live:
            arcs_live.append(arc_n)
        else:
            # Within alert horizon and not live → at risk.
            if weeks_until_cdn <= alert_horizon_weeks:
                arcs_at_risk.append(arc_n)

    # Step 4+5: Create/update/resolve blockers.
    print("Blocker updates:")
    blocker_actions: list[str] = []
    for row in rows:
        arc_n = row["arc"]
        arc_id = row["arc_id"]
        feature_id = f"arc_cadence_{arc_id}"
        existing = _get_open_blocker(client, feature_id)

        if row["is_live"]:
            # Arc is live — resolve any open blocker.
            if existing:
                _resolve_blocker(client, existing["id"], arc_id, dry_run)
                blocker_actions.append(f"resolved:{arc_id}")
            else:
                if verbose:
                    print(f"  Arc {arc_n} ({arc_id}): CDN-live, no open blocker. OK.")
        else:
            if arc_n in arcs_at_risk:
                if existing:
                    _update_blocker(
                        client, existing["id"], arc_n, arc_id,
                        row["cdn_deadline_date"], row["weeks_until_cdn"], dry_run,
                    )
                    blocker_actions.append(f"updated:{arc_id}")
                else:
                    _create_blocker(
                        client, arc_n, arc_id,
                        row["cdn_deadline_date"], row["weeks_until_cdn"], dry_run,
                    )
                    blocker_actions.append(f"created:{arc_id}")
            else:
                if verbose:
                    print(
                        f"  Arc {arc_n} ({arc_id}): not live, "
                        f"{row['weeks_until_cdn']:.1f}wk until deadline — not yet in alert window."
                    )

    if not blocker_actions:
        print("  (no blocker changes needed)")

    # Step 6: Print summary table.
    print(
        f"\n{'Arc':<6}{'Arc ID':<10}{'CDN Deadline':<16}"
        f"{'Wks Until CDN':<16}{'Prod Start':<14}{'Status'}"
    )
    print("-" * 76)
    for row in rows:
        date_str = row["cdn_deadline_date"].isoformat() if row["cdn_deadline_date"] else "TBD"
        prod_start_str = f"T+{row['prod_start_wk']:.0f}wk"
        wks_str = f"{row['weeks_until_cdn']:.1f}wk"
        print(
            f"{row['arc']:<6}{row['arc_id']:<10}{date_str:<16}"
            f"{wks_str:<16}{prod_start_str:<14}{row['status']}"
        )

    # Step 7: Write activity log.
    summary = (
        f"arc_cadence_monitor run {today.isoformat()}: "
        f"{len(arcs_live)} arcs CDN-live, {len(arcs_at_risk)} at risk. "
        f"Actions: {', '.join(blocker_actions) or 'none'}."
    )
    _write_activity_log(client, summary, arcs_live, arcs_at_risk, dry_run)
    print(f"\nDone. {summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Arc Release Cadence Monitor (Stream F Item 7)")
    parser.add_argument("--dry-run", action="store_true", help="No writes; show what would happen")
    parser.add_argument("--verbose", action="store_true", help="Print all arcs even when no action needed")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, verbose=args.verbose)
    except SystemExit:
        raise
    except Exception as exc:
        error_msg = traceback.format_exc()
        print(f"ERROR: arc_cadence_monitor.py failed — {exc}", file=sys.stderr)
        print(error_msg, file=sys.stderr)
        try:
            _write_warn_activity_log(DirectusAdminClient(), str(exc))
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
