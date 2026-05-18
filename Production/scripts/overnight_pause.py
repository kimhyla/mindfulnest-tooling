#!/usr/bin/env python3
"""Signal overnight build pause via .overnight_paused lock file + activity log.

Per V59 spec §0 Phase 0 / Agent A amendment A4. Orchestrator and phase scripts
must check for .overnight_paused before proceeding.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus import try_post_or_queue  # noqa: E402

PAUSE_FILE = REPO_ROOT / ".overnight_paused"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pause overnight autonomous build")
    parser.add_argument("--reason", default="manual", help="Pause reason (default: manual)")
    args = parser.parse_args()

    paused_at = _now_iso()
    paused_by = getpass.getuser()
    content = f"paused_at={paused_at}\nreason={args.reason}\npaused_by={paused_by}\n"
    PAUSE_FILE.write_text(content, encoding="utf-8")

    action = f"OVERNIGHT_PAUSED_{_utc_stamp()}"
    try_post_or_queue(
        "prod_activity_log",
        {
            "action": action,
            "details": {
                "reason": args.reason,
                "paused_at": paused_at,
                "paused_by": paused_by,
            },
            "performed_by": "overnight_pause",
        },
    )

    print(f"OVERNIGHT PAUSED at {paused_at}  reason={args.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
