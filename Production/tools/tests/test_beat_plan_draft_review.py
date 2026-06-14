"""Review saved plan — draft persistence + reconstruct from beats."""
from __future__ import annotations

import beat_generator as bg


def test_segment_beats_to_plan_rows_reconstructs_stage_and_dialogue():
    beats = [
        {
            "beat_id": "bg_arc1_event2_pre_beat_01",
            "speaker": "[Stage Direction]",
            "dialogue_text": "Ruins in forest light.",
            "emotion": "quiet",
            "scene_notes": "still insert",
            "pipeline": "still_insert",
        },
        {
            "beat_id": "bg_arc1_event2_pre_beat_02",
            "speaker": "Lorelai",
            "dialogue_text": "Hello there!",
            "emotion": "curious",
            "scene_notes": "rooted in place",
        },
    ]
    rows = bg.segment_beats_to_plan_rows(beats)
    assert len(rows) == 2
    assert rows[0]["beat_type"] == "stage_still"
    assert rows[1]["speaker"] == "Lorelai"


def test_apply_approved_extract_plan_keeps_draft_snapshot():
    sidecar = {"arcs": {}}
    plan = [{
        "beat_index": 1,
        "beat_type": "dialogue",
        "speaker": "Lorelai",
        "dialogue_text": "Hi",
        "emotion": "warm",
        "scene_notes": "",
    }]
    bg.apply_approved_extract_plan(
        sidecar, 1, "2", "pre", "summary", plan, {1: "prompt"},
    )
    seg = bg.get_seg_entry(sidecar, 1, "2", "pre")
    draft = seg.get("beat_plan_draft") or {}
    assert draft.get("beats_plan")
    assert len(draft["beats_plan"]) == 1
    assert draft.get("source") == "approved_snapshot"


def test_draft_get_handler_source_wiring():
    text = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    assert "segment_beats_to_plan_rows" in text
    assert "reconstructed_from_beats" in text
