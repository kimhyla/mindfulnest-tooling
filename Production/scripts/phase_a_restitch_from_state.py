#!/usr/bin/env python3
"""Restitch Phase A via POST /api/phase_a/restitch (pinned fly-in/out)."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    server = os.environ.get("MN_SERVER", "http://127.0.0.1:5111")
    event = os.environ.get("MN_EVENT_ID", "Event_1")
    body = json.dumps({
        "event_id": event,
        "scope_video_role": "intro",
        "phase": "a",
    }).encode()
    req = urllib.request.Request(
        f"{server}/api/phase_a/restitch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
