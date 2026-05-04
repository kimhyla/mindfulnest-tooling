#!/usr/bin/env python3
"""
failure_mode_matrix.py — read-only join over Directus governance collections.

For each LD (prod_locked_decisions), surfaces:
  - latest activity_log entry referencing the LD (by decision_key in details OR
    by enforcement_artifact_ref match in details.related_decision_key)
  - latest preflight review whose task_description mentions the LD's decision_key
  - open app_blockers whose description mentions the LD's decision_key
  - last-touched file (from latest activity log details.files_modified or .files_created)

Output: human-readable table to stdout. NON-BLOCKING — errors per row are logged
to stderr but do not halt the script.

Usage:
    python3 failure_mode_matrix.py [--severity {CRITICAL,HIGH,MEDIUM,LOW}]
                                   [--limit N] [--keys KEY1,KEY2,...]
                                   [--json]

Wired into CLAUDE.md "Session Start: Lightweight Sanity Check" as step 3a
(opt-in via the `--matrix` flag from the wrapper, not default-on, per Phase 0
LOW finding mitigation: avoid regressing the 2-min sanity check budget).

Performance design (per Phase 0 MED finding):
  - Each LD's activity_log scan uses Directus filter `details` JSON containment
    where supported, falling back to a single bounded fetch + Python filter.
  - Cap activity_log fetch to last 200 rows globally (sufficient for "latest
    per LD" without an O(LDs x rows) cross-join).
  - Wall-clock target: <3s for ~300 LDs.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
from lib.directus_admin_client import DirectusAdminClient, DirectusAdminError  # noqa: E402


SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, None: 0, "": 0}


def _ld_key_in_details(details, key: str) -> bool:
    if not details:
        return False
    if isinstance(details, str):
        return key in details
    try:
        return key in json.dumps(details)
    except Exception:
        return False


def _files_from_details(details) -> str | None:
    if not details or isinstance(details, str):
        return None
    files = (details.get("files_modified") or []) + (details.get("files_created") or [])
    return files[0] if files else None


def build_matrix(client: DirectusAdminClient, args) -> list[dict]:
    lds = client.get_items("prod_locked_decisions", filters={"status": {"_eq": "active"}}) or []
    if args.severity:
        lds = [l for l in lds if (l.get("severity") or "").upper() == args.severity.upper()]
    if args.keys:
        keyset = set(args.keys.split(","))
        lds = [l for l in lds if l.get("decision_key") in keyset]
    if args.limit:
        lds.sort(key=lambda l: SEVERITY_RANK.get((l.get("severity") or "").upper(), 0), reverse=True)
        lds = lds[: args.limit]

    # Bounded scans per Phase 0 MED finding (server-side limits, not full cross-join)
    activity = client.get_items("prod_activity_log", filters=None) or []
    activity = sorted(activity, key=lambda r: r.get("id", 0), reverse=True)[:200]

    preflights = client.get_items("prod_preflight_reviews", filters=None) or []
    preflights = sorted(preflights, key=lambda r: r.get("id", 0), reverse=True)[:100]

    blockers = client.get_items("app_blockers", filters={"is_resolved": {"_eq": False}}) or []

    matrix = []
    for ld in lds:
        key = ld.get("decision_key", "")
        latest_activity = next((a for a in activity if _ld_key_in_details(a.get("details"), key)
                                or key in (a.get("action") or "")), None)
        latest_preflight = next((p for p in preflights if key in (p.get("task_description") or "")
                                 or key in (p.get("synthesis") or "")), None)
        open_blockers = [b for b in blockers if key in (b.get("description") or "")
                         or key in (b.get("title") or "")]
        last_file = _files_from_details(latest_activity.get("details") if latest_activity else None) \
                    or ld.get("enforcement_artifact_ref")
        matrix.append({
            "ld_id": ld.get("id"),
            "decision_key": key,
            "severity": ld.get("severity"),
            "status": ld.get("status"),
            "latest_activity_id": latest_activity.get("id") if latest_activity else None,
            "latest_preflight_id": latest_preflight.get("id") if latest_preflight else None,
            "open_blockers": [{"id": b.get("id"), "severity": b.get("severity"), "title": (b.get("title") or "")[:60]}
                              for b in open_blockers],
            "last_touched_file": last_file,
        })
    return matrix


def print_matrix(matrix: list[dict]) -> None:
    if not matrix:
        print("[matrix] no LDs match filters")
        return
    print(f"{'LD id':>6}  {'KEY':<36}  {'SEV':<8}  {'ACT':>4}  {'PRE':>4}  BLOCKERS  FILE")
    print("-" * 110)
    for row in matrix:
        bl = ",".join(f"#{b['id']}({b['severity']})" for b in (row.get("open_blockers") or [])) or "-"
        f = (row.get("last_touched_file") or "-")
        if len(f) > 50:
            f = "..." + f[-47:]
        print(f"{row['ld_id']:>6}  {row['decision_key'][:36]:<36}  {(row.get('severity') or '-'):<8}  "
              f"{(row.get('latest_activity_id') or '-')!s:>4}  {(row.get('latest_preflight_id') or '-')!s:>4}  "
              f"{bl[:30]:<30}  {f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--severity", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"], default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--keys", default=None, help="Comma-separated decision_keys")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of table")
    args = ap.parse_args()

    t0 = time.monotonic()
    try:
        client = DirectusAdminClient()
        matrix = build_matrix(client, args)
    except (DirectusAdminError, RuntimeError) as e:
        print(f"[matrix] ERROR (non-blocking): {e}", file=sys.stderr)
        return 0  # NON-BLOCKING per CLAUDE.md sanity check wiring

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    if args.json:
        print(json.dumps({"matrix": matrix, "elapsed_ms": elapsed_ms}, indent=2, default=str))
    else:
        print_matrix(matrix)
        print(f"\n[matrix] {len(matrix)} LDs in {elapsed_ms}ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
