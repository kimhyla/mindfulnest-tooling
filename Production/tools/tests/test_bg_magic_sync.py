"""BG magic sync — storyboard partition ↔ Beat Gen sidecar."""
from __future__ import annotations

import beat_generator as bg


def test_merge_storyboard_magic_into_bg_beat_fills_missing_still():
    sidecar_beat = {"beat_id": "bg_arc1_event1_post_beat_01", "magic_video_path": "mv.mp4"}
    production_state = {
        "videos": {
            "resolution": {
                "beats": {
                    "beat_01": {
                        "magic_still_path": "magic_still_beat_01_20260605-180641.mp4",
                        "magic_manual_path": [[0.5, 0.5]],
                    },
                },
            },
        },
    }
    merged = bg.merge_storyboard_magic_into_bg_beat(
        sidecar_beat, production_state, "resolution",
    )
    assert merged["magic_still_path"] == "magic_still_beat_01_20260605-180641.mp4"
    assert merged["magic_video_path"] == "mv.mp4"


def test_stitch_export_prefers_magic_video_when_o3_approved(tmp_path):
    event_dir = tmp_path / "Event_1"
    event_dir.mkdir()
    magic_video = event_dir / "magic_video_beat_01.mp4"
    magic_still = event_dir / "magic_still_beat_01.mp4"
    magic_video.write_bytes(b"mv")
    magic_still.write_bytes(b"ms")
    beat = {
        "beat_id": "bg_arc1_event1_post_beat_01",
        "kling_o3_status": "approved",
        "magic_video_path": magic_video.name,
        "magic_still_path": magic_still.name,
    }
    chosen = bg.resolve_beat_stitch_export_clip_path(beat, event_dir, tmp_path / "scratch")
    assert chosen == magic_video.resolve()


def test_storyboard_beat_id_maps_by_display_order_position():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_post": {
                        "beats": [
                            {"beat_id": "bg_arc1_event1_post_beat_01"},
                            {"beat_id": "bg_arc1_event1_post_beat_21"},
                        ],
                    },
                },
            },
        },
    }
    production_state = {
        "videos": {
            "resolution": {
                "display_order": ["beat_01", "beat_02"],
                "beats": {},
            },
        },
    }
    mapped = bg.storyboard_beat_id_for_bg_beat(
        "bg_arc1_event1_post_beat_21",
        sidecar=sidecar,
        production_state=production_state,
        video_role="resolution",
    )
    assert mapped == "beat_02"


def test_merge_storyboard_magic_uses_display_order_mapping():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_post": {
                        "beats": [
                            {"beat_id": "bg_arc1_event1_post_beat_01"},
                            {"beat_id": "bg_arc1_event1_post_beat_21"},
                        ],
                    },
                },
            },
        },
    }
    production_state = {
        "videos": {
            "resolution": {
                "display_order": ["beat_01", "beat_02"],
                "beats": {
                    "beat_02": {
                        "magic_still_path": "magic_still_beat_02.mp4",
                    },
                },
            },
        },
    }
    merged = bg.merge_storyboard_magic_into_bg_beat(
        {"beat_id": "bg_arc1_event1_post_beat_21"},
        production_state,
        "resolution",
        sidecar,
    )
    assert merged["magic_still_path"] == "magic_still_beat_02.mp4"


def test_persist_magic_fields_on_bg_sidecar_by_storyboard_id():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_post": {
                        "beats": [{"beat_id": "bg_arc1_event1_post_beat_21"}],
                    },
                },
            },
        },
    }
    ok = bg.persist_magic_fields_on_bg_sidecar(
        sidecar,
        arc_number=1,
        event_id="1",
        phase="post",
        request_beat_id="beat_21",
        fields={"magic_still_path": "magic_still_beat_21.mp4"},
    )
    assert ok is True
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_1_post"]["beats"][0]
    assert beat["magic_still_path"] == "magic_still_beat_21.mp4"
