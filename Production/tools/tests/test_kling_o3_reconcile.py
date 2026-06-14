"""Kling O3 reconcile must not drop on-disk approved clips after failed redo."""
from __future__ import annotations

import beat_generator as bg


def test_gen_from_element_delivery_path():
    path = (
        "/tmp/bg_arc1_event2_pre_beat_24_g4_element_o3_master_delivery.mp4"
    )
    assert bg._kling_o3_gen_from_video_path(path) == 4


def test_reconcile_keeps_approved_clip_when_generation_ran_ahead(tmp_path):
    clip = tmp_path / "bg_test_beat_g3_element_o3_master_delivery.mp4"
    clip.write_bytes(b"fake")
    beat = {
        "beat_id": "bg_test_beat",
        "status": "approved",
        "kling_o3_status": "approved",
        "kling_o3_generation": 5,
        "kling_o3_video_path": str(clip),
    }
    changed = bg.reconcile_kling_o3_beat(beat, tmp_path)
    assert changed is True
    assert beat["kling_o3_video_path"] == str(clip.resolve())
    assert beat["kling_o3_generation"] == 3
    assert beat["kling_o3_status"] == "approved"


def test_reconcile_clears_only_missing_paths(tmp_path):
    beat = {
        "beat_id": "bg_test_beat",
        "status": "video_ready",
        "kling_o3_status": "completed",
        "kling_o3_generation": 4,
        "kling_o3_video_path": str(tmp_path / "missing_g3_element_o3_master_delivery.mp4"),
    }
    changed = bg.reconcile_kling_o3_beat(beat, tmp_path)
    assert changed is True
    assert "kling_o3_video_path" not in beat


def test_enrich_marks_video_path_exists(tmp_path):
    clip = tmp_path / "bg_test_beat_g1_element_o3_master_delivery.mp4"
    clip.write_bytes(b"fake")
    beat = {
        "beat_id": "bg_test_beat",
        "kling_o3_video_path": str(clip),
        "kling_o3_options": [
            {"video_path": str(clip), "key": "k1"},
            {"video_path": str(tmp_path / "gone.mp4"), "key": "k2"},
        ],
    }
    out = bg.enrich_beat_kling_o3_pinned(beat, tmp_path)
    assert out["kling_o3_video_path_exists"] is True
    assert out["kling_o3_options"][0]["video_path_exists"] is True
    assert out["kling_o3_options"][1]["video_path_exists"] is False
