#!/usr/bin/env python3
"""
asset_lookup_hook.py — UserPromptSubmit hook (Hook B from LD-421 spec).

Detects asset reference phrases in Kim's prompts. Sets asset_focus.json
so Claude knows to use find_asset.py first before disk inspection.

Mode (env var MINDFULNEST_HOOK_MODE): shadow | enforce
Phase 0 amendment: tightened regex to require media-specific context.
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Tightened regex (Phase 0 amendment) - require media-specific context
ASSET_REFERENCE_PHRASES = [
    r'\bthe approved (video|clip|audio|mp4|render|magic|asset)\b',
    r'\bfind the (video|clip|audio|music|render|magic|animation|lipsync)\b',
    r'\bremember (that |the )?(video|clip|render|animation|lipsync)\b',
    r'\bthe (music|audio|video|clip|render|magic|tts|voice) (from|for|where|that)\b',
    r'\blatest .* (portrait|render|version|clip|video|animation)\b',
    r'\bcanonical (final|version|video|clip)\b',
    r'\bwhere.?s the (video|clip|audio|render|magic)\b',
    r'\bI (need|want) the (video|clip|audio|render|magic|animation)\b',
    r'\bthe one with .* (lipsync|animation|magic|audio|music)\b',
]

ASSET_FOCUS_FILE = Path.home() / '.claude/mindfulnest-cache/asset_focus.json'
HOOK_LOG = Path.home() / '.claude/mindfulnest-cache/asset_lookup_hook_log.jsonl'
MODE = os.environ.get('MINDFULNEST_HOOK_MODE', 'shadow')


def detect_phrase(prompt: str) -> tuple:
    for pattern in ASSET_REFERENCE_PHRASES:
        m = re.search(pattern, prompt, re.IGNORECASE)
        if m:
            return True, m.group(0)
    return False, None


def write_focus(prompt: str, phrase: str):
    """Set asset_focus.json — Claude reads this on next tool call."""
    ASSET_FOCUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'timestamp': datetime.utcnow().isoformat(),
        'prompt': prompt[:500],
        'phrase': phrase,
        'expires_at': time.time() + 300,  # 5-min TTL
    }
    ASSET_FOCUS_FILE.write_text(json.dumps(data))


def log(record: dict):
    HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
    record['timestamp'] = datetime.utcnow().isoformat()
    record['hook'] = 'asset_lookup_hook'
    record['mode'] = MODE
    with HOOK_LOG.open('a') as f:
        f.write(json.dumps(record) + '\n')


def main():
    try:
        payload = json.loads(sys.stdin.read())
        prompt = payload.get('prompt', '')

        detected, phrase = detect_phrase(prompt)
        if not detected:
            sys.exit(0)

        write_focus(prompt, phrase)
        log({'verdict': 'detected', 'phrase': phrase, 'prompt_excerpt': prompt[:200]})

        # In enforce mode, also emit a system message
        if MODE == 'enforce':
            print(json.dumps({
                'systemMessage':
                    f'Hook B: asset reference phrase detected ("{phrase}"). '
                    f'Per Rule 31 + LD-421, query Directus first via find_asset.py:\n'
                    f'  python3 Production/tools/find_asset.py --phrase "<phrase>" --module <int>\n'
                    f'Disk inspection (Read, Glob, Bash ls/find) on media paths is BLOCKED until '
                    f'find_asset.py returns. If find_asset returns zero matches, then disk fallback is allowed.'
            }))
        sys.exit(0)

    except Exception as e:
        log({'verdict': 'allow_degraded', 'error': str(e)})
        sys.exit(0)


if __name__ == '__main__':
    main()
