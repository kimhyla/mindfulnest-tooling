"""Reorder must not truncate segments — full beat_id set required."""
from __future__ import annotations

from pathlib import Path


def test_reorder_rejects_partial_beat_id_list():
    src = (
        Path(__file__).resolve().parent.parent
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("def handle_bg_reorder_beats")[1].split("\ndef handle_bg_delete_beat")[0]
    assert "REORDER_BEAT_COUNT_MISMATCH" in block
    assert "REORDER_BEAT_SET_MISMATCH" in block
    assert "len(incoming_ids) != len(existing_ids)" in block
