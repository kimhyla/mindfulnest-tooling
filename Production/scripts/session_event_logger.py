#!/usr/bin/env python3
"""
MindfulNest PostToolUse hook — append tool events to session_events.jsonl.

Wires up the mn-context v2 tool-event journal (§ Session-time mechanisms).
Fires on every Write, Edit, or Bash call. Never blocks execution.

Journal format (one JSON line per event):
  {"ts": "...", "op": "Write|Edit|Bash", "path": "...", "description": "..."}
"""

from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

JOURNAL = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
    "Claude Mindfulnest Project Files/.mn-context/session_events.jsonl"
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
    except Exception:
        return 0

    try:
        tool_name = payload.get("tool_name", "") or ""
        tool_input = payload.get("tool_input", {}) or {}

        if tool_name not in ("Write", "Edit", "Bash"):
            return 0

        if tool_name in ("Write", "Edit"):
            path = tool_input.get("file_path", "") or ""
            description = tool_name.lower()
        else:  # Bash
            path = (tool_input.get("command", "") or "")[:100]
            description = (tool_input.get("description", "") or "bash")[:80]

        event = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "op": tool_name,
            "path": path,
            "description": description,
        }

        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a") as f:
            f.write(json.dumps(event) + "\n")

    except Exception:
        pass  # never block execution

    return 0


if __name__ == "__main__":
    sys.exit(main())
