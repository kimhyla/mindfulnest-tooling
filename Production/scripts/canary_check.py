#!/usr/bin/env python3
"""
C12 canary staleness check — Wave C.

Verifies:
  - ~/.claude/mindfulnest-cache/last_hook_fire.txt is fresh (<24h)
  - ~/.claude/mindfulnest-cache/last_session_start.txt is fresh (<48h)

If a canary is stale, the preflight hook (C5) may be silently no-op'ing —
which means governance reminders aren't firing when they should. Logs to
Directus app_activity_log with severity=HIGH.

Called from SessionStart hook (frequent sampling) + weekly cron
(catches stuck canaries even when Kim stops using Claude for a while).

Usage:
  python3 Production/scripts/canary_check.py [--quiet]

Exit 0 = all fresh. Exit 1 = at least one stale (but the script still writes
the audit record; exit code is informational).
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

try:
    from lib.directus_admin_client import DirectusAdminClient
except ImportError:
    DirectusAdminClient = None  # Graceful — still runs offline


CANARY_HOOK_FIRE = Path.home() / ".claude" / "mindfulnest-cache" / "last_hook_fire.txt"
CANARY_SESSION_START = Path.home() / ".claude" / "mindfulnest-cache" / "last_session_start.txt"

HOOK_FIRE_STALE_HOURS = 24
SESSION_START_STALE_HOURS = 48


def _parse_canary(path: Path) -> tuple[datetime, str] | None:
    """Return (timestamp, session_id) or None if missing/unparseable."""
    if not path.exists():
        return None
    try:
        line = path.read_text().strip()
        parts = line.split("|")
        if len(parts) < 2:
            return None
        ts = datetime.fromisoformat(parts[0].replace("Z", "+00:00"))
        return (ts, parts[1] if len(parts) > 1 else "unknown")
    except (ValueError, OSError):
        return None


def check() -> tuple[list[dict], bool]:
    """Returns (alerts, all_fresh_bool)."""
    now = datetime.now(timezone.utc)
    alerts = []

    for path, max_hours, name in [
        (CANARY_HOOK_FIRE, HOOK_FIRE_STALE_HOURS, "hook_fire"),
        (CANARY_SESSION_START, SESSION_START_STALE_HOURS, "session_start"),
    ]:
        parsed = _parse_canary(path)
        if parsed is None:
            alerts.append({
                "canary": name,
                "severity": "MEDIUM",
                "state": "MISSING",
                "path": str(path),
                "message": f"Canary file missing — C12 hook may not have fired yet",
            })
            continue
        ts, session_id = parsed
        age_hours = (now - ts).total_seconds() / 3600
        if age_hours > max_hours:
            alerts.append({
                "canary": name,
                "severity": "HIGH" if name == "hook_fire" else "MEDIUM",
                "state": "STALE",
                "path": str(path),
                "age_hours": round(age_hours, 1),
                "max_hours": max_hours,
                "last_timestamp": ts.isoformat(),
                "last_session_id": session_id,
                "message": f"Canary {age_hours:.1f}h old (threshold: {max_hours}h)",
            })

    return alerts, len(alerts) == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Directus")
    args = parser.parse_args()

    alerts, all_fresh = check()

    if not args.quiet:
        if all_fresh:
            print("[canary] OK — all canaries fresh")
        else:
            for a in alerts:
                print(f"[canary] {a['severity']}: {a['canary']} {a['state']} — {a['message']}")

    # Log to Directus if any alerts
    if alerts and not args.dry_run and DirectusAdminClient is not None:
        try:
            client = DirectusAdminClient()
            client.post_item("app_activity_log", {
                "feature_id": "c12_canary_check",
                "action": f"C12 canary check: {len(alerts)} alert(s) — " + ", ".join(a["canary"] + "=" + a["state"] for a in alerts),
                "performed_by": "canary_check.py",
                "details": {"alerts": alerts, "checked_at": datetime.now(timezone.utc).isoformat()},
            })
        except Exception as e:
            print(f"[canary] WARN: could not log to Directus: {e}")

    return 0 if all_fresh else 1


if __name__ == "__main__":
    sys.exit(main())
