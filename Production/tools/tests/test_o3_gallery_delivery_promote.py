"""O3 gallery — delivery finalize promotes video_path; pin-slot replaces one container only."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg


def test_promote_o3_video_path_active_over_stale_selected_key() -> None:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_28",
        "pipeline": "kling_o3_omni",
        "kling_o3_video_path": "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_28_g12_element_o3_master_delivery.mp4",
        "kling_o3_selected_option_key": "g9key",
        "kling_o3_options": [
            {
                "key": "g9key",
                "video_path": "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_28_g9_element_o3_master_delivery.mp4",
                "slot_index": 1,
                "active": True,
                "source": "kling_o3_element_native_voice",
                "generation": 9,
            },
            {
                "key": "g12key",
                "video_path": "/Event_2/kling_o3_clips/bg_arc1_event2_pre_beat_28_g12_element_o3_master_delivery.mp4",
                "slot_index": 2,
                "active": False,
                "source": "kling_o3_element_native_voice",
                "generation": 12,
            },
        ],
    }
    bg.stamp_o3_delivery_pipeline_coherence(
        beat,
        {},
        generation_mode=bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert beat["kling_o3_selected_option_key"] == "g12key"
    g12 = next(
        o for o in beat["kling_o3_options"]
        if o["video_path"].endswith("g12_element_o3_master_delivery.mp4")
    )
    g9 = next(
        o for o in beat["kling_o3_options"]
        if o["video_path"].endswith("g9_element_o3_master_delivery.mp4")
    )
    assert g12["active"] is True
    assert g9["active"] is False


def test_assign_replaces_only_target_slot_leaves_others(tmp_path: Path) -> None:
    p0 = tmp_path / "g8_element_o3_master_delivery.mp4"
    p9 = tmp_path / "g9_element_o3_master_delivery.mp4"
    p12 = tmp_path / "g12_element_o3_master_delivery.mp4"
    p13 = tmp_path / "g13_element_o3_master_delivery.mp4"
    for p in (p0, p9, p12, p13):
        p.write_bytes(b"v")
    beat = {
        "beat_id": "bg_test",
        "kling_o3_replace_slot_index": 2,
        "kling_o3_options": [
            {"key": "g8", "video_path": str(p0), "slot_index": 0, "active": False},
            {"key": "g9", "video_path": str(p9), "slot_index": 1, "active": True},
            {"key": "g12", "video_path": str(p12), "slot_index": 2, "active": False},
        ],
    }
    bg.assign_kling_o3_option_to_slot(
        beat,
        2,
        video_path=str(p13),
        label="g13",
        source="kling_o3_element_native_voice",
        now="2026-06-19T00:00:00Z",
        make_active=True,
    )
    slots = bg.build_fixed_o3_ui_slots(beat)
    assert slots[0] is not None and slots[0]["video_path"] == str(p0)
    assert slots[1] is not None and slots[1]["video_path"] == str(p9)
    assert slots[2] is not None and slots[2]["video_path"] == str(p13)
    displaced = next(o for o in beat["kling_o3_options"] if o["video_path"] == str(p12))
    assert "slot_index" not in displaced
    assert beat["kling_o3_replace_slot_index"] == 2


def test_replace_slot_index_unchanged_on_assign() -> None:
    beat = {
        "beat_id": "bg_test",
        "kling_o3_replace_slot_index": 0,
        "kling_o3_options": [],
    }
    bg.assign_kling_o3_option_to_slot(
        beat,
        0,
        video_path="/tmp/g1_element_o3_master_delivery.mp4",
        label="g1",
        source="test",
        now="now",
        make_active=True,
    )
    assert beat["kling_o3_replace_slot_index"] == 0
