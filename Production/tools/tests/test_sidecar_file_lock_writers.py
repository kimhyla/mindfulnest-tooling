"""Regression — handler sidecar writes use SQLite store APIs (P4 cutover).

2026-06-14: O3 subprocesses used thread-only ``_sidecar_lock`` while add-beat used
``sidecar_file_lock()``. Concurrent whole-file writes dropped newly inserted beats.

P4+: ``background.py``, ``kling_o3.py``, and ``production_server.py`` must use
``update_beat_locked`` / ``mutate_sidecar_locked`` / ``read_sidecar`` — not flock.
"""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent


def _module_text(relpath: str) -> str:
    return (TOOLS / relpath).read_text(encoding="utf-8")


def test_kling_o3_sidecar_writes_use_store_api():
    text = _module_text("server_handlers/kling_o3.py")
    assert "update_beat_locked(" in text
    assert "mutate_sidecar_locked(" in text
    assert "with bg.sidecar_file_lock():" not in text
    assert "with bg._sidecar_lock:" not in text


def test_background_sidecar_writes_use_store_api():
    text = _module_text("server_handlers/background.py")
    assert "update_beat_locked(" in text
    assert "mutate_sidecar_locked(" in text
    assert "with bg.sidecar_file_lock():" not in text
    assert "with bg._sidecar_lock:" not in text


def test_production_server_sidecar_writes_use_store_api():
    text = _module_text("production_server.py")
    assert "update_beat_locked(" in text
    assert "with bg.sidecar_file_lock():" not in text
    assert "with bg._sidecar_lock:" not in text
