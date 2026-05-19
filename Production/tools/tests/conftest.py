"""pytest conftest for Production/tools/tests/.

Adds the runtime sys.path entries that production_server.py adds at boot,
so test modules can `import production_server`, `import ffmpeg_stitch`,
etc., without each test re-bootstrapping. Closes audit C8-2 (3 test files
were un-collectable due to ffmpeg_stitch import error).

P5.1 / LD-505 Phase C — 2026-05-19.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent  # Production/tools/
_PROD_DIR = _TOOLS_DIR.parent  # Production/
_REPO_ROOT = _PROD_DIR.parent  # tooling repo root — required for `import Production.*`
_CRED_LIB = _TOOLS_DIR / "credentials_lib"  # ffmpeg_stitch.py lives here too

for p in (_TOOLS_DIR, _PROD_DIR, _REPO_ROOT, _CRED_LIB):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Test-safe env defaults (existing per-file inserts override if needed).
os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")
