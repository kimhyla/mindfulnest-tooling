"""Avatar Pro prompt pollution must restore Element/Omni V2 build_kling_o3_prompt shape."""
from __future__ import annotations

import beat_generator as bg
from kling_o3_prompt import kling_o3_prompt_passes_v2_lint

_AVATAR_POISON = (
    "Continuity: Loral has just heard Oliver say: \"Hi\".\n\n"
    "Continutiy: Loral the racooon stands chest-up portrait. TRIPOD LOCK — static camera.\n"
    "PROHIBIT: no Chinese characters."
)


def test_o3_prompt_is_avatar_pro_poisoned_detects_tripod_lock():
    assert bg.o3_prompt_is_avatar_pro_poisoned(_AVATAR_POISON)


def test_heal_avatar_pro_poisoned_rebuilds_v2_and_clears_box_law():
    beat = {
        "beat_id": "bg_arc1_event3b_full_beat_02",
        "speaker": "Lorelai",
        "dialogue_text": "Hello?",
        "emotion": "attentive",
        "kling_o3_prompt": _AVATAR_POISON,
        "o3_prompt_box_law": True,
        "kling_o3_mode": bg.KLING_O3_MODE_AVATAR,
        "o3_generate_mode": bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    }
    assert bg.heal_avatar_pro_poisoned_o3_prompt(beat) is True
    assert kling_o3_prompt_passes_v2_lint(beat["kling_o3_prompt"])
    assert "TRIPOD LOCK" not in beat["kling_o3_prompt"]
    assert beat["kling_o3_prompt"].startswith("@Image1 (Loral)")
    assert not bg.o3_prompt_box_law_active(beat)
    assert beat["kling_o3_mode"] == bg.KLING_O3_MODE_ELEMENT_NATIVE


def test_migrate_sidecar_skips_avatar_heal_when_box_law_active():
    """Canonical skip must run before avatar poison heal — operator prompts are protected."""
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_02",
        "speaker": "Lorelai",
        "dialogue_text": "Hello kiddo",
        "kling_o3_prompt": _AVATAR_POISON,
        "o3_prompt_box_law": True,
    }
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "1": {
                "segments": {
                    "2|pre": {
                        "beats": [beat],
                    }
                }
            }
        }
    }
    before = beat["kling_o3_prompt"]
    bg._migrate_sidecar(sidecar)
    assert beat["kling_o3_prompt"] == before


def test_heal_skips_valid_v2_operator_prompt():
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_02",
        "speaker": "Lorelai",
        "dialogue_text": "Hello kiddo",
        "kling_o3_prompt": (
            "@Image1 (Loral). Scene from @Image2.\n\n"
            'Loral speaks in a warm excited conversational pace: "Hello kiddo."\n\n'
            "Children's illustrated fantasy storybook style, warm golden forest light."
        ),
        "o3_prompt_box_law": True,
    }
    before = beat["kling_o3_prompt"]
    assert bg.heal_avatar_pro_poisoned_o3_prompt(beat) is False
    assert beat["kling_o3_prompt"] == before
    assert kling_o3_prompt_passes_v2_lint(before)
