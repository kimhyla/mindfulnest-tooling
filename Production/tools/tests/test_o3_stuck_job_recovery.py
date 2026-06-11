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


def test_session_state_handler_calls_reconcile() -> None:
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "reconcile_stuck_o3_voice_beats" in src
    assert "handle_bg_session_state" in src
