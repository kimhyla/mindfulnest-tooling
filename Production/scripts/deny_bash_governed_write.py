#!/usr/bin/env python3
"""
PreToolUse Bash hook — deny output redirects to governed files.

Wave C / spec v2 §C5. Replaces earlier regex-based inline hook with a
shlex-based parser that correctly distinguishes real redirect targets
from quoted string literals containing governed filenames.

Correctly ALLOWS:
  - Python heredocs that mention governed filenames as string content
  - Comments or docstrings referencing governed filenames
  - Normal tool invocations (git, python3, jq, ls, etc.)

Correctly DENIES:
  - `echo X > firestore.rules`
  - `cat y >> ~/Projects/MindfulNest/firestore/firestore.rules`
  - `tee /path/to/SKILL.md`

Exit 0 = allow. Non-zero + JSON decision = deny.
"""

from __future__ import annotations
import json
import shlex
import sys
from pathlib import Path


# Filename suffixes or substrings that mark a file as governed
GOVERNED_SUFFIXES = (
    "firestore.rules",
    "/SKILL.md",
    "/CLAUDE.md",
    "/settings.json",  # matches ~/.claude/settings.json
)
GOVERNED_SUBSTRINGS = (
    "/.github/workflows/",
    "/maestro/",
    "/functions/",
)
GOVERNED_EXTENSIONS_IN_WORKFLOWS = (".yml", ".yaml")
GOVERNED_EXTENSIONS_IN_MAESTRO = (".yaml",)
GOVERNED_EXTENSIONS_IN_FUNCTIONS = (".ts", ".js")

REDIRECT_OPS = {">", ">>", ">|", "&>", "&>>"}


def is_governed(path: str) -> bool:
    if not path:
        return False
    # Direct suffix match
    for suf in GOVERNED_SUFFIXES:
        if path.endswith(suf):
            return True
    # Substring-and-extension match (workflows/maestro/functions)
    for substr in GOVERNED_SUBSTRINGS:
        if substr in path:
            if substr == "/.github/workflows/" and path.endswith(GOVERNED_EXTENSIONS_IN_WORKFLOWS):
                return True
            if substr == "/maestro/" and path.endswith(GOVERNED_EXTENSIONS_IN_MAESTRO):
                return True
            if substr == "/functions/" and path.endswith(GOVERNED_EXTENSIONS_IN_FUNCTIONS):
                return True
    return False


def scan_for_governed_redirect(command: str) -> tuple[bool, str]:
    """
    Returns (should_deny, target_path_if_any).

    Approach: shlex-tokenize with posix=True (which respects quotes —
    string content stays as one token, not parsed as shell syntax).
    Then walk tokens looking for a redirect operator followed by
    a target. Since shlex STRIPS quotes, a Python heredoc or bash
    single-quoted string becomes a single token with its content —
    NOT parsed for redirect operators.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        # Malformed shell — let it through (bash will error)
        return False, ""

    # Walk tokens: if we see a redirect op followed by a governed path, DENY
    for i, tok in enumerate(tokens):
        if tok in REDIRECT_OPS and i + 1 < len(tokens):
            target = tokens[i + 1]
            if is_governed(target):
                return True, target
        # Also handle fused form: `>file` (no space)
        for op in REDIRECT_OPS:
            if tok.startswith(op) and len(tok) > len(op):
                target = tok[len(op):]
                if is_governed(target):
                    return True, target
                break

    # `tee` special case: tee path1 path2 ...
    for i, tok in enumerate(tokens):
        if tok == "tee":
            for candidate in tokens[i + 1:]:
                if candidate.startswith("-"):
                    continue  # tee flag
                if is_governed(candidate):
                    return True, candidate
                break  # first non-flag arg is the path target

    return False, ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return 0  # malformed input — allow (bash will decide)

    command = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    deny, target = scan_for_governed_redirect(command)

    if deny:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Bash write to governed file blocked.\n"
                    f"Target: {target}\n"
                    f"Use the Edit/Write tool (triggers Rule 19 Phase 0 hook).\n"
                    f"Bypass only with explicit Kim approval + SHORTCUT_ Directus entry."
                ),
            }
        }
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
