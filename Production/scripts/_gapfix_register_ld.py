#!/usr/bin/env python3
"""V59 CI/CD gap-fix: register a Locked Decision via try_post_or_queue.

Runs from anywhere inside the tooling repo. Reads decision payload from a
JSON file or stdin and writes via the Production/lib/directus.py helper.

Usage:
    python3 Production/scripts/_gapfix_register_ld.py --payload-file <path>
    cat payload.json | python3 Production/scripts/_gapfix_register_ld.py --stdin
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus import try_post_or_queue  # noqa: E402


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-file", type=Path, default=None)
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--collection", default="prod_locked_decisions")
    args = parser.parse_args()

    if args.stdin:
        payload = json.loads(sys.stdin.read())
    elif args.payload_file:
        payload = json.loads(args.payload_file.read_text(encoding="utf-8"))
    else:
        print("error: --payload-file or --stdin required", file=sys.stderr)
        return 2

    # Ensure required fields are set per collection. Activity log uses
    # collection-specific fields only; locked decisions need date_locked +
    # status. Adding extras to other collections triggers SilentWriteFailure
    # because Directus drops unknown fields.
    if args.collection == "prod_locked_decisions":
        payload.setdefault("date_locked", _utcnow_iso()[:10])
        payload.setdefault("status", "active")

    result = try_post_or_queue(args.collection, payload)
    print(json.dumps(result, indent=2, default=str))
    if result.get("queued") or result.get("silent_write_failure") or result.get("browser_smoke_missing") or result.get("browser_smoke_gate_unverifiable"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
