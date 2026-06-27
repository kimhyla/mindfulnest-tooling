"""Autouse test gates + shared import path for Production/tools/tests."""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_TOOLS = _TESTS.parent
_PRODUCTION = _TOOLS.parent
for _p in (_TOOLS, _TOOLS / "credentials_lib", _PRODUCTION):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

import pytest


@pytest.fixture(autouse=True)
def _beatgen_truth_stack_test_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        import beat_generator as bg
        from lib.beatgen_store import BeatgenStore

        BeatgenStore.reset_singleton_for_tests()
        bg.reset_bg_paths_activation_for_tests()
        monkeypatch.setattr(bg, "_BG_EVENT_DIR", None, raising=False)
    except Exception:
        pass
    monkeypatch.setenv("MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE", "1")
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "0")
    yield
    try:
        from lib.beatgen_store import BeatgenStore

        BeatgenStore.reset_singleton_for_tests()
    except Exception:
        pass
