"""PHASE_A_ARLO_LAYERED_ROUTE_V1 ? orphan/reconcile wiring contracts."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
PHASES = TOOLS / "server_handlers" / "phases.py"


def _handler_block() -> str:
    block = PHASES.read_text(encoding="utf-8").split("def handle_phase_a_lipsync", 1)[1]
    return block.split("\ndef handle_phase_b_lipsync", 1)[0]


def _layered_handler_block() -> str:
    src = PHASES.read_text(encoding="utf-8")
    block = src.split("def _handle_phase_a_lipsync_layered", 1)[1]
    return block.split("\ndef _handle_phase_a_lipsync_bytedance", 1)[0]


def test_handler_block_is_arlo_layered_single_route():
    block = _handler_block()
    layered = _layered_handler_block()
    assert "PHASE_A_ARLO_LAYERED_ROUTE_V1" in block
    assert "execute_layered_job" in layered
    assert "create_layered_job" in layered
    assert "validate_arlo_layered_assets" in layered
    assert "run_phase_a_arlo_idle_lipsync_startend_still" not in block
    assert "submit_avatar_pro" not in block
    # Dispatcher defaults to layered; ByteDance is opt-in only.
    assert "MN_PHASE_A_BYTEDANCE" in block
    assert "_handle_phase_a_lipsync_bytedance" in block
    assert "return _handle_phase_a_lipsync_layered" in block


def test_handler_budget_gate_is_per_chunk():
    layered = _layered_handler_block()
    assert "plan_layered_lipsync" in layered
    assert "COST_PER_LIPSYNC * chunk_jobs" in layered
    assert "_apply_phase_audio_trim" in layered
    assert "_apply_phase_lipsync_audio_prep(" not in layered


def test_orphan_and_reconcile_wired_into_polling_thread():
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "sweep_phase_a_lipsync_orphan" in server
    assert "reconcile_phase_a_layered_lipsync" in server
    # ByteDance resume remains available but only under MN_PHASE_A_BYTEDANCE.
    assert "MN_PHASE_A_BYTEDANCE" in server
    assert "sweep_phase_a_lipsync_resume" in server


def test_profile_contract_full_loop_30s_rejects_full_also():
    import layered_character_lipsync as engine

    profile = engine.ARLO_PROFILE
    assert profile.route_id == "PHASE_A_ARLO_LAYERED_ROUTE_V1"
    assert [u.name for u in profile.idle_units] == ["full_loop_30s"]
    assert profile.idle_units[0].relative_path.endswith(
        "arlo_gesture_idle_full_loop_30s_green_1920x1080_v1.mp4"
    )
    assert profile.plate_relative_path.endswith(
        "arlo_room_plate_chair_study_1280x720_v2.png"
    )
    assert "green" in profile.chroma_filter or profile.key_rgb[1] > 200
    engine.validate_arlo_idle_contract(profile)
    with pytest.raises(ValueError, match="rejected Arlo idle"):
        engine.assert_idle_path_not_rejected(
            "NEW STYLE CHARACTERS/ARLO/"
            "arlo_gesture_idle_full_also_27s_green_1920x1080_v1.mp4"
        )


class _FakeStateMgr:
    def __init__(self, state: dict):
        self._state = dict(state)
        self.mutations = 0
        self.event_dir = Path("/tmp/Event_3")

    def read_state(self) -> dict:
        return dict(self._state)

    def mutate_state(self, fn):
        self.mutations += 1
        fn(self._state)
        return self._state.get("_module_version", 0)


@pytest.fixture()
def _no_worker(monkeypatch: pytest.MonkeyPatch):
    import server_handlers.phases as phases

    monkeypatch.setattr(phases, "_module_lipsync_worker", None)
    monkeypatch.setattr(phases, "_module_lipsync_worker_owner", None)
    return phases


def test_orphan_sweep_clears_dead_running(_no_worker):
    phases = _no_worker
    mgr = _FakeStateMgr({
        "phase_a_lipsync_status": "running",
        "phase_a_lipsync_started_at": time.time() - 3600,
        "phase_a_lipsync_pending_output": "x.mp4",
        "phase_a_lipsync_pending_audio": "x.mp3",
    })
    phases.sweep_phase_a_lipsync_orphan(mgr)
    snap = mgr.read_state()
    assert snap["phase_a_lipsync_status"].startswith("error: orphan_restart")
    assert "phase_a_lipsync_pending_output" not in snap
    assert "phase_a_lipsync_pending_audio" not in snap
    assert "phase_a_lipsync_started_at" not in snap


def test_orphan_sweep_respects_grace_window(_no_worker):
    phases = _no_worker
    mgr = _FakeStateMgr({
        "phase_a_lipsync_status": "running",
        "phase_a_lipsync_started_at": time.time() - 10,
    })
    phases.sweep_phase_a_lipsync_orphan(mgr)
    assert mgr.read_state()["phase_a_lipsync_status"] == "running"
    assert mgr.mutations == 0


def test_orphan_sweep_leaves_alive_worker_alone(monkeypatch: pytest.MonkeyPatch):
    import server_handlers.phases as phases
    from layered_lipsync_jobs import ModuleLipsyncWorkerOwner

    class _AliveThread:
        @staticmethod
        def is_alive() -> bool:
            return True

    owner = ModuleLipsyncWorkerOwner(
        phase="a",
        event_instance_id="instance",
        event_dir=Path("/tmp/Event_3"),
        event_generation=1,
        job_id="job-alive",
        server_instance_id="server",
    )
    monkeypatch.setattr(phases, "_module_lipsync_worker", _AliveThread())
    monkeypatch.setattr(phases, "_module_lipsync_worker_owner", owner)
    mgr = _FakeStateMgr({
        "phase_a_lipsync_status": "running",
        "phase_a_lipsync_started_at": time.time() - 600,
    })
    mgr.event_dir = Path("/tmp/Event_3")
    phases.sweep_phase_a_lipsync_orphan(mgr)
    assert mgr.read_state()["phase_a_lipsync_status"] == "running"
    assert mgr.mutations == 0
