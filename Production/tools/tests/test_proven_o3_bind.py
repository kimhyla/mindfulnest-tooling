"""proven_o3_bind — registry Element+voice must not drift from proven stacks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
REG_PATH = TOOLS.parent / "character_subjects.json"

LORELAI_PROVEN_ELEMENT = "313441038164306"
LORELAI_PROVEN_VOICE = "895210468825628751"
ARLO_PROVEN_ELEMENT = "313106596591323"
ARLO_PROVEN_VOICE = "893833801724461134"


def _patch_registry(monkeypatch, tmp_path: Path, speaker: str, overrides: dict):
    data = json.loads(REG_PATH.read_text(encoding="utf-8"))
    entry = dict(data["characters"][speaker])
    entry.update(overrides)
    data["characters"][speaker] = entry
    reg_file = tmp_path / "character_subjects.json"
    reg_file.write_text(json.dumps(data), encoding="utf-8")
    import kling_character_registry as reg

    monkeypatch.setattr(reg, "character_subjects_path", lambda: reg_file)
    monkeypatch.setattr(reg, "load_character_subjects", lambda: json.loads(reg_file.read_text()))
    return reg


@pytest.fixture()
def lorelai_registry(monkeypatch, tmp_path: Path):
    return _patch_registry(
        monkeypatch,
        tmp_path,
        "Lorelai",
        {
            "element_id": "313472196292503",
            "kling_voice_id": LORELAI_PROVEN_VOICE,
            "proven_o3_bind": {
                "element_id": LORELAI_PROVEN_ELEMENT,
                "kling_voice_id": LORELAI_PROVEN_VOICE,
                "proven_from_beat_id": "bg_arc1_event2_pre_beat_18",
                "lock_element_id": True,
            },
        },
    )


@pytest.fixture()
def arlo_registry(monkeypatch, tmp_path: Path):
    return _patch_registry(
        monkeypatch,
        tmp_path,
        "Arlo",
        {
            "element_id": "313040140095522",
            "kling_voice_id": "891326025224429589",
            "proven_o3_bind": {
                "element_id": ARLO_PROVEN_ELEMENT,
                "kling_voice_id": ARLO_PROVEN_VOICE,
                "proven_from_beat_id": "bg_arc1_event1_pre_beat_10",
                "lock_element_id": True,
            },
        },
    )


def test_lorelai_get_element_list_entry_uses_proven_bind(lorelai_registry):
    entry = lorelai_registry.get_element_list_entry("Lorelai")
    assert entry is not None
    assert entry["element_id"] == LORELAI_PROVEN_ELEMENT
    assert entry["voice_id"] == LORELAI_PROVEN_VOICE
    assert entry["element_name"] == "Loral"


def test_lorelai_pose_refresh_cannot_rotate_locked_element(lorelai_registry, monkeypatch):
    cfg = lorelai_registry.get_character_entry("Lorelai")
    monkeypatch.delenv("MN_FORCE_ELEMENT_REREGISTER", raising=False)
    out = lorelai_registry.apply_element_id_with_proven_lock(
        cfg,
        "313999999999999",
        source="test_pose_refresh",
    )
    assert out["element_id"] == LORELAI_PROVEN_ELEMENT
    assert out.get("_proven_bind_element_restore")


def test_arlo_get_element_list_entry_uses_proven_bind(arlo_registry):
    entry = arlo_registry.get_element_list_entry("Arlo")
    assert entry is not None
    assert entry["element_id"] == ARLO_PROVEN_ELEMENT
    assert entry["voice_id"] == ARLO_PROVEN_VOICE


def test_arlo_get_bound_voice_id_uses_proven_bind(arlo_registry):
    assert arlo_registry.get_bound_voice_id("Arlo") == ARLO_PROVEN_VOICE


def test_lorelai_get_proven_element_list_entry_uses_loral_display_name(lorelai_registry):
    entry = lorelai_registry.get_proven_element_list_entry("Lorelai")
    assert entry is not None
    assert entry["element_id"] == LORELAI_PROVEN_ELEMENT
    assert entry["voice_id"] == LORELAI_PROVEN_VOICE
    assert entry["element_name"] == "Loral"


def test_arlo_pose_refresh_cannot_rotate_locked_element(arlo_registry, monkeypatch):
    cfg = arlo_registry.get_character_entry("Arlo")
    monkeypatch.delenv("MN_FORCE_ELEMENT_REREGISTER", raising=False)
    out = arlo_registry.apply_element_id_with_proven_lock(
        cfg,
        "313040140095522",
        source="test_chipper_interim_refresh",
    )
    assert out["element_id"] == ARLO_PROVEN_ELEMENT
    assert out.get("_proven_bind_element_restore")
