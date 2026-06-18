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
    src = (TOOLS / "storyboard-v2" / "src" / "o3JobStatusContract.ts").read_text(encoding="utf-8")
    assert "voiceFix.startsWith('failed')" in src


def test_voice_fix_terminal_failure_contract() -> None:
    from o3_job_status_contract import voice_fix_is_terminal_failure

    assert voice_fix_is_terminal_failure("failed_provider_fetch")
    assert voice_fix_is_terminal_failure("failed_provider_sub720")
    assert voice_fix_is_terminal_failure("failed_o3")
    assert not voice_fix_is_terminal_failure("approved")
    assert not voice_fix_is_terminal_failure("job_running")


def test_bg_failure_banner_visible_when_old_clip_kept() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "resolveVoiceFirstFailureBanner" in src
    idx = src.find("const o3FailureMessage")
    assert idx >= 0
    snippet = src[idx : idx + 220]
    assert "resolveVoiceFirstFailureBanner(beat" in snippet
    assert "kling_o3_status !== 'approved'" not in snippet


def test_bg_stale_failure_does_not_toast_on_session_load() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "seedGenFailureSeenKeys" in src
    assert "no error toast on hard refresh" in src
    load_block = src.split("const initialBeats = applyPromptEditsToBeats", 1)[1][:500]
    assert "seedGenFailureSeenKeys(initialBeats" in load_block
    assert "notifyNewGenFailures(initialBeats" not in load_block


def test_finalize_respects_sidecar_failed_provider_fetch(monkeypatch, tmp_path) -> None:
    import importlib

    bg_mod = importlib.import_module("server_handlers.background")
    beat_id = "bg_arc1_event2_pre_beat_01"
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": beat_id,
                            "kling_o3_status": "approved",
                            "kling_o3_voice_fix_status": "failed_provider_fetch",
                            "kling_o3_voice_fix_error": "unsafe url: non-public host",
                        }],
                    },
                },
            },
        },
    }

    class _FakeBg:
        @staticmethod
        def sidecar_file_lock(timeout_s=30):
            import contextlib
            return contextlib.nullcontext()

        @staticmethod
        def read_sidecar():
            return sidecar

        @staticmethod
        def _migrate_sidecar(data):
            return data

        @staticmethod
        def find_beat(data, bid):
            for beat in data["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]:
                if beat["beat_id"] == bid:
                    return "event_2_pre", beat
            return None, None

    class _Proc:
        def poll(self):
            return 1

    monkeypatch.setattr(bg_mod, "_bg_module", lambda: _FakeBg())
    job = {
        "status": "running",
        "beat_id": beat_id,
        "proc": _Proc(),
        "log_path": str(tmp_path / "job.log"),
    }
    (tmp_path / "job.log").write_text("Traceback non-public host\n", encoding="utf-8")
    bg_mod._finalize_o3_job_after_subprocess_exit(job, tmp_path / "Event_2")
    assert job["status"] == "failed"
    assert "non-public" in job["error"].lower() or "localhost" in job["error"].lower()


def test_o3_poll_returns_enriched_beat_snapshot_on_terminal() -> None:
    src = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "_enriched_beat_snapshot_for_o3_poll" in src
    assert "_o3_poll_payload_with_beat_snapshot" in src
    assert 'out["beat"] = snap' in src


def test_o3_poll_ui_patches_single_beat_without_full_refresh() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx").read_text(encoding="utf-8")
    assert "mergeBeatFromO3Poll" in src
    assert "O3_POLL_INTERVAL_MS" in src
    assert "res.data.beat" in src
