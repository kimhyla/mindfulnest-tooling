"""W1 — checkpoint-before-done: terminal done must imply delivery in kling_o3_options."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg
import pytest


def test_checkpoint_before_done_writes_option_to_kling_o3_options(
    monkeypatch, tmp_path: Path,
) -> None:
    """Golden: encode checkpoint lands delivery row before finalize terminal."""
    beat_id = "bg_arc1_event2_pre_beat_27"
    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps({
            "schema_version": 1,
            "arcs": {
                "arc_1": {
                    "segments": {
                        "event_2_pre": {
                            "beats": [{
                                "beat_id": beat_id,
                                "speaker": "Lorelai",
                                "kling_o3_voice_fix_attempt_id": "attempt-1",
                                "kling_o3_options": [None, None, None],
                            }],
                        },
                    },
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    delivery = tmp_path / f"{beat_id}_g10_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"mp4")

    bg.persist_o3_delivery_option_checkpoint(
        beat_id,
        video_path=str(delivery),
        slot_index=0,
        label="g10 O3 Element voice",
        o3_voice_binding={"element_id": "e1", "kling_voice_id": "v1"},
        attempt_id="attempt-1",
        generation=10,
    )

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    paths = {
        str(o.get("video_path") or "")
        for o in (beat.get("kling_o3_options") or [])
        if isinstance(o, dict)
    }
    assert str(delivery) in paths
    assert beat.get("kling_o3_video_path") == str(delivery)


def test_terminal_done_on_disk_implies_gallery_or_checkpoint(
    tmp_path: Path, monkeypatch,
) -> None:
    """When terminal is done and delivery exists on disk, reconcile imports into options."""
    event_dir = tmp_path / "Event_2"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    beat_id = "bg_arc1_event2_pre_beat_04"
    delivery = clips / f"{beat_id}_g3_element_o3_master_delivery.mp4"
    delivery.write_bytes(b"v")
    beat = {
        "beat_id": beat_id,
        "speaker": "Tessa",
        "pipeline": "kling_o3_omni",
        "kling_o3_options": [],
    }
    changed = bg.reconcile_o3_disk_deliveries_for_beat(beat, event_dir)
    assert changed is True
    paths = {o.get("video_path") for o in beat["kling_o3_options"]}
    assert str(delivery.resolve()) in paths


def test_element_pipeline_source_has_checkpoint_before_success_terminal():
    src = (
        Path(__file__).resolve().parent.parent
        / "kling_o3_element_beat_pipeline.py"
    ).read_text(encoding="utf-8")
    block = src.split("def run_pipeline_from_intent", 1)[1].split("\ndef ", 1)[0]
    assert "persist_o3_delivery_option_checkpoint" in block
    assert block.index("persist_o3_delivery_option_checkpoint") < block.index("terminal_body = {")
