"""Blast-radius gates for active generation intent."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
from o3_generation_intent import beat_has_active_intent, write_generation_intent


def _sidecar_with_prompt(beat_id: str, prompt: str) -> dict:
    return {
        "schema_version": 1,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": beat_id,
                            "speaker": "Lorelai",
                            "kling_o3_prompt": prompt,
                            "dialogue_text": "x",
                        }],
                    },
                },
            },
        },
    }


def test_migrate_sidecar_skips_active_beat(tmp_path, monkeypatch):
    beat_id = "bg_arc1_event2_pre_beat_30"
    prompt = "Loral (female raccoon) speaks: \"Keep me\""
    sidecar = _sidecar_with_prompt(beat_id, prompt)
    event_dir = tmp_path / "Event_2"
    jobs = event_dir / "arlo_o3_jobs"
    jobs.mkdir(parents=True)
    write_generation_intent({
        "schema_version": 1,
        "job_id": "active01",
        "beat_id": beat_id,
        "committed_at": "2026-06-15T21:00:00Z",
        "prompt": {"verbatim": prompt},
    }, event_dir)
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(tmp_path / "beat_generator_state.json"))
    monkeypatch.setattr(bg, "_PROD_DIR", tmp_path)
    with patch("beat_generator.heal_o3_element_submit_prompt") as heal:
        heal.side_effect = lambda b: b.update({"kling_o3_prompt": "MORPHED"}) or True
        migrated = bg._migrate_sidecar(sidecar)
    beat = migrated["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["kling_o3_prompt"] == prompt
    assert beat_has_active_intent(beat_id, event_dir)


def test_highest_o3_generation_on_disk_scans_clips(tmp_path):
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    bid = "bg_arc1_event2_pre_beat_30"
    (clips / f"{bid}_g5_element_o3_master.mp4").write_bytes(b"x")
    (clips / f"{bid}_g7_element_o3_master_delivery.mp4").write_bytes(b"y")
    assert bg.highest_o3_generation_on_disk(bid, event_dir) == 7
