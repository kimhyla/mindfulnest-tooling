"""Beat Gen O3 replace-slot assignment — fixed 3-container model."""

from __future__ import annotations

import beat_generator as bg


def test_assign_replaces_chosen_slot_without_shifting_others() -> None:
    beat = {
        "beat_id": "bg_arc1_event1_pre_beat_07",
        "kling_o3_video_path": "/tmp/a.mp4",
        "kling_o3_options": [
            {"key": "a", "video_path": "/tmp/a.mp4", "slot_index": 0, "active": True},
            {"key": "b", "video_path": "/tmp/b.mp4", "slot_index": 1, "active": False},
            {"key": "c", "video_path": "/tmp/c.mp4", "slot_index": 2, "active": False},
        ],
        "kling_o3_replace_slot_index": 1,
    }
    bg.assign_kling_o3_option_to_slot(
        beat,
        1,
        video_path="/tmp/new.mp4",
        label="latest",
        source="test",
        now="2026-06-12T00:00:00Z",
    )
    slots = bg.normalize_kling_o3_option_slots(beat)
    assert slots[0] and slots[0]["video_path"] == "/tmp/a.mp4"
    assert slots[1] and slots[1]["video_path"] == "/tmp/new.mp4"
    assert slots[2] and slots[2]["video_path"] == "/tmp/c.mp4"
    assert beat["kling_o3_video_path"] == "/tmp/new.mp4"


def test_normalize_assigns_legacy_options_to_slot_indices() -> None:
    beat = {
        "beat_id": "bg_test",
        "kling_o3_options": [
            {"key": "x", "video_path": "/tmp/x.mp4"},
            {"key": "y", "video_path": "/tmp/y.mp4"},
        ],
    }
    slots = bg.normalize_kling_o3_option_slots(beat)
    assert slots[0]["video_path"] == "/tmp/x.mp4"
    assert slots[1]["video_path"] == "/tmp/y.mp4"
    assert slots[2] is None
