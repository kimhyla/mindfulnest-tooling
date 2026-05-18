#!/usr/bin/env python3
"""Clear overnight pause lock and log resume to prod_activity_log.

Per V59 spec §0 Phase 0 / Agent A amendment A4. Idempotent when not paused.
"""
from __future__ import annotations

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


def _parse_prior_reason(contents: str) -> str:
    for line in contents.splitlines():
        if line.startswith("reason="):
            return line.split("=", 1)[1].strip()
    return contents.strip()[:200] or "unknown"


def main() -> int:
    if not PAUSE_FILE.exists():
        print("NOT_PAUSED")
        return 0

    prior_contents = PAUSE_FILE.read_text(encoding="utf-8")
    prior_reason = _parse_prior_reason(prior_contents)
    PAUSE_FILE.unlink()

    resumed_at = _now_iso()
    resumed_by = getpass.getuser()
    action = f"OVERNIGHT_RESUMED_{_utc_stamp()}"
    try_post_or_queue(
        "prod_activity_log",
        {
            "action": action,
            "details": {
                "resumed_at": resumed_at,
                "prior_pause_reason": prior_contents,
                "resumed_by": resumed_by,
            },
            "performed_by": "overnight_resume",
        },
    )

    print(f"OVERNIGHT RESUMED at {resumed_at}  prior_pause={prior_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
