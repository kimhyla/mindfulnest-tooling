#!/usr/bin/env python3
"""
weekly_directus_snapshot.py — weekly JSON snapshot of key Directus collections.

Spec v2 §C15. Commits snapshots to a separate `mindfulnest-governance-backup` git repo
for audit trail + off-site redundancy. pg_dump (daily_backup.sh) is the primary DB backup;
this is the human-readable JSON audit trail.

Collections snapshotted:
- prod_locked_decisions (active + superseded)
- app_activity_log (last 90 days)
- prod_preflight_reviews (all)
- app_blockers (all)
- prod_app_stages (all)

Output: ~/MindfulNestBackups/governance-snapshot-repo/<YYYY-MM-DD>/<collection>.json
Then commits to the repo with message "Weekly snapshot YYYY-MM-DD".
"""

from __future__ import annotations
import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
from lib.directus_admin_client import DirectusAdminClient  # noqa: E402


REPO_DIR = Path(os.path.expanduser("~/MindfulNestBackups/governance-snapshot-repo"))
COLLECTIONS_FULL = ["prod_locked_decisions", "prod_preflight_reviews", "app_blockers", "prod_app_stages"]
COLLECTIONS_WINDOWED = {"app_activity_log": 90}  # last 90 days


def run(cmd: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {result.stderr}")
    return result.stdout.strip()


def ensure_repo() -> None:
    if not REPO_DIR.exists():
        REPO_DIR.mkdir(parents=True, exist_ok=True)
        run(["git", "init"], cwd=REPO_DIR)
        (REPO_DIR / ".gitignore").write_text(".DS_Store\n*.swp\n")
        run(["git", "add", ".gitignore"], cwd=REPO_DIR)
        run(["git", "commit", "-m", "init"], cwd=REPO_DIR)


def snapshot_collection(client: DirectusAdminClient, collection: str, filters: dict | None = None) -> list:
    return client.get_items(collection, filters=filters, limit=-1)


def main() -> int:
    ensure_repo()
    client = DirectusAdminClient()
    today = datetime.now(timezone.utc).date().isoformat()
    day_dir = REPO_DIR / today
    day_dir.mkdir(exist_ok=True)

    counts = {}
    for col in COLLECTIONS_FULL:
        rows = snapshot_collection(client, col)
        (day_dir / f"{col}.json").write_text(json.dumps(rows, indent=2, default=str))
        counts[col] = len(rows)

    for col, window_days in COLLECTIONS_WINDOWED.items():
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        rows = snapshot_collection(client, col, filters={"created_at": {"_gte": cutoff}})
        (day_dir / f"{col}_last{window_days}d.json").write_text(json.dumps(rows, indent=2, default=str))
        counts[col] = len(rows)

    # Git commit
    run(["git", "add", today], cwd=REPO_DIR)
    has_changes = run(["git", "status", "--porcelain"], cwd=REPO_DIR).strip()
    if has_changes:
        summary = ", ".join(f"{k}={v}" for k, v in counts.items())
        run(["git", "commit", "-m", f"Weekly snapshot {today} — {summary}"], cwd=REPO_DIR)
        print(f"SNAPSHOT {today}: committed ({summary})")
    else:
        print(f"SNAPSHOT {today}: no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
