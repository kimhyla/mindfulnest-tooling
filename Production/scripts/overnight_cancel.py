#!/usr/bin/env python3
"""Hard-halt V59 overnight build: pause lock, cancel vendor jobs, file LD + log.

Per V59 spec §0 Phase 0 / Agent A amendment A4. Invokes overnight_pause,
cancel_pending_vendor_jobs, registers prod_locked_decisions row, and exits 1.
"""
from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus import try_post_or_queue  # noqa: E402
from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _read_last_completed_phase(client: DirectusAdminClient) -> str:
    try:
        rows = client.get_items(
            "prod_activity_log",
            filters={"action": {"_ends_with": "_COMPLETE"}},
            sort="-id",
            fields=["action", "details"],
            limit=5,
        ) or []
        for row in rows:
            action = row.get("action") or ""
            if action.startswith("OVERNIGHT_") or "PHASE" in action.upper():
                return action
        if rows:
            return str(rows[0].get("action") or "unknown")
    except Exception:
        pass
    return "unknown"


def _invoke_pause(reason: str) -> None:
    import importlib.util

    pause_path = SCRIPTS / "overnight_pause.py"
    spec = importlib.util.spec_from_file_location("overnight_pause", pause_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {pause_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["overnight_pause.py", "--reason", reason]
    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        mod.main()


def _invoke_cancel_jobs() -> dict:
    import importlib.util

    cancel_path = SCRIPTS / "cancel_pending_vendor_jobs.py"
    spec = importlib.util.spec_from_file_location("cancel_pending_vendor_jobs", cancel_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {cancel_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "cancel_all_pending"):
        result = mod.cancel_all_pending()
        if isinstance(result, dict):
            return result
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cancel V59 overnight build mid-flight")
    parser.add_argument("--reason", required=True, help="Cancellation reason (required)")
    args = parser.parse_args()

    cancelled_at = _now_iso()
    stamp = _utc_stamp()
    git_head = _git_head()

    _invoke_pause(f"CANCELLED:{args.reason}")

    cancel_details = _invoke_cancel_jobs()

    client = DirectusAdminClient()
    last_phase = _read_last_completed_phase(client)

    decision_key = f"OVERNIGHT_CANCELLED_{stamp}_V1"
    decision_text = (
        f"V59 overnight build cancelled at {cancelled_at}. "
        f"reason={args.reason!r} last_completed_phase={last_phase!r} "
        f"git_head={git_head}"
    )
    ld_payload = {
        "decision_key": decision_key,
        "decision_name": "V59 overnight build cancelled mid-flight",
        "decision_text": decision_text,
        "severity": "HIGH",
        "task_category": "operations",
        "status": "active",
        "date_locked": cancelled_at[:10],
    }
    ld_result = try_post_or_queue("prod_locked_decisions", ld_payload, client=client)
    ld_id = ld_result.get("id") if isinstance(ld_result, dict) else None
    ld_label = f"LD-{ld_id}" if ld_id else decision_key

    activity_action = f"OVERNIGHT_CANCELLED_{stamp}"
    try_post_or_queue(
        "prod_activity_log",
        {
            "action": activity_action,
            "details": {
                "cancelled_at": cancelled_at,
                "reason": args.reason,
                "last_completed_phase": last_phase,
                "git_head": git_head,
                "decision_key": decision_key,
                "ld_id": ld_id,
                "cancelled_by": getpass.getuser(),
            },
            "performed_by": "overnight_cancel",
        },
        client=client,
    )

    n_cancelled = int(cancel_details.get("cancelled", 0))
    n_uncancel = int(cancel_details.get("uncancellable", 0))

    print(
        f"OVERNIGHT CANCELLED — {ld_label} filed, vendor jobs handled "
        f"({n_cancelled} cancelled, {n_uncancel} uncancellable)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
