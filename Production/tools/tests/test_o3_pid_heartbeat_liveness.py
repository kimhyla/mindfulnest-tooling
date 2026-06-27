"""Category L — PID + heartbeat liveness (v2 terminal model)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import o3_generation_intent as intent_mod
from o3_job_status_contract import beat_job_busy


def test_running_terminal_live_pid_is_busy(tmp_path: Path) -> None:
    event_dir = tmp_path / "Production" / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "livejob1"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    intent_mod.write_o3_job_pid(job_id, event_dir, os.getpid())
    intent_mod.touch_o3_job_heartbeat(job_id, event_dir)
    beat = {"beat_id": beat_id, "o3_current_job_id": job_id}
    assert beat_job_busy(beat, event_dir) is True


def test_running_terminal_stale_heartbeat_not_busy(tmp_path: Path) -> None:
    event_dir = tmp_path / "Production" / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "deadjob2"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    hb = intent_mod.heartbeat_path_for_job(job_id, event_dir)
    hb.write_text("old", encoding="utf-8")
    stale = time.time() - 500
    os.utime(hb, (stale, stale))
    beat = {"beat_id": beat_id, "o3_current_job_id": job_id}
    assert beat_job_busy(beat, event_dir) is False


def test_close_o3_attempt_writes_failed_terminal(tmp_path: Path, monkeypatch) -> None:
    import beat_generator as bg

    event_dir = tmp_path / "Production" / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "close01"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    sidecar = {"arcs": {"arc_1": {"segments": {"event_2_post": {"beats": [{
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
        "kling_o3_status": "approved",
        "status": "o3_element_running",
    }]}}}}}
    monkeypatch.setattr(bg, "read_sidecar", lambda: sidecar)

    def _upd(_bid, fn):
        _, b = bg.find_beat(sidecar, beat_id)
        fn(b, sidecar)
        return True, sidecar

    monkeypatch.setattr(bg, "update_beat_locked", _upd)
    term = intent_mod.close_o3_attempt(
        job_id, beat_id, event_dir, "failed", reason="test", persist_beat=True,
    )
    assert term["status"] == "failed"
    loaded = intent_mod.load_intent_terminal(intent_mod.terminal_path_for_job(job_id, event_dir))
    assert loaded and loaded["status"] == "failed"
