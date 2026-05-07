#!/usr/bin/env python3
"""
PreToolUse hook — enforce CLAUDE.md Rule 3 Kim-confirmation gate on .docx writes.

Registered via LD-261 DOCX_KIM_CONFIRMATION_SIGIL_HOOK (task_id
LD-261-docx-sigil-hook-20260418-a, preflight row 73).

Scope: Write and Edit tool calls where:
  (a) tool_input.file_path ends in .docx, AND
  (b) file_path is inside the MindfulNest project folder.

Rule 3 requires that before Claude writes/overwrites any .docx Kim actively
edits, a filename round-trip must occur: Claude names the exact filename,
Kim confirms using the same filename (or confirms after Claude named it).
This hook scans the Claude Code transcript (path supplied via
$1 hook JSON `transcript_path`) for the round-trip within a tunable message
window. On match → allow. On miss → deny with a message telling Claude to
ask Kim using the full filename (mirrors Rule 3's mandated phrasing).

Fail-open on any internal exception (missing transcript, JSON parse error,
etc.) — emits {"decision":"allow","reason":"hook_error_degraded"} and writes
an ERROR row to the shadow log so the audit catches it. This prevents the
hook from blocking Kim's velocity when something upstream breaks; the
audit surfaces the drift.

Scope is strict .docx only; does NOT touch .md reference docs (pipeline
generates those; Rule 3 pipeline-output exemption applies). Does NOT touch
.json, .mp3, .mp4, or any other extension.

Stdlib only (json, os, re, sys, pathlib, hashlib, time, datetime).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import platform as _platform
_PROJECT_ROOT_ENV = os.environ.get("MINDFULNEST_PROJECT_ROOT")
if _PROJECT_ROOT_ENV:
    PROJECT_ROOT = Path(_PROJECT_ROOT_ENV)
elif _platform.system() == "Windows":
    PROJECT_ROOT = Path(r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files")
else:
    PROJECT_ROOT = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
    )
CACHE_DIR = Path.home() / ".claude" / "mindfulnest-cache"
CONFIRMATION_CACHE = CACHE_DIR / "docx_confirmation_cache.json"
SHADOW_LOG = CACHE_DIR / "hook_shadow_log.jsonl"
CACHE_TTL_SECONDS = 300  # 5 minutes (counter-agent C4)
TRANSCRIPT_SCAN_TAIL = 120  # last N transcript lines scanned for round-trip
ROUND_TRIP_WINDOW = 6  # consent token must appear within 6 messages of filename mention

CONSENT_TOKENS = [
    # Explicit approvals
    r"\byes\b",
    r"\bgo ahead\b",
    r"\bproceed\b",
    r"\bconfirmed\b",
    r"\bconfirm\b",
    r"\bapproved\b",
    r"\bdo it\b",
    # "Haven't edited" family — Kim's exact Rule 3 phrasing
    r"haven'?t\s+(?:edited|touched|changed|modified)",
    r"no\s+edits?\b",
    r"not\s+edited\b",
    r"untouched\b",
    # Blanket "go" verbs
    r"\bship it\b",
    r"\bok(?:ay)?,?\s+go\b",
]
CONSENT_RE = re.compile("|".join(CONSENT_TOKENS), re.IGNORECASE)

MINDFULNEST_AUTONOMOUS_MARKERS = [
    # LD-232 autonomous-mode pre-authorization phrases — when Kim pre-authorizes,
    # the filename-mention requirement is satisfied by the task-level yes.
    r"autonomous mode",
    r"pre-?authoriz(?:e|ed|ation)",
    r"you have (?:my )?yes\b",
    r"proceed without (?:pausing|asking)",
    r"kim pre-?authoriz",
]
AUTONOMOUS_RE = re.compile("|".join(MINDFULNEST_AUTONOMOUS_MARKERS), re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_shadow(entry: dict) -> None:
    try:
        SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SHADOW_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # non-fatal


def _load_cache() -> dict:
    try:
        if CONFIRMATION_CACHE.exists():
            return json.loads(CONFIRMATION_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        CONFIRMATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CONFIRMATION_CACHE.write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def _cache_key(filename: str, context_snippet: str) -> str:
    h = hashlib.sha256(context_snippet.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{filename}::{h}"


def _is_in_scope(file_path: str) -> bool:
    """True if file_path is a .docx inside the MindfulNest project folder."""
    if not file_path:
        return False
    if not file_path.lower().endswith(".docx"):
        return False
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        resolved = Path(file_path)
    try:
        resolved.relative_to(PROJECT_ROOT)
        return True
    except ValueError:
        # Not in the project folder — out of scope
        return False


def _read_transcript(transcript_path: str) -> list[dict]:
    if not transcript_path:
        return []
    p = Path(transcript_path)
    if not p.exists():
        return []
    lines = []
    try:
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            raw_lines = f.readlines()
    except OSError:
        return []
    tail = raw_lines[-TRANSCRIPT_SCAN_TAIL:] if len(raw_lines) > TRANSCRIPT_SCAN_TAIL else raw_lines
    for line in tail:
        try:
            lines.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return lines


def _message_role(entry: dict) -> str:
    """Transcript JSONL uses multiple shapes across Claude Code versions. Normalize."""
    msg = entry.get("message") if isinstance(entry.get("message"), dict) else entry
    role = msg.get("role") or entry.get("role") or entry.get("type") or ""
    return str(role).lower()


def _message_text(entry: dict) -> str:
    msg = entry.get("message") if isinstance(entry.get("message"), dict) else entry
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    out.append(block.get("text", ""))
                elif "text" in block:
                    out.append(str(block.get("text", "")))
        return "\n".join(out)
    if isinstance(entry.get("text"), str):
        return entry["text"]
    return ""


def _scan_round_trip(entries: list[dict], filename: str) -> tuple[bool, str]:
    """
    Return (approved, context_snippet).

    Approval rules (ordered):
      1. If Kim's own recent user message contains BOTH the filename AND a consent token
         → round-trip satisfied by Kim alone.
      2. If an assistant message (Claude) within the last ROUND_TRIP_WINDOW messages
         named the filename, AND a subsequent user message from Kim contains a consent
         token within that window → round-trip satisfied across the pair.
      3. If any user message within the last ROUND_TRIP_WINDOW messages contains an
         autonomous-mode marker (LD-232) AND mentions the filename at least once
         in the current session → round-trip satisfied by pre-authorization.
    """
    if not entries:
        return False, ""
    fn_lower = filename.lower()

    # Rule 3: autonomous pre-authorization — scan whole tail for autonomy marker + filename
    autonomous_seen = False
    filename_seen_anywhere = False
    for e in entries:
        text = _message_text(e) or ""
        if _message_role(e) == "user" and AUTONOMOUS_RE.search(text):
            autonomous_seen = True
        if fn_lower in text.lower():
            filename_seen_anywhere = True

    # Rule 1 + 2 — walk from most recent back, look for consent + filename pairing
    recent = entries[-(ROUND_TRIP_WINDOW * 4):]  # search slightly wider
    for i in range(len(recent) - 1, -1, -1):
        e = recent[i]
        if _message_role(e) != "user":
            continue
        user_text = _message_text(e) or ""
        user_lower = user_text.lower()
        has_consent = bool(CONSENT_RE.search(user_text))
        has_filename = fn_lower in user_lower
        if has_consent and has_filename:
            return True, f"rule1:self_contained::{user_text[:200]}"
        if has_consent:
            # Look back ROUND_TRIP_WINDOW messages for an assistant message that named it
            lookback_start = max(0, i - ROUND_TRIP_WINDOW)
            for j in range(i - 1, lookback_start - 1, -1):
                prev = recent[j]
                if _message_role(prev) == "assistant":
                    prev_text = _message_text(prev) or ""
                    if fn_lower in prev_text.lower():
                        return True, f"rule2:cross_turn::assistant[{j}]+user[{i}]::{user_text[:150]}"

    if autonomous_seen and filename_seen_anywhere:
        return True, "rule3:autonomous_preauth::marker+filename_seen"

    return False, ""


def _check_cache(filename: str) -> bool:
    cache = _load_cache()
    now = time.time()
    entry = cache.get(filename)
    if not entry:
        return False
    ts = entry.get("ts", 0)
    if now - ts > CACHE_TTL_SECONDS:
        return False
    return True


def _write_cache(filename: str, context: str) -> None:
    cache = _load_cache()
    cache[filename] = {
        "ts": time.time(),
        "context_sha": _cache_key(filename, context),
        "iso": _now_iso(),
    }
    # Prune expired entries to keep file small
    now = time.time()
    cache = {k: v for k, v in cache.items() if isinstance(v, dict) and now - v.get("ts", 0) <= CACHE_TTL_SECONDS}
    _save_cache(cache)


def _emit(decision: str, reason: str) -> None:
    """Write Claude Code hook protocol response to stdout and exit 0."""
    if decision == "allow":
        # Allow silently; systemMessage optional for audit visibility
        sys.stdout.write(json.dumps({"systemMessage": f"[docx-hook] allow — {reason}"}))
    else:
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))


def _deny_message(filename: str) -> str:
    return (
        f"CLAUDE.md Rule 3 / LD-261 — .docx write BLOCKED.\n\n"
        f"File: {filename}\n\n"
        f"Before writing this .docx, Kim must confirm she has NOT edited this "
        f"specific file since last touch. The hook did not find a filename "
        f"round-trip in recent transcript messages.\n\n"
        f"Ask Kim using the EXACT phrasing from Rule 3:\n"
        f'  "Kim, I\'m about to write `{Path(filename).name}`. Have you made '
        f'any edits to this specific file since we last touched it?"\n\n'
        f"Kim must reply with a consent token (yes / haven\u2019t edited / "
        f"proceed / go ahead) — the filename itself does not need to be repeated "
        f"by Kim, since the hook cross-references your ask with her reply.\n\n"
        f"Bypass: not supported. If this is an autonomous-mode run (LD-232 "
        f"pattern), the pre-authorization message must mention this specific "
        f"filename at least once for the hook to honor it."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        payload = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        _log_shadow({"ts": _now_iso(), "hook": "docx_confirmation", "verdict": "allow_degraded", "reason": "stdin_parse_error"})
        _emit("allow", "hook_error_degraded_stdin")
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    transcript_path = payload.get("transcript_path") or ""
    file_path = tool_input.get("file_path") or ""

    if tool_name not in ("Write", "Edit"):
        return 0  # not our tool
    if not _is_in_scope(file_path):
        return 0  # not a project .docx

    try:
        filename_basename = Path(file_path).name

        # Cache fast-path
        if _check_cache(filename_basename):
            _log_shadow({
                "ts": _now_iso(),
                "hook": "docx_confirmation",
                "verdict": "allow_cached",
                "filename": filename_basename,
            })
            _emit("allow", f"cached confirmation <{CACHE_TTL_SECONDS}s for {filename_basename}")
            return 0

        entries = _read_transcript(transcript_path)
        approved, context = _scan_round_trip(entries, filename_basename)

        if approved:
            _write_cache(filename_basename, context)
            _log_shadow({
                "ts": _now_iso(),
                "hook": "docx_confirmation",
                "verdict": "allow",
                "filename": filename_basename,
                "match_rule": context.split("::", 1)[0] if "::" in context else context,
            })
            _emit("allow", f"round-trip found ({context.split('::', 1)[0]})")
            return 0

        _log_shadow({
            "ts": _now_iso(),
            "hook": "docx_confirmation",
            "verdict": "deny",
            "filename": filename_basename,
            "transcript_msgs_scanned": len(entries),
        })
        _emit("deny", _deny_message(file_path))
        return 0
    except Exception as exc:  # pragma: no cover — fail-open per counter-agent C2
        _log_shadow({
            "ts": _now_iso(),
            "hook": "docx_confirmation",
            "verdict": "allow_degraded",
            "reason": f"exception: {type(exc).__name__}: {exc}",
            "filename": file_path,
        })
        _emit("allow", "hook_error_degraded_exception")
        return 0


if __name__ == "__main__":
    sys.exit(main())
