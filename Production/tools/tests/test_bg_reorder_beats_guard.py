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
    # BG_REORDER_INDEX_ONLY_V1 — never heavy-migrate on ↑/↓ hot path.
    assert "reorder_segment_beats_locked" in block
    assert "migrate=True" not in block
    assert "_bg_reorder_audit" in block
    # Docstring may mention migrate; call site must not invoke it.
    code_only = block.split('"""', 2)[-1] if '"""' in block else block
    assert "_migrate_sidecar(" not in code_only


def test_reorder_segment_beats_locked_exists():
    src = (
        Path(__file__).resolve().parent.parent / "beat_generator.py"
    ).read_text(encoding="utf-8")
    assert "def reorder_segment_beats_locked" in src
    assert "migrate=False" in src.split("def reorder_segment_beats_locked")[1].split(
        "\ndef update_beat_locked"
    )[0]
