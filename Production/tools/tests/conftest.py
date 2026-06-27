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

# Ignore script-mode browser E2E runner. test_tier3_browser_e2e.py has its
# own `if __name__ == "__main__": sys.exit(main())` orchestrator and passes
# Playwright `browser` as a function parameter, NOT a pytest fixture. Pytest
# collection of this file produces 13 spurious "fixture 'browser' not found"
# errors. Run via: python3 Production/tools/tests/test_tier3_browser_e2e.py
collect_ignore = [
    "test_tier3_browser_e2e.py",
]


import pytest


@pytest.fixture(autouse=True)
def _isolate_kling_character_registry_prod_root():
    """Tests call set_prod_root(tmp_path); reset so later tests see real registry."""
    from tools import kling_character_registry as reg

    saved = reg._PROD_ROOT  # noqa: SLF001 — test isolation only
    yield
    reg._PROD_ROOT = saved  # noqa: SLF001


_SQLITE_OPT_IN_MODULES = frozenset({
    "test_beatgen_store",
    "test_sidecar_sqlite_cutover_gate",
})


@pytest.fixture(autouse=True)
def _json_sidecar_default_unless_sqlite_test(monkeypatch, request):
    """Live ~/.mindfulnest/state/beatgen.db must not hijack JSON-path contract tests."""
    mod = getattr(request.node.module, "__name__", "") or ""
    base = mod.rsplit(".", 1)[-1]
    if base in _SQLITE_OPT_IN_MODULES:
        return
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "0")
    try:
        from lib.beatgen_store import BeatgenStore

        BeatgenStore.reset_singleton_for_tests()
    except Exception:
        pass
