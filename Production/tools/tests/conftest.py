"""Autouse test gates for Beat Gen Truth Stack."""
from __future__ import annotations

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
    yield
    try:
        from lib.beatgen_store import BeatgenStore

        BeatgenStore.reset_singleton_for_tests()
    except Exception:
        pass
