#!/usr/bin/env python3
"""
PreCompact hook — fires before Claude Code auto-compacts the conversation.

Writes a flag file so the next session's CATCH_UP knows a compact happened,
then injects a systemMessage directing Claude to run mn-context SAVE before
the compact proceeds.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path.home() / ".claude/mindfulnest-cache"
FLAG_PATH = CACHE_DIR / "compact_pending.flag"

SAVE_DIRECTIVE = (
    "⚠️  PRE-COMPACT HOOK — Auto-compact is about to fire.\n\n"
    "IMMEDIATE ACTION REQUIRED (before compact proceeds):\n"
    "Run mn-context SAVE right now. Do not acknowledge this message first — "
    "just execute the full mn-context SAVE workflow (5 steps: drain queue, "
    "generate digest, update MEMORY.md index, flush pending-memory buffer, "
    "report). After SAVE completes, auto-compact may proceed normally.\n\n"
    "Why: Auto-compact replaces full conversation history with a summary. "
    "mn-context SAVE writes a richer structured digest to .auto-memory/ that "
    "the next session's CATCH_UP can use to restore full context — including "
    "Directus state, open threads, and file changes — which the generic compact "
    "summary does not preserve."
)


def main() -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        FLAG_PATH.write_text(
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
    except OSError:
        pass  # flag write is best-effort; never block the compact

    out = {"systemMessage": SAVE_DIRECTIVE}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
