"""BG job truth + gallery spec — contract tests (BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

import beat_generator as bg

TOOLS = Path(__file__).resolve().parent.parent
BACKGROUND = TOOLS / "server_handlers" / "background.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    # Nested `def _q` inside handle_bg_session_state — scan to next top-level handler.
    rest = text[start + 1 :]
    end_offset = len(rest)
    for marker in ("\ndef handle_", "\ndef _run_o3", "\ndef _enrich_beats", "\ndef _o3_gallery"):
        idx = rest.find(marker)
        if idx >= 0:
            end_offset = min(end_offset, idx)
    return text[start : start + 1 + end_offset]


def test_beat_job_busy_terminal_wins(tmp_path: Path) -> None:
    from o3_generation_intent import write_intent_terminal
    from o3_job_status_contract import beat_job_busy

    event_dir = tmp_path / "Event_2" / "arlo_o3_jobs"
    event_dir.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_04"
    job_id = "69104d9d"
    write_intent_terminal(job_id, event_dir.parent, {"status": "done", "beat_id": beat_id})
    beat = {
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_ui_job_id": job_id,
        "kling_o3_voice_fix_status": "o3_running",
    }
    with patch("beat_generator._PROD_DIR", str(tmp_path)):
        assert beat_job_busy(beat, event_dir.parent) is False


def test_beat_job_busy_pointer_without_terminal_not_live(tmp_path: Path) -> None:
    from o3_job_status_contract import beat_job_busy

    beat_id = "bg_arc1_event2_pre_beat_04"
    job_id = "abcd1234"
    beat = {"beat_id": beat_id, "o3_current_job_id": job_id}
    event_dir = tmp_path / "Event_2"
    from o3_generation_intent import write_running_terminal_at_submit

    write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    with patch("o3_generation_intent.o3_subprocess_is_live", return_value=False):
        with patch("beat_generator._PROD_DIR", str(tmp_path)):
            assert beat_job_busy(beat, event_dir) is False


def test_beat_job_busy_running_terminal_live_subprocess(tmp_path: Path) -> None:
    from o3_job_status_contract import beat_job_busy

    beat_id = "bg_arc1_event2_pre_beat_04"
    job_id = "abcd1234"
    beat = {"beat_id": beat_id, "o3_current_job_id": job_id}
    event_dir = tmp_path / "Event_2"
    from o3_generation_intent import write_running_terminal_at_submit

    write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    with patch("o3_generation_intent.o3_subprocess_is_live", return_value=True):
        with patch("beat_generator._PROD_DIR", str(tmp_path)):
            assert beat_job_busy(beat, event_dir) is True


def test_clear_o3_pointer_if_terminal(tmp_path: Path) -> None:
    from o3_generation_intent import write_intent_terminal
    from o3_job_status_contract import clear_o3_pointer_if_terminal, resolve_o3_current_job_id

    event_dir = tmp_path / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    job_id = "69104d9d"
    write_intent_terminal(job_id, event_dir, {"status": "done"})
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_04",
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_ui_job_id": job_id,
        "kling_o3_status": "approved",
        "status": "o3_voice_job_running",
        "kling_o3_voice_fix_status": "o3_running",
    }
    with patch("beat_generator._PROD_DIR", str(tmp_path)):
        assert clear_o3_pointer_if_terminal(beat, event_dir) is True
    assert resolve_o3_current_job_id(beat) == ""


def test_pin_slot_assign_preserves_other_slots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bg, "_BG_EVENT_DIR", str(tmp_path / "Event_1"))
    p0 = tmp_path / "g1_element_o3_master_delivery.mp4"
    p1 = tmp_path / "g2_element_o3_master_delivery.mp4"
    p2 = tmp_path / "g3_element_o3_master_delivery.mp4"
    p_new = tmp_path / "g4_element_o3_master_delivery.mp4"
    for p in (p0, p1, p2, p_new):
        p.write_bytes(b"v")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_options": [
            {"video_path": str(p0), "key": "k0", "slot_index": 0},
            {"video_path": str(p1), "key": "k1", "slot_index": 1},
            {"video_path": str(p2), "key": "k2", "slot_index": 2},
        ],
    }
    bg.assign_kling_o3_option_to_slot(
        beat, 2, video_path=str(p_new), label="g4", source="test", now="now", make_active=True,
    )
    slots = bg.build_fixed_o3_ui_slots(beat)
    assert slots[0] is not None and str(slots[0].get("video_path")) == str(p0)
    assert slots[1] is not None and str(slots[1].get("video_path")) == str(p1)
    assert slots[2] is not None and str(slots[2].get("video_path")) == str(p_new)


def test_build_fixed_o3_ui_slots_by_slot_index() -> None:
    beat = {
        "beat_id": "bg_test",
        "pipeline": "kling_o3_omni",
        "kling_o3_options": [
            {"video_path": "/a/g1.mp4", "generation": 1, "slot_index": 2},
            {"video_path": "/a/g9.mp4", "generation": 9, "slot_index": 0},
            {"video_path": "/a/g5.mp4", "generation": 5, "slot_index": 1},
        ],
    }
    slots = bg.build_fixed_o3_ui_slots(beat)
    assert [s.get("generation") if s else None for s in slots] == [9, 5, 1]


def test_reconcile_additive_never_shrinks(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_27"
    g9 = clips / f"{beat_id}_g9_element_o3_master_delivery.mp4"
    g9.write_bytes(b"a")
    beat = {
        "beat_id": beat_id,
        "speaker": "Tessa",
        "pipeline": "kling_o3_omni",
        "kling_o3_options": [
            {"video_path": str(clips / f"{beat_id}_g10_element_o3_master_delivery.mp4"), "slot_index": 0},
        ],
    }
    before = len(beat["kling_o3_options"])
    bg.reconcile_beat_gallery_from_disk(beat, event_dir)
    assert len(beat["kling_o3_options"]) >= before
    paths = {o.get("video_path") for o in beat["kling_o3_options"]}
    assert str(g9.resolve()) in paths


def test_session_get_read_only_no_heal_persist():
    block = _handler_block("handle_bg_session_state")
    assert "persist_heals" not in block
    assert "reconcile_stuck_o3_voice_beats" not in block
    assert "rehydrate_o3_ui_job_ids" not in block
    assert "reconcile_stale_o3_intent_locks_all_events" not in block
    assert "_enrich_beats_job_busy" in block
    assert "if force_reconcile_o3 and scope_event_id" in block
    assert block.index("force_reconcile_o3") < block.index("_run_o3_gallery_repair_for_event")


def test_session_get_no_write_sidecar_in_heal_path():
    block = _handler_block("handle_bg_session_state")
    idle = block.split("force_reconcile_o3 and event_dir.is_dir()", 1)[0]
    assert "mutate_sidecar_locked" not in idle


def test_gallery_repair_at_startup():
    src = BACKGROUND.read_text(encoding="utf-8")
    assert "def schedule_o3_gallery_repair_at_startup" in src
    repair_fn = src.split("def _run_o3_gallery_repair_for_event", 1)[1].split("\ndef ", 1)[0]
    assert "_o3_gallery_repair_runtime_key" in repair_fn


def test_sidecar_fields_from_intent_writes_current_job_id():
    from o3_generation_intent import sidecar_fields_from_intent

    fields = sidecar_fields_from_intent({
        "job_id": "abcd1234",
        "intent_id": "intent-1",
        "prompt": {"verbatim": "hello"},
        "generation": {"replace_slot_index": 2},
    })
    assert fields["o3_current_job_id"] == "abcd1234"
    assert "o3_active_intent_job_id" not in fields


def test_o3_job_status_contract_documented():
    src = (TOOLS / "o3_job_status_contract.py").read_text(encoding="utf-8")
    assert "BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1" in src
    assert "def beat_job_busy" in src


def test_reconcile_additive_assigns_slot_index(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_27"
    g9 = clips / f"{beat_id}_g9_element_o3_master_delivery.mp4"
    g9.write_bytes(b"a")
    beat = {
        "beat_id": beat_id,
        "speaker": "Tessa",
        "pipeline": "kling_o3_omni",
        "kling_o3_options": [],
    }
    bg.reconcile_beat_gallery_from_disk(beat, event_dir)
    assert len(beat["kling_o3_options"]) == 1
    assert isinstance(beat["kling_o3_options"][0].get("slot_index"), int)


def test_ts_job_busy_trusts_server():
    contract = (TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts").read_text(encoding="utf-8")
    busy_fn = contract.split("export function beatO3JobBusy", 1)[1].split("export function", 1)[0]
    assert "typeof beat.job_busy === 'boolean'" in busy_fn
    assert "submitPending" in busy_fn
    assert "return beat.job_busy" in busy_fn
    assert "activeO3Jobs" not in busy_fn
    assert "beatO3JobLooksRunning(beat)" not in busy_fn
    assert "O3_OPTIMISTIC_JOB_TTL_MS" not in contract
    assert "O3_SUBMIT_PENDING_TTL_MS" in contract
    assert "activeO3PollJobsFromBeats" in contract
    bg = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "mergeActiveO3JobsFromBeats" not in bg
    assert "optimisticO3JobsRef" not in bg
    assert "submitPollLatchRef" in bg


def test_assign_does_not_call_refresh_layout():
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    fn = src.split("def assign_kling_o3_option_to_slot", 1)[1].split("\ndef ", 1)[0]
    assert "refresh_o3_ui_slot_layout" not in fn


def test_update_beat_operator_gate_uses_job_busy_not_intent_reconcile():
    block = _handler_block("handle_bg_update_beat")
    patch_fn = block.split("def _patch_beat", 1)[1].split("\n    def ", 1)[0]
    assert "reconcile_stale_o3_intent_locks" not in patch_fn
    assert "_beat_o3_operator_lock_active" in patch_fn


def test_server_operator_gates_use_beat_job_busy_not_legacy_heuristic():
    src = BACKGROUND.read_text(encoding="utf-8")
    update = _handler_block("handle_bg_update_beat")
    lib_drop = src.split("def handle_bg_accept_lib_image", 1)[1].split("\ndef ", 1)[0]
    set_pipe = src.split("def handle_bg_set_pipeline", 1)[1].split("\ndef ", 1)[0]
    for label, block in (
        ("update_beat", update),
        ("accept_lib_image", lib_drop),
        ("set_beat_pipeline", set_pipe),
    ):
        assert "beat_o3_voice_job_running" not in block, label
        assert "_beat_o3_operator_lock_active" in block, label
    looks = src.split("def _beat_o3_job_looks_running", 1)[1].split("\ndef ", 1)[0]
    assert "beat_o3_voice_job_running" in looks
    bg_src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    assert "def _beat_pipeline_operator_busy" in bg_src
    pipe_fn = bg_src.split("def set_beat_pipeline_mode", 1)[1].split("\ndef ", 1)[0]
    assert "_beat_pipeline_operator_busy" in pipe_fn
    assert "beat_o3_voice_job_running(beat)" not in pipe_fn

def test_submit_commit_no_intent_reconcile():
    block = _handler_block("handle_bg_submit_arlo_o3_voice")
    commit_fn = block.split("def _commit_o3", 1)[1].split("\n        ok, _ = bg.update_beat_locked", 1)[0]
    assert "reconcile_stale_o3_intent_locks" not in commit_fn


def test_o3_admin_reconcile_endpoint_and_startup():
    src = BACKGROUND.read_text(encoding="utf-8")
    assert "def handle_bg_o3_admin_reconcile" in src
    assert "def run_blocking_o3_startup" in src
    assert "def _run_o3_admin_reconcile" in src
    admin_fn = src.split("def handle_bg_o3_admin_reconcile", 1)[1].split("\ndef ", 1)[0]
    assert "allow_missing_video_role=True" in admin_fn
    ps = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/bg/o3/admin-reconcile" in ps
    startup = ps.split("schedule_o3_gallery_repair_at_startup(app)", 1)[0]
    assert "run_blocking_o3_startup(app)" in startup

def test_refresh_o3_ui_slot_layout_no_generation_sort():
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    fn = src.split("def refresh_o3_ui_slot_layout", 1)[1].split("\ndef ", 1)[0]
    assert "_sync_o3_option_gen_label" in fn
    assert "sorted(" not in fn
    assert "slot_index" not in fn.split("_sync_o3_option_gen_label", 1)[1]
