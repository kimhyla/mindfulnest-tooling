"""Regression gates for O3 voice job state durability."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg

TOOLS = Path(__file__).resolve().parent.parent


def _state() -> dict:
    return {
        "schema_version": 1,
        "active_context": None,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "beat_a",
                                "dialogue_text": "A",
                                "kling_o3_voice_fix_attempt_id": "attempt-a",
                                "kling_o3_voice_fix_status": "job_running",
                            },
                            {
                                "beat_id": "beat_b",
                                "dialogue_text": "B",
                                "kling_o3_voice_fix_attempt_id": "attempt-b",
                                "kling_o3_voice_fix_status": "job_running",
                            },
                        ],
                    },
                },
            },
        },
    }


def test_update_beat_locked_patches_only_target_beat(monkeypatch, tmp_path) -> None:
    sidecar = tmp_path / "beat_generator_state.json"
    sidecar.write_text(json.dumps(_state()), encoding="utf-8")
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar))

    ok, _beat = bg.update_beat_locked(
        "beat_a",
        lambda beat, _sidecar: beat.update({"kling_o3_voice_fix_status": "approved"}),
        expected_attempt_id="attempt-a",
    )

    assert ok is True
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    beats = data["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"]
    assert beats[0]["kling_o3_voice_fix_status"] == "approved"
    assert beats[1]["kling_o3_voice_fix_status"] == "job_running"


def test_update_beat_locked_rejects_stale_attempt(monkeypatch, tmp_path) -> None:
    sidecar = tmp_path / "beat_generator_state.json"
    sidecar.write_text(json.dumps(_state()), encoding="utf-8")
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar))

    ok, _beat = bg.update_beat_locked(
        "beat_a",
        lambda beat, _sidecar: beat.update({"kling_o3_voice_fix_status": "approved"}),
        expected_attempt_id="older-attempt",
    )

    assert ok is False
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    beat = data["arcs"]["arc_1"]["segments"]["event_1_pre"]["beats"][0]
    assert beat["kling_o3_voice_fix_status"] == "job_running"


def test_arlo_pipeline_uses_locked_beat_updates_not_whole_file_writes() -> None:
    src = (TOOLS / "arlo_o3_voice_pipeline.py").read_text(encoding="utf-8")
    assert "bg_sidecar.update_beat_locked" in src
    assert "sidecar.write_text" not in src
    assert "sidecar_state" not in src


def test_background_duplicate_guard_and_terminal_statuses_are_explicit() -> None:
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "deduped" in src
    assert "kling_o3_voice_fix_attempt_id" in src
    assert "STALE_JOB_PROCESS_GONE" in src
    assert "failed_provider_sub720" in src
    assert "failed_provider_fetch" in src


def test_ui_treats_failed_prefixes_as_terminal() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "voiceFix.startsWith('failed')" in src
    assert "(beat.kling_o3_voice_fix_status ?? '').startsWith('failed')" in src
