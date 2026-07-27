"""Regression — BG add-beat must use cross-process sidecar commit (not thread lock only).

2026-06-14: add-beat used _sidecar_lock while O3 subprocesses used sidecar_file_lock().
Concurrent whole-file writes dropped newly inserted beats (e.g. beat_27 vanished).
P4: handlers use mutate_sidecar_locked / update_beat_locked instead of sidecar_file_lock.
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


def test_handle_bg_insert_beat_uses_mutate_sidecar_locked():
    block = _handler_block("handle_bg_insert_beat")
    assert "mutate_sidecar_locked(_insert" in block
    assert "sidecar_file_lock" not in block
    assert "materialize_sidecar_beat_from_plan_row" in block
    assert "create_blank_bg_beat" not in block


def test_handle_bg_add_beat_deprecated_410():
    block = _handler_block("handle_bg_add_beat")
    assert "INSERT_BEAT_FORM_REQUIRED" in block
    assert "410" in block


def test_handle_bg_session_state_read_only_snapshot():
    block = _handler_block("handle_bg_session_state")
    assert "read_sidecar_for_poll_snapshot" in block
    assert "persist_heals" not in block
    assert "_enrich_beats_job_busy" in block
    assert "force_reconcile_o3" in block
    assert "maybe_auto_register_beat_char_ref" not in block


def test_handle_bg_delete_beat_uses_delete_beat_locked():
    block = _handler_block("handle_bg_delete_beat")
    assert "delete_beat_locked" in block
    assert "mutate_sidecar_locked(_delete" not in block
    assert "sidecar_file_lock" not in block
    assert "with bg._sidecar_lock:" not in block


def test_handle_bg_reorder_beats_uses_index_only_locked():
    block = _handler_block("handle_bg_reorder_beats")
    assert "reorder_segment_beats_locked" in block
    assert "migrate=True" not in block
    assert "sidecar_file_lock" not in block
    assert "with bg._sidecar_lock:" not in block


def test_handle_bg_update_beat_syncs_without_heal_redirect():
    text = (
        Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
    ).read_text(encoding="utf-8")
    block = text[text.index("def handle_bg_update_beat"):text.index("\ndef handle_bg_reorder_beats")]
    assert "_BG_ELEMENT_CHAR_REF_SYNC_FIELDS" in block
    assert "identity_fields_written" in block
    assert "sync_element_char_ref_status(b, heal_mismatch=False)" in block
    assert re.search(
        r"if identity_fields_written:\s*\n\s*bg\.sync_element_char_ref_status\(b, heal_mismatch=False(?:, sidecar=sidecar)?\)",
        block,
    ), "bg_update_beat must sync Element gate only for speaker/reference_image writes"
    assert "kling_o3_prompt" not in text[
        text.index("_BG_ELEMENT_CHAR_REF_SYNC_FIELDS"):
        text.index("_BG_ELEMENT_CHAR_REF_SYNC_FIELDS") + 200
    ]


def test_bgtab_wires_beat_missing_guard_helpers():
    text = (
        Path(__file__).resolve().parent.parent / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    ).read_text(encoding="utf-8")
    assert "function isBeatNotFoundResult" in text
    assert "guardBeatPatchResult" in text
    assert "onBeatMissing={handleBeatMissingOnSave}" in text
    for needle in (
        "bg-o3-submit-error",
        "bg-native-lipsync-submit-error",
        "bg-accept-opt-error",
        "bg-select-o3-error",
        "bg-o3-cut-error",
        "bg-still-clip-error",
    ):
        assert needle in text, f"missing beat-missing guard wiring near {needle}"


def test_handle_bg_update_beat_returns_beat_not_found_code():
    block = _handler_block("handle_bg_update_beat")
    assert 'error_code="BEAT_NOT_FOUND"' in block
