"""Orphan O3 intent locks — reconcile across all Event_* dirs and beat-scoped lookup."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import o3_generation_intent as intent_mod


def _sidecar_with_beat(beat_id: str, *, running: bool = False) -> dict:
    beat = {
        "beat_id": beat_id,
        "speaker": "Tessa",
        "kling_o3_voice_fix_status": "o3_running" if running else "approved",
    }
    return {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {"beats": [beat]},
                },
            },
        },
    }


def test_intent_event_dir_uses_beat_id_not_wrong_server_scope(tmp_path):
    prod = tmp_path / "Production"
    event1 = prod / "Event_1"
    event2 = prod / "Event_2"
    event1.mkdir(parents=True)
    event2.mkdir(parents=True)
    beat_id = "bg_arc1_event1_pre_beat_03"
    with patch("beat_generator._PROD_DIR", str(prod)):
        resolved = intent_mod.intent_event_dir_for_beat(beat_id, event2)
    assert resolved == event1


def test_reconcile_closes_orphan_intent_without_terminal(tmp_path):
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_14"
    job_id = "deadbeef"
    intent = {
        "schema_version": 1,
        "job_id": job_id,
        "intent_id": "intent-1",
        "beat_id": beat_id,
        "committed_at": "2026-06-16T20:00:00Z",
        "runtime": {"log_path": str(jobs / f"{job_id}_{beat_id}.log")},
    }
    (jobs / f"{job_id}_intent.json").write_text(json.dumps(intent), encoding="utf-8")
    (jobs / f"{job_id}_{beat_id}.log").write_text(
        '{"phase": "o3_submit", "beat_id": "%s"}\n' % beat_id,
        encoding="utf-8",
    )
    sidecar = _sidecar_with_beat(beat_id)
    with patch("beat_generator._PROD_DIR", str(prod)):
        assert intent_mod.beat_has_active_intent(beat_id, event_dir) is True
        closed = intent_mod.reconcile_stale_o3_intent_locks_all_events(sidecar, prod)
    assert closed == 1
    terminal = jobs / f"{job_id}_terminal.json"
    assert terminal.is_file()
    assert json.loads(terminal.read_text(encoding="utf-8"))["status"] == "failed"
    assert intent_mod.beat_has_active_intent(beat_id, event_dir) is False


def test_reconcile_all_events_scans_every_event_dir(tmp_path):
    prod = tmp_path / "Production"
    for event_name, beat_id in (
        ("Event_1", "bg_arc1_event1_pre_beat_01"),
        ("Event_2", "bg_arc1_event2_pre_beat_14"),
    ):
        jobs = prod / event_name / "arlo_o3_jobs"
        jobs.mkdir(parents=True)
        job_id = f"job_{event_name[-1]}"
        intent = {
            "schema_version": 1,
            "job_id": job_id,
            "intent_id": f"intent-{event_name}",
            "beat_id": beat_id,
            "committed_at": "2026-06-16T20:00:00Z",
        }
        (jobs / f"{job_id}_intent.json").write_text(json.dumps(intent), encoding="utf-8")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {"beats": [{"beat_id": "bg_arc1_event1_pre_beat_01"}]},
                    "event_2_pre": {"beats": [{"beat_id": "bg_arc1_event2_pre_beat_14"}]},
                },
            },
        },
    }
    with patch("beat_generator._PROD_DIR", str(prod)):
        closed = intent_mod.reconcile_stale_o3_intent_locks_all_events(sidecar, prod)
    assert closed == 2


def test_reconcile_writes_done_terminal_when_log_has_done(tmp_path):
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_14"
    job_id = "abc12345"
    video = event_dir / "kling_o3_clips" / f"{beat_id}_g3_delivery.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"mp4")
    log_path = jobs / f"{job_id}_{beat_id}.log"
    log_path.write_text(
        json.dumps({
            "phase": "done",
            "beat_id": beat_id,
            "video": str(video),
        }) + "\n",
        encoding="utf-8",
    )
    intent = {
        "schema_version": 1,
        "job_id": job_id,
        "intent_id": "intent-done",
        "beat_id": beat_id,
        "committed_at": "2026-06-16T18:00:00Z",
        "runtime": {"log_path": str(log_path)},
    }
    (jobs / f"{job_id}_intent.json").write_text(json.dumps(intent), encoding="utf-8")
    sidecar = _sidecar_with_beat(beat_id)
    with patch("beat_generator._PROD_DIR", str(prod)):
        closed = intent_mod.reconcile_stale_o3_intent_locks(sidecar, event_dir)
    assert closed == 1
    terminal = json.loads((jobs / f"{job_id}_terminal.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "done"
    assert intent_mod.beat_has_active_intent(beat_id, event_dir) is False


def test_reconcile_skips_when_subprocess_still_running(tmp_path):
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_14"
    job_id = "running1"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": job_id,
            "beat_id": beat_id,
            "committed_at": "2026-06-16T20:00:00Z",
        }),
        encoding="utf-8",
    )
    sidecar = _sidecar_with_beat(beat_id, running=True)
    with patch("beat_generator._PROD_DIR", str(prod)):
        closed = intent_mod.reconcile_stale_o3_intent_locks_all_events(sidecar, prod)
    assert closed == 0
    assert intent_mod.beat_has_active_intent(beat_id, event_dir) is True


def test_session_state_handler_reconciles_all_events():
    src = (
        Path(__file__).resolve().parent.parent
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
    assert "reconcile_stale_o3_intent_locks_all_events" in block
