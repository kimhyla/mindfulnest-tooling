"""Sidecar lock starvation — slow work must never run under beat_generator_state.json.lock."""
from __future__ import annotations

import re
from pathlib import Path

BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"
BEAT_GEN = Path(__file__).resolve().parent.parent / "beat_generator.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    end = text.index("\ndef ", start + 1)
    return text[start:end]


def _first_index(section: str, needle: str) -> int:
    idx = section.index(needle)
    assert idx >= 0, needle
    return idx


def test_background_handlers_have_no_sidecar_file_lock():
    text = BACKGROUND.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "sidecar_file_lock" in line and not line.strip().startswith("#"):
            raise AssertionError(
                f"background.py must not call sidecar_file_lock (P4): {line.strip()}"
            )


def test_background_handlers_use_sqlite_sidecar_apis():
    text = BACKGROUND.read_text(encoding="utf-8")
    assert "update_beat_locked" in text
    assert "mutate_sidecar_locked" in text


def test_submit_builds_intent_before_sidecar_commit():
    block = _handler_block("handle_bg_submit_arlo_o3_voice")
    assert "WaveSpeed / Element registration — never under sidecar_file_lock." in block
    intent_idx = _first_index(block, "build_generation_intent(")
    commit_idx = _first_index(block, "update_beat_locked(str(beat_id), _commit_o3)")
    assert intent_idx < commit_idx


def test_submit_writes_intent_after_sidecar_commit():
    block = _handler_block("handle_bg_submit_arlo_o3_voice")
    commit_idx = block.index("update_beat_locked(str(beat_id), _commit_o3)")
    write_idx = block.index("write_generation_intent(committed_intent")
    assert write_idx > commit_idx


def test_submit_reattach_before_intent_and_commit():
    """BG_O3_SUBMIT_UI_REATTACH_V1 — dedup/reattach must run before intent build + sidecar commit."""
    block = _handler_block("handle_bg_submit_arlo_o3_voice")
    reattach_idx = block.index("_o3_submit_reattach_response_if_running(")
    intent_idx = block.index("committed_intent = build_generation_intent(")
    commit_idx = block.index("update_beat_locked(str(beat_id), _commit_o3)")
    assert reattach_idx < intent_idx < commit_idx


def test_update_beat_element_registration_before_lock():
    block = _handler_block("handle_bg_update_beat")
    pre_idx = _first_index(block, "try_register_dropped_char_ref_on_element(")
    lock_idx = _first_index(block, "update_beat_locked(beat_id, _patch_beat)")
    assert pre_idx < lock_idx
    lock_body = block[lock_idx:]
    assert "try_register_dropped_char_ref_on_element(" not in lock_body


def test_gallery_repair_disk_work_outside_lock():
    repair_fn = BACKGROUND.read_text(encoding="utf-8").split(
        "def _run_o3_gallery_repair_for_event", 1
    )[1].split("\ndef ", 1)[0]
    assert "_plan_o3_gallery_repair_for_event" in repair_fn
    plan_idx = repair_fn.index("_plan_o3_gallery_repair_for_event")
    lock_idx = repair_fn.index("mutate_sidecar_locked(_commit, timeout_s=10)")
    assert plan_idx < lock_idx
    assert "reconcile_beat_gallery_from_disk" not in repair_fn.split("mutate_sidecar_locked", 1)[1]


def test_select_o3_migrate_and_validate_before_lock():
    block = _handler_block("handle_bg_select_o3_video")
    lock_idx = block.index("update_beat_locked")
    assert "_select" in block[lock_idx : lock_idx + 120]
    assert "_migrate_sidecar(sidecar_probe)" in block
    assert block.index("_migrate_sidecar(sidecar_probe)") < lock_idx
    assert "_migrate_sidecar(sidecar)" not in block.split("update_beat_locked", 1)[1]


def test_session_get_read_only_no_heal_persist_lock():
    block = _handler_block("handle_bg_session_state")
    assert "persist_heals" not in block
    assert "_apply_session_heal_deltas" not in block
    assert "if force_reconcile_o3 and scope_event_id" in block


def test_sidecar_file_lock_defaults_to_bounded_acquire():
    text = BEAT_GEN.read_text(encoding="utf-8")
    assert "SIDECAR_LOCK_DEFAULT_TIMEOUT_S" in text
    assert "SIDECAR_LOCK_HOLD_WARN_S" in text
    lock_fn = text.split("def sidecar_file_lock", 1)[1].split("\ndef ", 1)[0]
    assert "if timeout_s is None:" in lock_fn
    assert "SIDECAR_LOCK_DEFAULT_TIMEOUT_S" in lock_fn
    assert "held_s >= SIDECAR_LOCK_HOLD_WARN_S" in lock_fn
