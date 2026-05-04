#!/usr/bin/env python3
"""
asset_findability_hook.py — PreToolUse hook (Hook A from LD-421 spec).

Intercepts Bash + Write tool calls that produce media files under Production/.
Denies writes that don't carry the registered_write.py wrapper sentinel.

Modes (env var MINDFULNEST_HOOK_MODE):
  shadow  - log to hook_shadow_log.jsonl, always allow (DEFAULT for first 7 days)
  enforce - deny non-wrapper writes (after Kim flips the env var)

Fail-open: any internal exception → log + allow with reason='hook_error_degraded'.
"""
import json
import os
import re
import sys
import shlex
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = os.environ.get(
    'MINDFULNEST_PROJECT_ROOT',
    '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files'
)
HOOK_LOG = Path.home() / '.claude/mindfulnest-cache/asset_findability_hook_log.jsonl'
MODE = os.environ.get('MINDFULNEST_HOOK_MODE', 'shadow')

MEDIA_EXTS = ('.mp4', '.mp3', '.wav', '.png', '.webp', '.jpg', '.jpeg', '.mov')

# Whitelist: paths that don't need wrapper (intermediates, tests, archives, sandbox)
WHITELIST_PATTERNS = [
    r'/_temp_',
    r'/_tmp_',
    r'/__pycache__/',
    r'/_sandbox/',
    r'/_archive_',
    r'/tests?/',
    r'/debug_',
    r'\.tmp\.',
    r'/_previews/',  # HTML previews are exempt
]

WRAPPER_SENTINELS = [
    'registered_write',
    '__MINDFULNEST_REGISTERED_WRITE__',
    'registered_write.register_asset',
    'registered_write.approve_asset',
]


def detect_media_write(tool_name: str, tool_input: dict) -> tuple:
    """Returns (is_media_write, file_path) — file_path is the destination."""
    if tool_name == 'Write':
        path = tool_input.get('file_path', '')
        if any(path.endswith(ext) for ext in MEDIA_EXTS) and PROJECT_ROOT in path:
            return True, path
    elif tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        # ffmpeg outputs, cp/mv with media destinations
        if any(ext in cmd for ext in MEDIA_EXTS):
            try:
                tokens = shlex.split(cmd, posix=True)
            except ValueError:
                return False, None
            for tok in tokens:
                if any(tok.endswith(ext) for ext in MEDIA_EXTS) and PROJECT_ROOT in tok:
                    return True, tok
    return False, None


def is_whitelisted(file_path: str) -> bool:
    return any(re.search(p, file_path) for p in WHITELIST_PATTERNS)


def has_wrapper_sentinel(tool_name: str, tool_input: dict) -> bool:
    if tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        return any(s in cmd for s in WRAPPER_SENTINELS)
    if tool_name == 'Write':
        # Write tool can't carry sentinel; must go through Bash subprocess in wrapper
        return False
    return False


def emit_allow(reason: str = None):
    if reason:
        print(json.dumps({'systemMessage': f'Hook A: allow ({reason})'}))
    sys.exit(0)


def emit_deny(reason: str):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason,
        }
    }))
    sys.exit(0)


def log(record: dict):
    HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
    record['timestamp'] = datetime.utcnow().isoformat()
    record['hook'] = 'asset_findability_hook'
    record['mode'] = MODE
    with HOOK_LOG.open('a') as f:
        f.write(json.dumps(record) + '\n')


def main():
    try:
        payload = json.loads(sys.stdin.read())
        tool_name = payload.get('tool_name')
        tool_input = payload.get('tool_input', {})

        is_media, file_path = detect_media_write(tool_name, tool_input)
        if not is_media:
            sys.exit(0)  # Not relevant; allow silently

        if is_whitelisted(file_path):
            log({'verdict': 'allow', 'reason': 'whitelisted', 'path': file_path})
            sys.exit(0)

        if has_wrapper_sentinel(tool_name, tool_input):
            log({'verdict': 'allow', 'reason': 'wrapper_sentinel', 'path': file_path})
            sys.exit(0)

        # Match — would deny
        log({
            'verdict': 'would_deny' if MODE == 'shadow' else 'deny',
            'reason': 'no_wrapper_sentinel',
            'path': file_path,
            'tool_name': tool_name
        })

        if MODE == 'shadow':
            sys.exit(0)  # Shadow mode: log + allow

        emit_deny(
            f'Hook A: media write to {file_path} did not go through registered_write.py wrapper.\n'
            f'Per LD-421 + Compliance Gate Check 6, all media writes under Production/ must use:\n'
            f'  from Production.tools import registered_write\n'
            f'  registered_write.register_asset(file_path=..., asset_type=..., ...)\n'
            f'Or for ad-hoc one-shot writes that should not be registered, use a path matching\n'
            f'  whitelist pattern (e.g., Production/_sandbox/, Production/_temp_*/, /tests/).'
        )

    except Exception as e:
        # Fail-open per LD-261 precedent
        log({'verdict': 'allow_degraded', 'error': str(e), 'mode': MODE})
        sys.exit(0)


if __name__ == '__main__':
    main()
