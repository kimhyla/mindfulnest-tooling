"""Regression — BG add-beat must use cross-process sidecar lock (not thread lock only).

2026-06-14: add-beat used _sidecar_lock while O3 subprocesses used sidecar_file_lock().
Concurrent whole-file writes dropped newly inserted beats (e.g. beat_27 vanished).
"""
from __future__ import annotations

import re
from pathlib import Path

BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    end = text.index("\ndef ", start + 1)
    return text[start:end]


def test_handle_bg_add_beat_uses_sidecar_file_lock():
    block = _handler_block("handle_bg_add_beat")
    assert "with bg.sidecar_file_lock():" in block
    assert "create_blank_bg_beat" in block
    assert "with bg._sidecar_lock:" not in block


def test_handle_bg_session_state_migrate_write_uses_sidecar_file_lock():
    block = _handler_block("handle_bg_session_state")
    assert re.search(
        r"with bg\.sidecar_file_lock\(\):\s*\n\s*sidecar = bg\.read_sidecar\(\)\s*\n\s*sidecar = bg\._migrate_sidecar",
        block,
    ), "session-state migrate+write must hold cross-process lock"


def test_handle_bg_update_beat_returns_beat_not_found_code():
    block = _handler_block("handle_bg_update_beat")
    assert 'error_code="BEAT_NOT_FOUND"' in block
