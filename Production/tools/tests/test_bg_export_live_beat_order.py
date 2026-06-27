"""Export job must concat live segment beats, not frozen submit-time beat_ids."""
from __future__ import annotations

from server_handlers import kling_o3 as ko


def test_load_beats_for_export_job_uses_live_segment_order() -> None:
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {"beat_id": "bg_arc1_event2_pre_beat_14"},
                            {"beat_id": "bg_arc1_event2_pre_beat_15"},
                            {"beat_id": "bg_arc1_event2_pre_beat_17"},
                        ],
                    },
                },
            },
        },
    }
    ctx = {
        "arc_number": 1,
        "bg_event_id": "2",
        "phase": "pre",
        "beat_ids": [
            "bg_arc1_event2_pre_beat_14",
            "bg_arc1_event2_pre_beat_31",
            "bg_arc1_event2_pre_beat_32",
        ],
    }

    class _Bg:
        get_seg_entry = staticmethod(
            lambda _sc, arc, evt, ph: sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"],
        )

    beats = ko._load_beats_for_export_job(_Bg(), sidecar, ctx)
    assert [b["beat_id"] for b in beats] == [
        "bg_arc1_event2_pre_beat_14",
        "bg_arc1_event2_pre_beat_15",
        "bg_arc1_event2_pre_beat_17",
    ]
