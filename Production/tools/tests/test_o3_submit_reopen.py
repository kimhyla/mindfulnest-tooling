"""Category H — job_busy false must not block submit with INTENT_JOB_ACTIVE."""
from __future__ import annotations

import json
from pathlib import Path

import o3_generation_intent as intent_mod
import pytest


def test_build_generation_intent_allows_submit_when_terminal_failed(tmp_path: Path, monkeypatch) -> None:
    prod = tmp_path / "Production"
    event_dir = prod / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    beat_id = "bg_arc1_event2_post_beat_03"
    job_id = "deadjob1"
    (jobs / f"{job_id}_intent.json").write_text(
        json.dumps({
            "schema_version": 1,
            "job_id": job_id,
            "intent_id": "i1",
            "beat_id": beat_id,
            "committed_at": "2020-01-01T00:00:00Z",
        }),
        encoding="utf-8",
    )
    intent_mod.write_intent_terminal(job_id, event_dir, {
        "status": "failed",
        "failure": {"message": "prior fail"},
    })
    beat = {
        "beat_id": beat_id,
        "speaker": "Lorelai",
        "kling_o3_prompt": "@Image1 test prompt here",
        "reference_image": {"abs_path": str(tmp_path / "c.png")},
        "bg_ref_image": {"abs_path": str(tmp_path / "b.png")},
        "o3_generate_mode": "element_native",
    }
    (tmp_path / "c.png").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    sidecar = {"beats": [beat], "active_context": {"event_id": "Event_2", "phase": "post"}}
    monkeypatch.setattr("beat_generator.event_dir_for_beat_id", lambda _b: event_dir)
    monkeypatch.setattr("beat_generator.normalize_bg_event_id", lambda x: "Event_2")
    monkeypatch.setattr("beat_generator.segment_event_phase_for_beat", lambda _s, _b: ("Event_2", "post"))
    monkeypatch.setattr("beat_generator.resolve_beat_generation_mode", lambda _b, _s: "element_native")
    monkeypatch.setattr(
        "beat_generator.validate_o3_submit_prompt_for_mode",
        lambda _p, _m: (True, "", ""),
    )
    monkeypatch.setattr("tools.kling_character_registry.is_speaker_voice_ready", lambda _s: True)
    monkeypatch.setattr(
        "operator_workbench_contract.materialize_o3_submit_refs",
        lambda body, b, **_: (b["reference_image"], b["bg_ref_image"]),
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.char_ref_matches_element_images",
        lambda *_a, **_k: (True, ""),
    )
    monkeypatch.setattr("o3_job_status_contract.beat_job_busy", lambda *_a, **_k: False)
    body = {"kling_o3_prompt": beat["kling_o3_prompt"]}
    intent = intent_mod.build_generation_intent(
        beat=beat,
        sidecar=sidecar,
        body=body,
        beat_id=beat_id,
        event_dir=event_dir,
        job_id="newjob01",
        attempt_id="att1",
        log_path=jobs / "newjob01_x.log",
        pipeline_script=Path("pipeline.py"),
        wavespeed_key="k",
    )
    assert intent["job_id"] == "newjob01"
