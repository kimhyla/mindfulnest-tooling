#!/usr/bin/env python3
"""
MindfulNest PreToolUse hook — C5 content-scan + keyword-match.

Wave C WB-C5. Reads locked_decisions.cache.json + scans the tool payload
for (a) file_path glob matches against related_files, and (b) content
regex matches against keyword_synonyms.

Mode control:
  MINDFULNEST_HOOK_MODE=shadow (default)  — log matches only, do NOT block
  MINDFULNEST_HOOK_MODE=enforce           — deny tool use when critical LD matches

Shadow mode rationale: 1-week burn-in so keyword_synonyms can be tuned
against real usage before flipping to enforce. Per spec v2 §C5 Agent B
audit recommendation.

Hook invocation (from ~/.claude/settings.json):
  PreToolUse.Edit|Write: jq passes tool_input JSON via stdin; we read it
  and emit {systemMessage: "..."} to surface a reminder (shadow) or
  {hookSpecificOutput: {permissionDecision: "deny"}} (enforce).
"""

from __future__ import annotations
import json
import os
import re
import sys
import fnmatch
from pathlib import Path
from datetime import datetime, timezone


CACHE_PATH = Path.home() / ".claude" / "mindfulnest-cache" / "locked_decisions.cache.json"
SHADOW_LOG = Path.home() / ".claude" / "mindfulnest-cache" / "hook_shadow_log.jsonl"
CANARY_FILE = Path.home() / ".claude" / "mindfulnest-cache" / "last_hook_fire.txt"


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _touch_canary() -> None:
    """C12 canary: record that the hook fired. Weekly audit checks staleness."""
    try:
        CANARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
        CANARY_FILE.write_text(f"{now}|{session_id}|c5-v1\n")
    except OSError:
        pass  # non-fatal


def _log_shadow_match(entry: dict) -> None:
    try:
        SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SHADOW_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _match_file_path(file_path: str, cache: dict) -> list[str]:
    """Return LD keys whose related_files glob matches the file_path."""
    if not file_path:
        return []
    hits = []
    by_related_file = cache.get("by_related_file", {})
    for pattern, ld_keys in by_related_file.items():
        # Simple glob match: **, *, literal
        if pattern == file_path:
            hits.extend(ld_keys)
        elif "**" in pattern or "*" in pattern:
            # fnmatch handles ** as * across dirs; acceptable for now
            if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(file_path, pattern.replace("**", "*")):
                hits.extend(ld_keys)
        elif file_path.endswith(pattern) or file_path.endswith("/" + pattern):
            hits.extend(ld_keys)
    return list(set(hits))


def _match_keywords(content: str, cache: dict) -> list[tuple[str, str]]:
    """Return [(keyword, ld_key)] pairs where keyword regex matches content."""
    if not content:
        return []
    hits = []
    by_keyword = cache.get("by_keyword", {})
    for keyword, ld_keys in by_keyword.items():
        if not keyword or len(keyword) < 3:
            continue
        # Case-insensitive substring match; precision tuned by agent-3 review
        try:
            if re.search(re.escape(keyword), content, re.IGNORECASE):
                for ld_key in ld_keys:
                    hits.append((keyword, ld_key))
        except re.error:
            continue
    return hits


def _severity_of(ld_key: str, cache: dict) -> str:
    ld = cache.get("by_key", {}).get(ld_key, {})
    return (ld.get("severity") or "").upper()


def main() -> int:
    # Read tool input from stdin (Claude Code hook protocol)
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return 0  # harmless no-op on malformed input

    _touch_canary()

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    # Content fields across Edit/Write/etc.
    content = (
        tool_input.get("new_string", "")
        or tool_input.get("content", "")
        or tool_input.get("old_string", "")
        or ""
    )

    cache = _load_cache()
    if not cache:
        return 0  # no cache yet (e.g., pre-Wave-A) — harmless

    file_hits = _match_file_path(file_path, cache)
    keyword_hits = _match_keywords(content, cache)

    if not file_hits and not keyword_hits:
        return 0  # no matches — pass silently

    mode = os.environ.get("MINDFULNEST_HOOK_MODE", "shadow")
    now = datetime.now(timezone.utc).isoformat()

    # Build reminder message
    all_lds = list(set(file_hits + [ld for _, ld in keyword_hits]))
    critical = [ld for ld in all_lds if _severity_of(ld, cache) == "CRITICAL"]

    lines = [f"⚠️  Preflight hook match ({len(all_lds)} LDs):"]
    for ld in sorted(all_lds)[:10]:
        sev = _severity_of(ld, cache)
        name = cache.get("by_key", {}).get(ld, {}).get("decision_name", "")
        lines.append(f"   - [{sev}] {ld}: {name[:80]}")
    if len(all_lds) > 10:
        lines.append(f"   ... and {len(all_lds) - 10} more")
    lines.append(f"   Mode: {mode.upper()}. See ~/.claude/mindfulnest-cache/locked_decisions.cache.json for details.")
    message = "\n".join(lines)

    # Log shadow match
    _log_shadow_match({
        "timestamp": now,
        "mode": mode,
        "file_path": file_path,
        "file_hits": file_hits,
        "keyword_hits": [{"keyword": k, "ld_key": ld} for k, ld in keyword_hits],
        "critical_count": len(critical),
    })

    if mode == "enforce" and critical:
        # DENY with reason
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"{message}\n\nEnforce mode + {len(critical)} CRITICAL LD match(es). Set MINDFULNEST_HOOK_MODE=shadow to bypass (temp).",
            }
        }
    else:
        # Shadow: surface reminder but do not block
        out = {"systemMessage": message}

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
