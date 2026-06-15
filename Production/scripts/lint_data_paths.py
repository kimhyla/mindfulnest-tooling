#!/usr/bin/env python3
"""Lint guard — fail on new `__file__`-derived DATA paths in handler modules.

LD-505 Phase C (2026-05-19) — closes the class of bugs that caused PR #73:
when production_server.py runs from ~/Projects/mindfulnest-tooling/ but
DATA lives in Dropbox, any path computed from `Path(__file__)` lands in
the (empty) tooling tree. The fix is to derive data paths from the
runtime event_dir via `Production/lib/paths.runtime_production_root(...)`
or per-handler `_data_root(h)`.

This script enforces the policy by greping the scoped files. Allow-listed
sites: sys.path inserts to import sibling Python modules, HTML template
loads (HTML IS code), and the canonical resolver itself.

Exit code 0 on clean; 1 on violations. Designed for pre-push hook.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # Production/scripts/.. -> repo root

# Files in scope. Add more as new handler modules land.
SCOPED_FILES = [
    "Production/tools/server_handlers/background.py",
    "Production/tools/server_handlers/phases.py",
    "Production/tools/server_handlers/stitch_editor.py",
    "Production/tools/server_handlers/cropper.py",
    "Production/tools/server_handlers/beats_legacy.py",
    "Production/tools/server_handlers/beats_v2.py",
    "Production/tools/server_handlers/core.py",
    "Production/tools/server_handlers/event_video.py",
    "Production/tools/server_handlers/timeline.py",
    "Production/tools/server_handlers/vendor_jobs.py",
    "Production/tools/magic_compositor.py",
]

# Allow-listed patterns — these uses of __file__ are legitimate code-tree
# operations (sys.path insert to import a sibling .py, loading a shipped
# HTML template, locating a sibling sql/yaml schema in the code tree).
ALLOWED_SUBSTRINGS = [
    "sys.path.insert",
    "sys.path.append",
    'stitch_editor.html',
    'path_picker.html',
    '_PSERVER_TOOLS_DIR = Path(__file__)',  # the code-tree anchor itself
    'CODE tree',  # explicit annotation acknowledging code-tree intent
    'code-vs-data',
]

# Pattern that signals a possible data-path use of __file__:
# any line containing `__file__` that does NOT match an allowed pattern.
PATTERN = re.compile(r'__file__')


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    for rel in SCOPED_FILES:
        fp = REPO_ROOT / rel
        if not fp.is_file():
            continue
        all_lines = fp.read_text().splitlines()
        for i, line in enumerate(all_lines, start=1):
            if not PATTERN.search(line):
                continue
            if any(s in line for s in ALLOWED_SUBSTRINGS):
                continue
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Skip if line is inside a docstring referring to an old constant
            # (heuristic: line contains backtick-quoted code referring to __file__).
            if '`' in line and '__file__' in line:
                continue
            # Look at preceding 6 lines for a "CODE tree" annotation comment.
            # i is 1-indexed; all_lines is 0-indexed; line i is all_lines[i-1].
            window = all_lines[max(0, i-7):i-1]
            if any(any(s in w for s in ALLOWED_SUBSTRINGS) for w in window):
                continue
            violations.append((rel, i, stripped))

    if not violations:
        print("[lint_data_paths] OK — no __file__ data-path uses in handler modules.")
        return 0

    print("[lint_data_paths] FAIL — __file__ used in handler modules for non-allow-listed sites:")
    for rel, ln, body in violations:
        print(f"  {rel}:{ln}  {body[:120]}")
    print()
    print("LD-505 Phase C policy: derive runtime DATA paths from event_dir via")
    print("`Production/lib/paths.runtime_production_root(h.app.event_dir)` or the")
    print("per-handler `_data_root(h)` helper. Use _PSERVER_TOOLS_DIR ONLY for")
    print("CODE-tree lookups (sys.path inserts, sibling Python imports, HTML")
    print("templates). Annotate code-tree uses with a 'CODE tree' comment so the")
    print("linter can ignore them.")
    print()
    print("Bypass for emergency: MN_SKIP_DATA_PATH_LINT=1 git push --no-verify")
    return 1


if __name__ == "__main__":
    sys.exit(main())
