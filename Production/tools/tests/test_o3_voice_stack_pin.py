"""Per-beat O3 voice stack pin — legacy rows only; proven registry wins at submit."""
from __future__ import annotations

import beat_generator as bg
from kling_o3_prompt import validate_element_list_alignment
from kling_voice_bind import (
    advance_o3_element_quality_for_proven_registry,
    detect_voice_bind_drift,
    reconcile_o3_element_quality_for_submit,
)


BEAT3_PIN = {
    "pinned_from_beat_id": "bg_arc1_event2_pre_beat_03",
    "element_id": "313390553209506",
    "element_name": "Lorelai",
    "kling_voice_id": "895024801360777292",
}


def test_resolve_o3_element_list_entry_uses_pin_when_no_proven(monkeypatch):
    monkeypatch.setattr(
        "tools.kling_character_registry.get_proven_element_list_entry",
        lambda _s: None,
    )
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


def test_stack_pin_does_not_skip_registry_alignment(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.kling_character_registry.get_proven_element_list_entry",
        lambda _s: None,
    )
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
    assert any("element_name must be" in e for e in errors)


def test_proven_registry_migration_skips_voice_bind_drift(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {
            "proven_o3_bind": {
                "element_id": "313441038164306",
                "kling_voice_id": "895210468825628751",
            },
        },
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.resolve_proven_o3_bind",
        lambda entry: (entry or {}).get("proven_o3_bind"),
    )
    beat = {
        "speaker": "Lorelai",
        "o3_element_quality": {
            "speaker": "Lorelai",
            "element_id": "313390553209506",
            "kling_voice_id": "895024801360777292",
        },
    }
    changed = advance_o3_element_quality_for_proven_registry(
        beat,
        "Lorelai",
        registry_element_id="313441038164306",
        registry_voice_id="895210468825628751",
    )
    assert changed is True
    assert detect_voice_bind_drift(beat, "Lorelai", "895210468825628751") is None


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
