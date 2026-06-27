"""Failed O3 attempts must clear busy state and surface errors (all events/arcs)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import o3_generation_intent as intent_mod

TOOLS = Path(__file__).resolve().parent.parent


def _beat14_sidecar(*, lock_job: str, ui_job: str | None = None, error: str | None = None) -> dict:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_14",
        "speaker": "Tessa",
        "kling_o3_status": "approved",
        "kling_o3_voice_fix_status": "approved",
        "kling_o3_video_path": "/fake/g9_element_o3_master_delivery.mp4",
        "o3_active_intent_job_id": lock_job,
    }
    if ui_job:
        beat["kling_o3_voice_fix_ui_job_id"] = ui_job
    if error:
        beat["kling_o3_voice_fix_error"] = error
    return {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [beat]},
                },
            },
        },
    }


def test_reconcile_clears_lock_when_terminal_already_exists(tmp_path):
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_14"
    job_id = "2387dca8"
    fail_msg = "Audio 11.68s leaves only 0.00s lipsync tail"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": job_id,
            "beat_id": beat_id,
            "committed_at": "2026-06-18T12:00:00Z",
        }),
        encoding="utf-8",
    )
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({
            "status": "failed",
            "terminal_at": "2026-06-18T12:05:00Z",
            "failure": {"message": fail_msg},
        }),
        encoding="utf-8",
    )
    sidecar = _beat14_sidecar(lock_job=job_id, ui_job=job_id)
    with patch("beat_generator._PROD_DIR", str(prod)):
        closed = intent_mod.reconcile_stale_o3_intent_locks(sidecar, event_dir)
    assert closed == 1
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat.get("o3_active_intent_job_id") is None
    assert beat.get("kling_o3_voice_fix_ui_job_id") is None
    assert beat["kling_o3_voice_fix_error"] == fail_msg
    assert beat.get("kling_o3_last_attempt_failed_at") == "2026-06-18T12:05:00Z"


def test_reconcile_o3_terminal_attempt_fields_all_events(tmp_path):
    import importlib

    bg_mod = importlib.import_module("server_handlers.background")
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_09"
    job_id = "abc12def"
    fail_msg = "provider timeout"
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({
            "status": "failed",
            "terminal_at": "2026-06-19T01:00:00Z",
            "failure": {"message": fail_msg},
        }),
        encoding="utf-8",
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": beat_id,
                            "kling_o3_voice_fix_status": "approved",
                            "kling_o3_status": "approved",
                            "o3_active_intent_job_id": job_id,
                            "kling_o3_voice_fix_ui_job_id": job_id,
                        }],
                    },
                },
            },
        },
    }
    with patch("beat_generator._PROD_DIR", str(prod)):
        changed = bg_mod.reconcile_o3_terminal_attempt_fields_all_events(sidecar)
    assert changed == 1
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_voice_fix_error"] == fail_msg
    assert beat.get("o3_active_intent_job_id") is None
    assert beat.get("kling_o3_voice_fix_ui_job_id") is None


def test_session_state_read_only_no_legacy_terminal_heal_on_get():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "reconcile_o3_terminal_attempt_fields_all_events" not in block
    assert "_apply_o3_session_terminal_reconcile" in block


def test_ts_poll_map_stale_when_sidecar_has_error():
    src = (TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts").read_text(encoding="utf-8")
    assert "beatO3JobLooksRunning" in src
    assert "kling_o3_voice_fix_error" in src
    assert "beatO3JobBusy" in src
    nav = (TOOLS / "storyboard-v2" / "src" / "utils" / "bgBeatNavStatus.ts").read_text(encoding="utf-8")
    assert "Last attempt failed" in nav


def test_cancelled_terminal_does_not_block_active_intent(tmp_path):
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_23"
    job_id = "f5dce0a9"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": job_id,
            "beat_id": beat_id,
            "committed_at": "2026-06-19T04:55:18Z",
        }),
        encoding="utf-8",
    )
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({
            "status": "cancelled",
            "error": "Operator cancelled accidental generation.",
            "terminal_at": "2026-06-19T04:56:54Z",
        }),
        encoding="utf-8",
    )
    with patch("beat_generator._PROD_DIR", str(prod)):
        assert intent_mod.beat_has_active_intent(beat_id, event_dir) is False


def test_heal_aborted_attempt_restores_approved_clip(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"mp4")
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_23",
        "kling_o3_status": "approved",
        "kling_o3_video_path": str(video),
        "kling_o3_voice_fix_status": "failed",
        "kling_o3_task_id": "102bd39b3f4b4d608c8a4f1df085f896",
        "kling_o3_voice_fix_job_log_path": "/fake/f5dce0a9_bg_arc1_event2_pre_beat_23.log",
        "status": "approved",
    }
    assert intent_mod.heal_o3_beat_after_aborted_attempt(beat) is True
    assert beat["kling_o3_voice_fix_status"] == "approved"
    assert "kling_o3_task_id" not in beat
    assert "kling_o3_voice_fix_job_log_path" not in beat


def test_reconcile_stale_log_pointers_clears_cancelled_job(tmp_path):
    import importlib

    bg_mod = importlib.import_module("server_handlers.background")
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    clips = event_dir / "kling_o3_clips"
    jobs.mkdir(parents=True)
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_23"
    job_id = "f5dce0a9"
    video = clips / f"{beat_id}_g8_element_o3_master_delivery.mp4"
    video.write_bytes(b"mp4")
    log_path = jobs / f"{job_id}_{beat_id}.log"
    log_path.write_text('{"phase":"o3_poll"}\n', encoding="utf-8")
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({"status": "cancelled", "terminal_at": "2026-06-19T04:56:54Z"}),
        encoding="utf-8",
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": beat_id,
                            "kling_o3_status": "approved",
                            "kling_o3_video_path": str(video),
                            "kling_o3_voice_fix_status": "approved",
                            "kling_o3_voice_fix_job_log_path": str(log_path),
                        }],
                    },
                },
            },
        },
    }
    with patch("beat_generator._PROD_DIR", str(prod)):
        changed = bg_mod.reconcile_stale_o3_job_log_pointers_all_events(sidecar)
    assert changed == 1
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat.get("kling_o3_voice_fix_job_log_path") is None


def test_session_state_read_only_no_log_pointer_heal_on_get():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "reconcile_stale_o3_job_log_pointers_all_events" not in block


def test_session_state_read_only_no_pipeline_sync_on_get():
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "sync_o3_selection_pipeline_fields" not in block


def test_generate_submit_not_blocked_when_prompt_save_fails():
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    block = src.split("const onGenerateBatch = async", 1)[1].split("const onSubmitNativeLipSyncExperiment", 1)[0]
    assert "const saved = await onUpdateBeatText" in block
    assert "await submitO3Voice" in block
    assert "if (beatO3JobLooksRunning(latestBeat))" not in block
    assert "beatO3JobBusy(latestBeat" in block


def test_cancelled_intent_terminal_status_parity():
    from o3_job_status_contract import INTENT_TERMINAL_STATUSES

    src = (TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts").read_text(encoding="utf-8")
    assert "cancelled" in INTENT_TERMINAL_STATUSES
    assert "cancelled" in src


def test_ts_busy_ignores_stale_poll_map():
    nav = (TOOLS / "storyboard-v2" / "src" / "utils" / "bgBeatNavStatus.ts").read_text(encoding="utf-8")
    assert "beatO3JobBusy" in nav
    assert "Last attempt failed" in nav
    bg = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "resolveO3FailureBanner" in bg
    assert "beatO3JobBusy(beat" in bg
    assert "o3-attempt-fail:" in bg
    assert "INTENT_JOB_ACTIVE" in bg


def test_ts_f2_thin_busy_contract():
    src = (TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts").read_text(encoding="utf-8")
    assert "pruneO3SubmitPending" in src
    assert "pruneSubmitPollLatch" in src
    assert "beatO3PollMapIsStale" not in src
    assert "pruneStaleO3ClientStateFromBeats" not in src


def test_ts_refresh_uses_server_poll_map():
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "activeO3PollJobsFromBeats" in src
    assert "pruneO3SubmitPending" in src
    assert "visibilitychange" in src
    assert "syncAfterWake" in src


def test_ts_wake_refresh_clears_overnight_stuck_generating():
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "background tabs throttle O3 poll timers" in src
    assert "document.visibilityState === 'visible'" in src


def test_terminal_reconcile_clears_done_log_path(tmp_path):
    import importlib

    bg_mod = importlib.import_module("server_handlers.background")
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_14"
    job_id = "6d2bba01"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({"schema_version": 1, "job_id": job_id, "beat_id": beat_id}),
        encoding="utf-8",
    )
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({"status": "done", "terminal_at": "2026-06-19T05:20:00Z"}),
        encoding="utf-8",
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": beat_id,
                            "kling_o3_status": "approved",
                            "kling_o3_voice_fix_status": "approved",
                            "kling_o3_voice_fix_job_log_path": f"/fake/{job_id}_{beat_id}.log",
                        }],
                    },
                },
            },
        },
    }
    with patch("beat_generator._PROD_DIR", str(prod)):
        changed = bg_mod.reconcile_o3_terminal_attempt_fields_all_events(sidecar)
    assert changed == 1
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert "kling_o3_voice_fix_job_log_path" not in beat
