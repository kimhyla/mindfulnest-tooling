"""O3 job liveness — pointer without subprocess must not stay busy forever."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import o3_generation_intent as intent_mod


def _sidecar_beat(beat_id: str, job_id: str) -> dict:
    return {
        "beat_id": beat_id,
        "status": "o3_element_running",
        "kling_o3_status": "submitted",
        "kling_o3_voice_fix_status": "o3_running",
        "kling_o3_voice_fix_phase": "subprocess",
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_ui_job_id": job_id,
        "kling_o3_video_path": f"/Event_2/kling_o3_clips/{beat_id}_g3_element_o3_master_delivery.mp4",
    }


def test_subprocess_running_matches_element_pipeline(tmp_path: Path) -> None:
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "f2db16c2"
    line = (
        f"12345 python /tools/kling_o3_element_beat_pipeline.py "
        f"--beat-id {beat_id} --job-id {job_id} "
        f"/Event_2/arlo_o3_jobs/{job_id}_{beat_id}.log"
    )
    with patch("subprocess.check_output", return_value=line):
        assert intent_mod.subprocess_running_for_o3_job(job_id, beat_id) is True


def test_o3_subprocess_not_live_when_pid_and_heartbeat_stale(tmp_path: Path) -> None:
    event_dir = tmp_path / "Production" / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "f2db16c2"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    pid_path = intent_mod.pid_path_for_job(job_id, event_dir)
    pid_path.write_text("999999", encoding="utf-8")
    hb = intent_mod.heartbeat_path_for_job(job_id, event_dir)
    hb.write_text("old", encoding="utf-8")
    stale = time.time() - 500
    os.utime(hb, (stale, stale))
    assert intent_mod.o3_subprocess_is_live(job_id, beat_id, event_dir) is False


def test_reconcile_closes_busy_pointer_orphan_post_beat_03_shape(tmp_path: Path) -> None:
    """Nav beat 4 class — sidecar still 'running' with pointer but dead subprocess."""
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    clips = event_dir / "kling_o3_clips"
    jobs.mkdir(parents=True)
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "f2db16c2"
    clip = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
    clip.write_bytes(b"mp4")
    log_path = jobs / f"{job_id}_{beat_id}.log"
    log_path.write_text(
        json.dumps({"phase": "starting", "beat_id": beat_id}) + "\n"
        + json.dumps({"phase": "o3_submit", "beat_id": beat_id, "generation_slot": "g4"}) + "\n",
        encoding="utf-8",
    )
    stale = time.time() - 1200
    os.utime(log_path, (stale, stale))
    intent = {
        "schema_version": 1,
        "job_id": job_id,
        "intent_id": "intent-busy",
        "beat_id": beat_id,
        "committed_at": "2026-06-19T16:27:28Z",
        "runtime": {"log_path": str(log_path)},
    }
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    (jobs / f"{job_id}_intent.json").write_text(json.dumps(intent), encoding="utf-8")
    beat_row = {
        **_sidecar_beat(beat_id, job_id),
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(clip),
    }
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_post": {"beats": [beat_row]},
                },
            },
        },
    }
    with patch("beat_generator._PROD_DIR", str(prod)):
        with patch("o3_generation_intent.o3_subprocess_is_live", return_value=False):
            closed = intent_mod.reconcile_stale_o3_intent_locks(sidecar, event_dir)
    assert closed == 1
    terminal = json.loads((jobs / f"{job_id}_terminal.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_post"]["beats"][0]
    assert beat.get("o3_current_job_id") in (None, "")
    assert beat.get("status") == "approved"


def test_finalize_o3_job_lost_attempt_persists_heal(tmp_path: Path, monkeypatch) -> None:
    import beat_generator as bg

    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "deadbeef"
    clip = event_dir / "kling_o3_clips" / f"{beat_id}_g3_element_o3_master_delivery.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"mp4")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_post": {
                        "beats": [{
                            **_sidecar_beat(beat_id, job_id),
                            "kling_o3_status": "approved",
                            "kling_o3_video_path": str(clip),
                        }],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    monkeypatch.setattr(bg, "read_sidecar", lambda: sidecar)
    persisted: list[dict] = []

    def _update(bid: str, fn):
        _, beat = bg.find_beat(sidecar, bid)
        fn(beat, sidecar)
        persisted.append(dict(beat))
        return True, sidecar

    monkeypatch.setattr(bg, "update_beat_locked", _update)
    terminal = intent_mod.finalize_o3_job_lost_attempt(
        job_id,
        beat_id,
        event_dir,
        persist_beat=True,
    )
    assert terminal["status"] == "failed"
    assert persisted
    assert persisted[0].get("o3_current_job_id") in (None, "")
