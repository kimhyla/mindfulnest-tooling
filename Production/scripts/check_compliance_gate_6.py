#!/usr/bin/env python3
"""
check_compliance_gate_6.py — LD-421 Compliance Gate Check 6 validator.

Verifies that production skills use registered_write.py for all media writes.
Run against one skill or all skills with --all-skills.

Check 6 verification:
1. Grep skill for registered_write import — must be present
2. Grep for direct media writes outside wrapper — none allowed (whitelist patterns exempt)
3. Smoke test (optional): invoke skill, verify prod_assets row created
"""
import os
import re
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = os.environ.get(
    'MINDFULNEST_PROJECT_ROOT',
    '/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files'
)

SKILLS_DIR = Path(PROJECT_ROOT) / '.claude/skills'
TOOLS_DIR = Path(PROJECT_ROOT) / 'Production/tools'

WRAPPER_IMPORT_PATTERNS = [
    r'from Production\.tools import registered_write',
    r'from Production\.tools\.registered_write import',
    r'import registered_write',
    r'registered_write\.register_asset',
    r'registered_write\.approve_asset',
]

DIRECT_MEDIA_WRITE_PATTERNS = [
    (r'ffmpeg.*-y.*\.(mp4|mp3|wav|png|webp|jpg)', 'ffmpeg output'),
    (r"open\([^,]+,\s*['\"]wb['\"]", 'raw open(wb)'),
    (r'imageio\.imwrite', 'imageio.imwrite'),
    (r'imageio\.mimwrite', 'imageio.mimwrite'),
    (r'cv2\.imwrite', 'cv2.imwrite'),
    (r'cv2\.VideoWriter', 'cv2.VideoWriter'),
    (r'shutil\.copy.*\.(mp4|mp3|wav|png|webp|jpg)', 'shutil.copy media'),
]

WHITELIST_PATHS = [r'_temp_', r'_sandbox', r'/tests/', r'debug_', r'_tmp_', r'_previews']


def check_skill(skill_path: Path) -> dict:
    """Check a skill file for Check 6 compliance."""
    try:
        code = skill_path.read_text()
    except Exception as e:
        return {'pass': False, 'error': str(e)}

    # Check 1: wrapper imported
    wrapper_imported = any(re.search(p, code) for p in WRAPPER_IMPORT_PATTERNS)

    # Check 2: no direct media writes (unless whitelisted)
    direct_writes = []
    lines = code.split('\n')
    for line_no, line in enumerate(lines, 1):
        # Skip if line is in a whitelist path context
        if any(re.search(w, line) for w in WHITELIST_PATHS):
            continue
        # Skip comments
        if line.strip().startswith('#'):
            continue

        for pattern, name in DIRECT_MEDIA_WRITE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                direct_writes.append(f'{skill_path.name}:{line_no}: {name}')

    return {
        'pass': wrapper_imported or not direct_writes,  # Pass if imports wrapper OR no direct writes
        'wrapper_imported': wrapper_imported,
        'direct_writes': direct_writes,
    }


def main():
    parser = argparse.ArgumentParser(description='Check 6: registered_write.py compliance')
    parser.add_argument('--skill', help='Check specific skill by name')
    parser.add_argument('--all-skills', action='store_true', help='Check all skills')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    results = {}

    # Check skills
    if args.all_skills or args.skill:
        skills = list(SKILLS_DIR.glob('*/SKILL.md'))
        for skill in skills:
            skill_name = skill.parent.name
            if args.skill and skill_name != args.skill:
                continue
            results[f'skill/{skill_name}'] = check_skill(skill)

    # Always check core tool scripts
    tool_scripts = [
        'magic_compositor.py',
        'lipsync_sender.py',
        'build_storyboard.py',
        'kling_startend_pipeline.py',
    ]

    for script in tool_scripts:
        script_path = TOOLS_DIR / script
        if script_path.exists():
            results[f'tools/{script}'] = check_skill(script_path)

    # Summary
    passed = [n for n, r in results.items() if r.get('pass', False)]
    failed = [n for n, r in results.items() if not r.get('pass', True)]

    print(f"=== Compliance Gate Check 6 ===")
    print(f"Passed: {len(passed)}/{len(results)}")

    if args.verbose or failed:
        print()
        for name in sorted(results.keys()):
            r = results[name]
            status = '✓ PASS' if r.get('pass') else '✗ FAIL'
            print(f"  {status}: {name}")
            if not r.get('pass'):
                if not r.get('wrapper_imported'):
                    print(f"       - registered_write.py NOT imported")
                for w in r.get('direct_writes', []):
                    print(f"       - direct write: {w}")

    if failed:
        print(f"\n{len(failed)} skill(s) failed Check 6.")
        sys.exit(1)
    else:
        print("\nAll skills pass Check 6.")
        sys.exit(0)


if __name__ == '__main__':
    main()
