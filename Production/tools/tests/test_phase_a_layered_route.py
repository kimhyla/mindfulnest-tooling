"""Phase A ByteDance default + optional layered reconcile markers."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
PHASES = TOOLS / "server_handlers" / "phases.py"


def _handler_block() -> str:
    block = PHASES.read_text(encoding="utf-8").split("def handle_phase_a_lipsync", 1)[1]
    return block.split("\ndef handle_phase_b_lipsync", 1)[0]


def test_handler_block_is_bytedance_base_clip_not_layered():
    block = _handler_block()
    assert "run_phase_a_base_clip_bytedance_lipsync" in block
    assert "base_clip_bytedance_tight_v1" in block or "PHASE_A_BYTEDANCE_METHOD" in block
    assert "execute_layered_job" not in block
    assert "create_layered_job" not in block
    assert "PHASE_A_ARLO_LAYERED_ROUTE_V1" not in block
    assert "run_phase_a_arlo_idle_lipsync_startend_still" not in block
    assert "submit_avatar_pro" not in block


def test_handler_budget_gate_is_single_bytedance_job():
    block = _handler_block()
    assert "COST_PER_LIPSYNC * lipsync_jobs" in block
    assert "lipsync_jobs = 1" in block
    assert "_apply_phase_audio_trim" in block


def test_resume_wired_into_polling_thread():
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "sweep_phase_a_lipsync_resume" in server
    assert "sweep_phase_a_lipsync_orphan" not in server
    # Layered Phase A reconcile is opt-in only.
    assert "MN_PHASE_A_LAYERED" in server
    assert "reconcile_phase_b_layered_lipsync" in server


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

    monkeypatch.setattr(phases, "_phase_a_lipsync_worker", None)
    return phases


def test_resume_sweep_clears_dead_running_without_tmp(_no_worker, tmp_path: Path):
    phases = _no_worker
    mgr = _FakeStateMgr({
        "phase_a_lipsync_status": "running",
        "phase_a_lipsync_started_at": time.time() - 3600,
        "phase_a_lipsync_pending_output": "x.mp4",
        "phase_a_lipsync_pending_audio": "x.mp3",
    })
    mgr.event_dir = tmp_path
    phases.sweep_phase_a_lipsync_resume(mgr)
    snap = mgr.read_state()
    assert snap["phase_a_lipsync_status"].startswith("error: orphan_restart")
    assert "phase_a_lipsync_pending_output" not in snap
    assert "phase_a_lipsync_pending_audio" not in snap
    assert "phase_a_lipsync_started_at" not in snap


def test_resume_sweep_respects_grace_window(_no_worker, tmp_path: Path):
    phases = _no_worker
    mgr = _FakeStateMgr({
        "phase_a_lipsync_status": "running",
        "phase_a_lipsync_started_at": time.time() - 10,
    })
    mgr.event_dir = tmp_path
    phases.sweep_phase_a_lipsync_resume(mgr)
    assert mgr.read_state()["phase_a_lipsync_status"] == "running"
    assert mgr.mutations == 0
