"""Early O3 submit reattach — busy beat returns 200 deduped, not BEAT_JOB_BUSY 409."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _import_background():
    import importlib
    return importlib.import_module("server_handlers.background")


def test_o3_submit_reattach_helper_exists():
    bg_mod = _import_background()
    assert hasattr(bg_mod, "_o3_submit_reattach_response_if_running")


def test_o3_submit_reattach_before_intent_build_in_handler():
    src = (
        Path(__file__).resolve().parent.parent
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("def handle_bg_submit_arlo_o3_voice", 1)[1].split("\ndef ", 1)[0]
    assert "_o3_submit_reattach_response_if_running" in block
    assert block.index("_o3_submit_reattach_response_if_running(") < block.index(
        "committed_intent = build_generation_intent",
    )


def test_o3_submit_reattach_on_busy_beat(tmp_path, monkeypatch):
    bg_mod = _import_background()
    prod = tmp_path / "Production"
    event_dir = prod / "Event_3"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event3_pre_beat_03"
    job_id = "abc12345"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": job_id,
            "intent_id": "intent1",
            "beat_id": beat_id,
            "generation": {"slot": "g1", "slot_index": 1},
            "prompt": {"verbatim": "test", "sha256": "abc"},
        }),
        encoding="utf-8",
    )
    (jobs / f"{job_id}_terminal.json").write_text(
        json.dumps({"status": "running", "job_id": job_id, "beat_id": beat_id}),
        encoding="utf-8",
    )
    beat = {
        "beat_id": beat_id,
        "job_busy": True,
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_ui_job_id": job_id,
        "kling_o3_voice_fix_status": "o3_running",
        "kling_o3_voice_fix_job_pid": 4242,
        "kling_o3_voice_fix_job_log_path": str(jobs / f"{job_id}_{beat_id}.log"),
    }
    sent: list[dict] = []

    class Handler:
        def _send_json(self, _status, payload):
            sent.append(payload)

    monkeypatch.setattr(bg_mod, "_ARLO_O3_JOBS", {})
    monkeypatch.setattr(bg_mod, "_pid_is_running", lambda _pid: True)
    monkeypatch.setattr(
        "o3_job_status_contract.beat_job_busy",
        lambda *_a, **_k: True,
    )
    ok = bg_mod._o3_submit_reattach_response_if_running(
        Handler(), beat_id, beat, event_dir,
    )
    assert ok is True
    assert len(sent) == 1
    assert sent[0]["ok"] is True
    assert sent[0]["deduped"] is True
    assert sent[0]["job_id"] == job_id


def test_intent_commit_busy_falls_back_to_reattach():
    src = (
        Path(__file__).resolve().parent.parent
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    block = src.split("except IntentCommitError as exc:", 1)[1].split("\n    except Exception", 1)[0]
    assert 'exc.error_code == "BEAT_JOB_BUSY"' in block
    assert "_o3_submit_reattach_response_if_running" in block
