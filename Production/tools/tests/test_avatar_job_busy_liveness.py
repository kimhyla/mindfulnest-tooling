"""Avatar Pro long-poll must keep session GET job_busy true (heartbeat + pgrep markers)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import o3_generation_intent as intent_mod
import pytest
from o3_job_status_contract import beat_job_busy


def test_avatar_pipeline_marker_in_pgrep_list():
    assert "arlo_avatar_beat_pipeline" in intent_mod._O3_PIPELINE_PROCESS_MARKERS


def test_running_terminal_fresh_heartbeat_is_busy(tmp_path: Path):
    event_dir = tmp_path / "Production" / "Event_1"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event3b_full_beat_02"
    job_id = "avatarhb1"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    intent_mod.write_o3_job_pid(job_id, event_dir, os.getpid())
    intent_mod.touch_o3_job_heartbeat(job_id, event_dir)
    beat = {"beat_id": beat_id, "o3_current_job_id": job_id}
    assert beat_job_busy(beat, event_dir) is True


def test_running_terminal_stale_heartbeat_dead_pid_not_busy(tmp_path: Path):
    event_dir = tmp_path / "Production" / "Event_1"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event3b_full_beat_02"
    job_id = "avatarhb2"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    hb = intent_mod.heartbeat_path_for_job(job_id, event_dir)
    hb.write_text("stale", encoding="utf-8")
    stale = time.time() - 500
    os.utime(hb, (stale, stale))
    beat = {"beat_id": beat_id, "o3_current_job_id": job_id}
    assert beat_job_busy(beat, event_dir) is False


def test_avatar_intent_uses_post_body_prompt_not_stale_sidecar(tmp_path: Path):
    from o3_generation_intent import build_generation_intent

    sidecar_prompt = 'Continuity: stale sidecar only.\n\nLoral speaks: "Sidecar line"'
    body_prompt = (
        'She looks briefly surprised, and then speaks: "Hello?"\n\n'
        "Match @Image1 character appearance exactly."
    )
    char = tmp_path / "lorelai_char.png"
    char.write_bytes(b"\x89PNG\r\n")
    beat = {
        "beat_id": "bg_arc1_event3b_full_beat_02",
        "speaker": "Lorelai",
        "o3_generate_mode": "avatar_pro",
        "reference_image": {"abs_path": str(char)},
        "kling_o3_prompt": sidecar_prompt,
    }
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {"beats": [beat]},
                },
            },
        },
    }
    event_dir = tmp_path / "Production" / "Event_1"
    event_dir.mkdir(parents=True)
    (event_dir / "arlo_o3_jobs").mkdir(parents=True)
    intent = build_generation_intent(
        beat=beat,
        sidecar=sidecar,
        body={
            "kling_o3_prompt": body_prompt,
            "generation_mode": "avatar_pro",
            "reference_image": beat["reference_image"],
        },
        beat_id=beat["beat_id"],
        event_dir=event_dir,
        job_id="avt99999",
        attempt_id="attempt-body-prompt",
        log_path=event_dir / "arlo_o3_jobs" / "avt99999_beat.log",
        pipeline_script=tmp_path / "arlo_avatar_beat_pipeline.py",
        wavespeed_key=None,
    )
    prepared = intent["prompt"]["prepared_for_api"]
    assert prepared == body_prompt
    assert "stale sidecar only" not in prepared
    assert prepared == intent["prompt"]["verbatim"]


def test_avatar_intent_prepared_for_api_matches_verbatim_no_morph():
    from o3_generation_intent import build_generation_intent

    o3 = (
        'Continuity: Loral has just heard Oliver say: "Hi".\n\n'
        'She looks briefly surprised, and then speaks: "Hello?"\n\n'
        "Match @Image1 character appearance exactly."
    )
    char = Path("/tmp/lorelai_char_avatar_verbatim.png")
    beat = {
        "beat_id": "bg_arc1_event3b_full_beat_02",
        "speaker": "Lorelai",
        "o3_generate_mode": "avatar_pro",
        "reference_image": {"abs_path": str(char)},
        "kling_o3_prompt": o3,
    }
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_3b_full": {"beats": [beat]},
                },
            },
        },
    }
    event_dir = Path("/tmp/event1_avatar_intent_verbatim")
    event_dir.mkdir(exist_ok=True)
    (event_dir / "arlo_o3_jobs").mkdir(exist_ok=True)
    char.write_bytes(b"\x89PNG\r\n")
    intent = build_generation_intent(
        beat=beat,
        sidecar=sidecar,
        body={
            "kling_o3_prompt": o3,
            "generation_mode": "avatar_pro",
            "reference_image": beat["reference_image"],
        },
        beat_id=beat["beat_id"],
        event_dir=event_dir,
        job_id="avt12345",
        attempt_id="attempt-avatar-intent",
        log_path=event_dir / "arlo_o3_jobs" / "avt12345_beat.log",
        pipeline_script=Path("/tmp/arlo_avatar_beat_pipeline.py"),
        wavespeed_key=None,
    )
    assert intent["prompt"]["verbatim"] == o3
    assert intent["prompt"]["prepared_for_api"] == o3


def test_observe_skips_stale_running_close_when_read_only(tmp_path: Path, monkeypatch):
    import beat_generator as bg

    event_dir = tmp_path / "Production" / "Event_1"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event3b_full_beat_02"
    job_id = "readon01"
    intent_mod.write_running_terminal_at_submit(job_id, event_dir, beat_id=beat_id)
    sidecar = {"arcs": {"arc_1": {"segments": {"event_3b_full": {"beats": [{
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
    }]}}}}}
    monkeypatch.setattr(bg, "read_sidecar_for_poll_snapshot", lambda **kw: sidecar)
    monkeypatch.setattr(
        intent_mod,
        "o3_subprocess_is_live",
        lambda *a, **k: False,
    )
    closed = intent_mod.observe_and_close_stale_o3_attempt(
        job_id, beat_id, event_dir, close_stale_running=False,
    )
    assert closed is False
    terminal = intent_mod.load_intent_terminal(
        intent_mod.terminal_path_for_job(job_id, event_dir),
    )
    assert terminal and terminal.get("status") == intent_mod.INTENT_RUNNING_STATUS


def test_observe_skips_terminal_pointer_cleanup_when_read_only(tmp_path: Path, monkeypatch):
    import beat_generator as bg

    event_dir = tmp_path / "Production" / "Event_1"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event3b_full_beat_02"
    job_id = "readon02"
    intent_mod.write_intent_terminal(job_id, event_dir, {
        "status": "done",
        "beat_id": beat_id,
    })
    sidecar = {"arcs": {"arc_1": {"segments": {"event_3b_full": {"beats": [{
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
    }]}}}}}
    monkeypatch.setattr(bg, "read_sidecar_for_poll_snapshot", lambda **kw: sidecar)
    update_calls: list[str] = []
    monkeypatch.setattr(
        bg,
        "update_beat_locked",
        lambda bid, mut: update_calls.append(bid) or (True, {}),
    )
    closed = intent_mod.observe_and_close_stale_o3_attempt(
        job_id, beat_id, event_dir, close_stale_running=False,
    )
    assert closed is False
    assert update_calls == []
