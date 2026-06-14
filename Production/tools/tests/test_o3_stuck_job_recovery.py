"""Stuck O3 voice job reconciliation — regression for dead-process + stale errors."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg

TOOLS = Path(__file__).resolve().parent.parent


def _import_background():
    import importlib

    return importlib.import_module("server_handlers.background")


def test_reconcile_clears_stale_running_with_failed_voice_fix(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_07",
                                "status": "o3_voice_job_running",
                                "kling_o3_status": "approved",
                                "kling_o3_video_path": str(tmp_path / "delivery.mp4"),
                                "kling_o3_voice_fix_status": "failed",
                                "kling_o3_voice_fix_error": "AttributeError: module 'beat_generator' has no attribute 'update_beat_locked'",
                                "kling_o3_voice_fix_job_pid": 999999,
                                "kling_o3_voice_fix_ui_job_id": "deadjob1",
                            }
                        ],
                    },
                },
            },
        },
    }
    (tmp_path / "delivery.mp4").write_bytes(b"x")
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    assert changed == 1
    assert beat["status"] == "approved"
    assert beat.get("kling_o3_voice_fix_error") is None
    assert beat.get("kling_o3_voice_fix_ui_job_id") is None


def test_reconcile_clears_stale_pid_after_approved_element_pipeline(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_02_g5_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"fake mp4")
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_02",
                                "status": "approved",
                                "kling_o3_status": "approved",
                                "kling_o3_video_path": str(delivery),
                                "kling_o3_voice_fix_status": "approved",
                                "kling_o3_voice_fix_job_pid": 96015,
                                "kling_o3_voice_fix_ui_job_id": None,
                            }
                        ],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert changed == 1
    assert beat.get("kling_o3_voice_fix_job_pid") is None


def test_reconcile_recovers_done_element_log_after_dead_subprocess(monkeypatch, tmp_path) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_02_g5_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"fake mp4")
    log_path = tmp_path / "job.log"
    log_path.write_text(
        json.dumps({
            "phase": "starting",
            "route": "o3_element_native_voice",
            "beat_id": "bg_arc1_event2_pre_beat_02",
        })
        + "\n"
        + json.dumps({
            "phase": "done",
            "beat_id": "bg_arc1_event2_pre_beat_02",
            "video": str(delivery),
            "delivery": {"width": 1280, "height": 720},
        })
        + "\n",
        encoding="utf-8",
    )
    sidecar = {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_02",
                                "status": "o3_element_running",
                                "kling_o3_status": "submitted",
                                "kling_o3_voice_fix_status": "o3_running",
                                "kling_o3_voice_fix_job_pid": 424242,
                                "kling_o3_voice_fix_ui_job_id": "8cde7a99",
                                "kling_o3_voice_fix_job_log_path": str(log_path),
                            }
                        ],
                    },
                },
            },
        },
    }
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: False)
    changed = bg_mod.reconcile_stuck_o3_voice_beats(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert changed == 1
    assert beat["status"] == "approved"
    assert beat["kling_o3_status"] == "approved"
    assert beat["kling_o3_voice_fix_status"] == "approved"
    assert beat["kling_o3_video_path"] == str(delivery)
    assert beat.get("kling_o3_voice_fix_ui_job_id") is None


def test_parse_element_pipeline_done_log(tmp_path) -> None:
    bg_mod = _import_background()
    log_path = tmp_path / "run.log"
    log_path.write_text(
        '{"phase": "delivery_encode"}\n'
        + json.dumps({
            "phase": "done",
            "beat_id": "bg_arc1_event2_pre_beat_02",
            "video": "/tmp/out.mp4",
            "delivery": {"width": 1280, "height": 720},
        })
        + "\n",
        encoding="utf-8",
    )
    parsed = bg_mod._parse_o3_pipeline_result_from_log(log_path)
    assert parsed is not None
    assert parsed.get("ok") is True
    assert parsed.get("video") == "/tmp/out.mp4"


def test_session_state_handler_calls_reconcile() -> None:
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "reconcile_stuck_o3_voice_beats" in src
    assert "handle_bg_session_state" in src


def test_recover_o3_job_from_sidecar_matches_log_path_when_ui_job_id_cleared(
    monkeypatch, tmp_path,
) -> None:
    bg_mod = _import_background()
    delivery = tmp_path / "bg_arc1_event2_pre_beat_03_g4_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"fake mp4")
    log_path = tmp_path / "f9d7dc09_bg_arc1_event2_pre_beat_03.log"
    log_path.write_text(
        json.dumps({"phase": "done", "video": str(delivery), "beat_id": "bg_arc1_event2_pre_beat_03"})
        + "\n",
        encoding="utf-8",
    )
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_03",
                            "kling_o3_status": "approved",
                            "kling_o3_voice_fix_status": "approved",
                            "kling_o3_video_path": str(delivery),
                            "kling_o3_voice_fix_job_log_path": str(log_path),
                        }],
                    },
                },
            },
        },
    }

    class _FakeBg:
        @staticmethod
        def sidecar_file_lock():
            import contextlib
            return contextlib.nullcontext()

        @staticmethod
        def read_sidecar():
            return sidecar

        @staticmethod
        def _migrate_sidecar(data):
            return data

    monkeypatch.setattr(bg_mod, "_bg_module", lambda: _FakeBg())
    recovered = bg_mod._recover_o3_job_from_sidecar("f9d7dc09")
    assert recovered is not None
    assert recovered["status"] == "done"
    assert recovered["beat_id"] == "bg_arc1_event2_pre_beat_03"
    assert recovered.get("recovered") is True
