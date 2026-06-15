"""Proven voice pin must copy char ref from source beat — not bypass Element gates."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent


@pytest.fixture()
def bg_module(tmp_path, monkeypatch):
    import beat_generator as bg

    sidecar_path = tmp_path / "beat_generator_state.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_2_pre": {
                                "beats": [
                                    {
                                        "beat_id": "bg_arc1_event2_pre_beat_18",
                                        "speaker": "Lorelai",
                                        "reference_image": {
                                            "key": "proven_ref",
                                            "abs_path": str(tmp_path / "proven.png"),
                                        },
                                    },
                                    {
                                        "beat_id": "bg_arc1_event2_pre_beat_27",
                                        "speaker": "Lorelai",
                                        "reference_image": {
                                            "key": "wrong_ref",
                                            "abs_path": str(tmp_path / "wrong.png"),
                                        },
                                        "reference_image_locked": True,
                                        "o3_voice_stack_pin": {
                                            "pinned_from_beat_id": "bg_arc1_event2_pre_beat_18",
                                            "element_id": "313441038164306",
                                            "kling_voice_id": "895210468825628751",
                                        },
                                    },
                                ]
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "proven.png").write_bytes(b"x")
    (tmp_path / "wrong.png").write_bytes(b"y")
    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    monkeypatch.setattr(bg, "read_sidecar", lambda: json.loads(sidecar_path.read_text()))
    monkeypatch.setattr(bg, "write_sidecar", lambda data: sidecar_path.write_text(json.dumps(data)))
    return bg


def test_apply_proven_char_ref_from_pin_source(bg_module):
    sidecar = bg_module.read_sidecar()
    _, beat = bg_module.find_beat(sidecar, "bg_arc1_event2_pre_beat_27")
    assert beat is not None
    changed = bg_module.apply_proven_char_ref_from_pin_source(beat, sidecar)
    assert changed is False
    assert "wrong.png" in str(beat["reference_image"]["abs_path"])
    assert beat["reference_image_locked"] is True


def test_apply_proven_char_ref_from_pin_source_when_unlocked(bg_module):
    sidecar = bg_module.read_sidecar()
    _, beat = bg_module.find_beat(sidecar, "bg_arc1_event2_pre_beat_27")
    beat["reference_image_locked"] = False
    changed = bg_module.apply_proven_char_ref_from_pin_source(beat, sidecar)
    assert changed is True
    assert "proven.png" in str(beat["reference_image"]["abs_path"])
    assert beat["reference_image_locked"] is True


def test_pin_does_not_skip_char_ref_gate(bg_module, monkeypatch):
    """Voice stack pin must not short-circuit require_element_char_ref_for_o3."""
    sidecar = bg_module.read_sidecar()
    _, beat = bg_module.find_beat(sidecar, "bg_arc1_event2_pre_beat_27")
    beat["element_char_ref_ok"] = False
    beat["element_char_ref_error"] = "bad ref"
    monkeypatch.setattr(
        bg_module,
        "sync_element_char_ref_status",
        lambda b, heal_mismatch=False: b.get("element_char_ref_ok", False),
    )
    with pytest.raises(RuntimeError, match="ELEMENT_VISUAL_MISMATCH"):
        bg_module.require_element_char_ref_for_o3(beat)


def test_validate_proven_o3_element_submit_blocks_wrong_element(bg_module, monkeypatch):
    import kling_character_registry as reg

    reg_file = Path(bg_module.BG_SIDECAR_PATH).parent / "character_subjects.json"
    reg_file.write_text(
        json.dumps(
            {
                "characters": {
                    "Lorelai": {
                        "element_id": "313441038164306",
                        "kling_voice_id": "895210468825628751",
                        "proven_o3_bind": {
                            "element_id": "313441038164306",
                            "kling_voice_id": "895210468825628751",
                            "lock_element_id": True,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(reg, "character_subjects_path", lambda: reg_file)
    monkeypatch.setattr(reg, "load_character_subjects", lambda: json.loads(reg_file.read_text()))
    sidecar = bg_module.read_sidecar()
    _, beat = bg_module.find_beat(sidecar, "bg_arc1_event2_pre_beat_27")
    err = bg_module.validate_proven_o3_element_submit(
        beat,
        "Lorelai",
        "313472196292503",
    )
    assert err is not None
    assert "313441038164306" in err


def test_proven_bypass_denied_when_locked_beat_uses_different_still(bg_module, tmp_path):
    (tmp_path / "proven.png").write_bytes(b"p")
    (tmp_path / "operator.png").write_bytes(b"o")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_03",
                                "speaker": "Lorelai",
                                "reference_image": {"abs_path": str(tmp_path / "proven.png")},
                            },
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_30",
                                "speaker": "Lorelai",
                                "reference_image": {"abs_path": str(tmp_path / "operator.png")},
                                "reference_image_locked": True,
                                "o3_voice_stack_pin": {
                                    "pinned_from_beat_id": "bg_arc1_event2_pre_beat_03",
                                },
                            },
                        ],
                    },
                },
            },
        },
    }
    _, beat = bg_module.find_beat(sidecar, "bg_arc1_event2_pre_beat_30")
    assert bg_module.proven_bypass_allowed_for_o3_submit(beat, sidecar, "Lorelai") is False
