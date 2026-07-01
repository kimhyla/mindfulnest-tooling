"""Tests for BG O3 selection → stitch slot invalidation."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg
from bg_o3_stitch_invalidation import (
    compute_bg_segment_o3_export_lineage_sig,
    invalidate_stitch_slot_for_bg_o3_selection_change,
    o3_export_authority_changed,
    stamp_bg_o3_export_lineage_on_slot,
)


class _MockStitchState:
    def __init__(self, initial: dict | None = None):
        self.state = initial or {"jobs": {}}

    def mutate_state(self, fn):
        fn(self.state)


class _MockApp:
    def __init__(self, event_dir: Path, state: dict | None = None):
        self.event_dir = event_dir
        self.stitch_state = _MockStitchState(state)


class _MockHandler:
    def __init__(self, event_dir: Path, state: dict | None = None):
        self.app = _MockApp(event_dir, state)


def test_o3_export_authority_changed_detects_path_and_key() -> None:
    before = {
        "kling_o3_video_path": "/a/silent.mp4",
        "kling_o3_selected_option_key": "key_a",
    }
    after_path = dict(before)
    after_path["kling_o3_video_path"] = "/a/audible.mp4"
    after_key = dict(before)
    after_key["kling_o3_selected_option_key"] = "key_b"
    assert o3_export_authority_changed(before, after_path)
    assert o3_export_authority_changed(before, after_key)
    assert not o3_export_authority_changed(before, dict(before))


def test_compute_lineage_sig_changes_when_selection_changes() -> None:
    beats_a = [
        {"beat_id": "bg_test_beat_01", "kling_o3_video_path": "/x/a.mp4", "kling_o3_selected_option_key": "k1"},
    ]
    beats_b = [
        {"beat_id": "bg_test_beat_01", "kling_o3_video_path": "/x/b.mp4", "kling_o3_selected_option_key": "k2"},
    ]
    assert compute_bg_segment_o3_export_lineage_sig(beats_a) != compute_bg_segment_o3_export_lineage_sig(beats_b)


def test_invalidate_clears_resolution_slot_video(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_4"
    event_dir.mkdir()
    old_export = event_dir / "assembled" / "resolution_kling_o3_old.mp4"
    old_export.parent.mkdir(parents=True)
    old_export.write_bytes(b"x")

    sidecar = {
        "arcs": {
            "arc1": {
                "segments": {
                    "event_4_post": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event4_post_beat_05",
                                "kling_o3_video_path": "/new/silent.mp4",
                                "kling_o3_selected_option_key": "silent_key",
                            },
                        ],
                    },
                },
            },
        },
    }
    stitch_state = {
        "jobs": {
            "Event_4_stitch": {
                "slots": {
                    "resolution": {
                        "video_path": str(old_export),
                        "video_dur_ms": 49000,
                        "mux_preview_hash": "abc123",
                        "bg_o3_export_lineage_sig": "old_sig",
                    },
                },
            },
        },
    }
    h = _MockHandler(event_dir, stitch_state)
    logs = invalidate_stitch_slot_for_bg_o3_selection_change(
        h,
        beat_id="bg_arc1_event4_post_beat_05",
        sidecar=sidecar,
        before_beat={
            "kling_o3_video_path": "/old/audible.mp4",
            "kling_o3_selected_option_key": "audible_key",
        },
        after_beat={
            "kling_o3_video_path": "/new/silent.mp4",
            "kling_o3_selected_option_key": "silent_key",
        },
    )
    slot = h.app.stitch_state.state["jobs"]["Event_4_stitch"]["slots"]["resolution"]
    assert "video_path" not in slot
    assert slot.get("superseded_bg_export_video_path") == str(old_export)
    assert slot.get("bg_o3_export_stale") is True
    assert "mux_preview_hash" not in slot
    assert logs


def test_stamp_lineage_clears_stale_flags() -> None:
    slot = {
        "bg_o3_export_stale": True,
        "bg_o3_export_stale_reason": "bg_o3_select",
        "superseded_bg_export_video_path": "/old.mp4",
    }
    beats = [{"beat_id": "b1", "kling_o3_video_path": "/x.mp4", "kling_o3_selected_option_key": "k1"}]
    sig = stamp_bg_o3_export_lineage_on_slot(slot, segment_beats=beats)
    assert sig
    assert slot.get("bg_o3_export_lineage_sig") == sig
    assert "bg_o3_export_stale" not in slot
