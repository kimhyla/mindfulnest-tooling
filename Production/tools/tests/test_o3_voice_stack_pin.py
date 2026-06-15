"""Per-beat O3 voice stack pin — use proven Element+voice without changing registry."""
from __future__ import annotations

import beat_generator as bg
from kling_o3_prompt import validate_element_list_alignment
from kling_voice_bind import (
    detect_voice_bind_drift,
    reconcile_o3_element_quality_for_submit,
)


BEAT3_PIN = {
    "pinned_from_beat_id": "bg_arc1_event2_pre_beat_03",
    "element_id": "313390553209506",
    "element_name": "Lorelai",
    "kling_voice_id": "895024801360777292",
}


def test_resolve_o3_element_list_entry_uses_pin() -> None:
    beat = {
        "speaker": "Lorelai",
        "o3_voice_stack_pin": BEAT3_PIN,
        "kling_o3_prompt": '@Image1 (Lorelai). Lorelai speaks in a warm calm conversational pace: "Hi!"',
    }
    entry = bg.resolve_o3_element_list_entry(beat, "Lorelai")
    assert entry == {
        "element_id": "313390553209506",
        "element_name": "Lorelai",
        "voice_id": "895024801360777292",
    }


def test_stack_pin_skips_voice_bind_drift() -> None:
    beat = {
        "o3_voice_stack_pin": BEAT3_PIN,
        "o3_element_quality": {
            "speaker": "Lorelai",
            "kling_voice_id": "895210468825628751",
            "element_id": "313441038164306",
        },
    }
    assert detect_voice_bind_drift(beat, "Lorelai", "895210468825628751") is None


def test_stack_pin_skips_registry_alignment_mismatch() -> None:
    beat = {
        "o3_voice_stack_pin": BEAT3_PIN,
        "kling_o3_prompt": '@Image1 (Lorelai). Lorelai speaks in a warm calm conversational pace: "Hi!"',
    }
    entry = bg.resolve_o3_element_list_entry(beat, "Lorelai")
    errors = validate_element_list_alignment(
        "Lorelai",
        entry,
        beat["kling_o3_prompt"],
        beat=beat,
    )
    assert errors == []


def test_reconcile_o3_element_quality_from_active_option_binding() -> None:
    beat = {
        "speaker": "Lorelai",
        "kling_o3_video_path": "/clips/g12_delivery.mp4",
        "o3_element_quality": {
            "speaker": "Lorelai",
            "element_id": "313390553209506",
            "kling_voice_id": "895024801360777292",
            "pinned_from_beat_id": "bg_arc1_event2_pre_beat_03",
        },
        "kling_o3_options": [
            {
                "video_path": "/clips/g12_delivery.mp4",
                "active": True,
                "o3_voice_binding": {
                    "element_id": "313441038164306",
                    "kling_voice_id": "895210468825628751",
                },
            }
        ],
    }
    changed = reconcile_o3_element_quality_for_submit(
        beat,
        "Lorelai",
        registry_element_id="313441038164306",
        registry_voice_id="895210468825628751",
    )
    assert changed is True
    quality = beat["o3_element_quality"]
    assert quality["element_id"] == "313441038164306"
    assert quality["kling_voice_id"] == "895210468825628751"
    assert "pinned_from_beat_id" not in quality
    assert detect_voice_bind_drift(beat, "Lorelai", "895210468825628751") is None
