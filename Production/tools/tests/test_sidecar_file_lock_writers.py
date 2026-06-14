"""Regression — every sidecar read/modify/write must use cross-process file lock.

2026-06-14: O3 subprocesses used thread-only ``_sidecar_lock`` while add-beat used
``sidecar_file_lock()``. Concurrent whole-file writes dropped newly inserted beats
(e.g. char-ref drop on beat_27 → BEAT_NOT_FOUND immediately after Insert).
"""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent


def _module_text(relpath: str) -> str:
    return (TOOLS / relpath).read_text(encoding="utf-8")


def test_kling_o3_sidecar_writes_use_file_lock():
    text = _module_text("server_handlers/kling_o3.py")
    assert "with bg.sidecar_file_lock():" in text
    assert "with bg._sidecar_lock:" not in text


def test_background_sidecar_writes_use_file_lock():
    text = _module_text("server_handlers/background.py")
    assert "with bg.sidecar_file_lock():" in text
    assert "with bg._sidecar_lock:" not in text


def test_production_server_sidecar_writes_use_file_lock():
    text = _module_text("production_server.py")
    assert "with bg.sidecar_file_lock():" in text
    assert "with bg._sidecar_lock:" not in text
