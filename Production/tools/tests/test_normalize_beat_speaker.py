"""Sidecar speaker must be registry key (Lorelai), not Kling display name (Loral)."""
from __future__ import annotations

from tools import kling_character_registry as reg


def test_loral_normalizes_to_lorelai():
    assert reg.normalize_beat_speaker_for_sidecar("Loral") == "Lorelai"


def test_lorelai_unchanged():
    assert reg.normalize_beat_speaker_for_sidecar("Lorelai") == "Lorelai"


def test_guide_bird_canonicalizes_to_arlo():
    assert reg.normalize_beat_speaker_for_sidecar("Guide Bird") == "Arlo"


def test_stage_direction_preserved():
    assert reg.normalize_beat_speaker_for_sidecar("[Stage Direction]") == "[Stage Direction]"


def test_script_label_colon_strips_to_registry_key():
    assert reg.strip_speaker_script_label("Arlo:") == "Arlo"
    assert reg.strip_speaker_script_label("Arlo :") == "Arlo"
    assert reg.normalize_beat_speaker_for_sidecar("Arlo:") == "Arlo"
    assert reg.normalize_beat_speaker_for_sidecar("Lorelai:") == "Lorelai"
    assert reg.normalize_beat_speaker_for_sidecar("Guide Bird:") == "Arlo"


def test_resolve_char_key_accepts_colon_label(monkeypatch):
    chars = {"Arlo": {"status": "active", "element_id": "1"}}
    monkeypatch.setattr(reg, "load_character_subjects", lambda: {"characters": chars})
    assert reg._resolve_char_key("Arlo:", chars) == "Arlo"
