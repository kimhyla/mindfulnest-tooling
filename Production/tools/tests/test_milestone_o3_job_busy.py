"""Milestone O3 job_busy — event3b beat ids must not fall back to Event_1 for job lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

TOOLS = Path(__file__).resolve().parents[1]


@pytest.fixture
def prod_tree(tmp_path: Path):
    prod = tmp_path / "Production"
    event1 = prod / "Event_1"
    event2 = prod / "Event_2"
    milestone_dir = prod / "Milestones" / "milestone1_arc1"
    for p in (event1, event2, milestone_dir):
        p.mkdir(parents=True)
    jobs2 = event2 / "arlo_o3_jobs"
    jobs2.mkdir(parents=True)
    beat_id = "bg_arc1_event3b_full_beat_02"
    job_id = "abc12345"
    (jobs2 / f"{job_id}_intent.json").write_text(
        json.dumps({"schema_version": 1, "job_id": job_id, "beat_id": beat_id}),
        encoding="utf-8",
    )
    (jobs2 / f"{job_id}_terminal.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job_id": job_id,
                "beat_id": beat_id,
                "status": "running",
                "phase_last": "submit",
            }
        ),
        encoding="utf-8",
    )
    (jobs2 / f"{job_id}.heartbeat").write_text("2026-06-25T12:00:00+00:00", encoding="utf-8")
    return prod, event1, event2, milestone_dir, beat_id, job_id


def test_event3b_beat_id_does_not_map_to_event1(prod_tree, monkeypatch):
    prod, event1, event2, _m, beat_id, _job = prod_tree
    import beat_generator as bg
    from beatgen_scope import BeatGenScopeError

    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    with pytest.raises(BeatGenScopeError):
        bg.event_dir_for_beat_id(beat_id)


def test_resolve_o3_job_event_dir_milestone_uses_library(prod_tree):
    prod, event1, event2, _m, beat_id, _job = prod_tree
    from o3_generation_intent import resolve_o3_job_event_dir

    assert resolve_o3_job_event_dir(
        beat_id,
        server_event_dir=event2,
        library_event_dir=event1,
        scope_type="milestone",
    ) == event1


def test_resolve_o3_job_event_dir_candidates_includes_server_fallback(prod_tree):
    prod, event1, event2, _m, beat_id, _job = prod_tree
    from o3_generation_intent import resolve_o3_job_event_dir_candidates

    dirs = resolve_o3_job_event_dir_candidates(
        beat_id,
        server_event_dir=event2,
        library_event_dir=event1,
        scope_type="milestone",
    )
    assert dirs[0] == event1
    assert event2 in dirs


def test_beat_job_busy_finds_running_terminal_on_server_pin(prod_tree, monkeypatch):
    prod, event1, event2, _m, beat_id, job_id = prod_tree
    import beat_generator as bg
    from o3_generation_intent import resolve_o3_job_event_dir_candidates
    from o3_job_status_contract import beat_job_busy_in_event_dirs

    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    beat = {
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_ui_job_id": job_id,
    }
    dirs = resolve_o3_job_event_dir_candidates(
        beat_id,
        server_event_dir=event2,
        library_event_dir=event1,
        scope_type="milestone",
    )
    assert beat_job_busy_in_event_dirs(beat, dirs, in_memory_jobs={}) is True


def test_enrich_beats_job_busy_milestone_event3b(prod_tree, monkeypatch):
    prod, event1, event2, milestone_dir, beat_id, job_id = prod_tree
    import beat_generator as bg
    from server_handlers import background as bg_handlers

    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    monkeypatch.setattr(
        bg,
        "read_sidecar_for_poll_snapshot",
        lambda **_: {"segments": []},
    )

    app = SimpleNamespace(
        event_dir=event2,
        scope_type="milestone",
        milestone_library_event_dir=event1,
        milestone_dir=milestone_dir,
    )
    h = MagicMock(app=app)
    monkeypatch.setattr(bg_handlers, "_data_root", lambda _h: prod)

    beat = {
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
        "kling_o3_voice_fix_ui_job_id": job_id,
        "pipeline": "kling_o3_omni",
    }
    beats = [beat]
    bg_handlers._enrich_beats_job_busy(beats, prod, h, session_read_only=True)
    assert beats[0]["job_busy"] is True
    assert beats[0]["o3_current_job_id"] == job_id


def test_wrong_event_dir_for_beat_id_alone_would_miss_running_job(prod_tree, monkeypatch):
    prod, event1, event2, _m, beat_id, job_id = prod_tree
    import beat_generator as bg
    from o3_job_status_contract import beat_job_busy

    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    beat = {
        "beat_id": beat_id,
        "o3_current_job_id": job_id,
    }
    assert beat_job_busy(beat, event1, in_memory_jobs={}) is False
