"""Regression — prompt-box law: Generate payload is what Kling hears."""
from __future__ import annotations

from pathlib import Path

import beat_generator as bg
from kling_o3_element_beat_pipeline import resolve_element_o3_submit_prompt

BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"

USER_LINE = (
    "OK, Kiddo. CUSTOM USER LINE ONLY. She knows the MindfulNest! "
    "But she's stressed. Let's see if the Wizard can teach you a calming spell."
)
USER_PROMPT = (
    "@Image1 (Arlo). Scene from @Image2.\n\n"
    "Camera: static locked shot.\n\n"
    f'Arlo speaks in a warm calm conversational pace: [warm] "{USER_LINE}"\n\n'
    "Children's illustrated fantasy storybook style, warm soft lighting"
)
CANON_COMPACT = (
    "OK, Kiddo. Lorelai's our best chance. She knows the MindfulNest! "
    "But she's stressed. Let's see if the Wizard can teach you a calming spell."
)


def _semi_canonical_arlo_beat() -> dict:
    return {
        "beat_id": "bg_arc1_event2_pre_beat_24",
        "speaker": "Arlo",
        "intro_beat_role": bg.INTRO_BEAT_ROLE_SEMI_CANONICAL,
        "emotion": "upbeat",
        "dialogue_text": CANON_COMPACT,
        "kling_o3_prompt": USER_PROMPT,
        "o3_prompt_box_law": True,
    }


def test_stamp_and_active_helpers():
    beat: dict = {}
    bg.stamp_o3_prompt_box_law(beat, USER_PROMPT)
    assert beat.get("o3_prompt_box_law") is True
    assert beat.get("kling_o3_prompt") == USER_PROMPT
    assert bg.o3_prompt_box_law_active(beat)
    bg.clear_o3_prompt_box_law(beat)
    assert not bg.o3_prompt_box_law_active(beat)


def test_prepare_skips_normalize_rebuild_when_prompt_box_law():
    beat = _semi_canonical_arlo_beat()
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, USER_PROMPT)
    assert USER_LINE in prepared
    assert CANON_COMPACT not in prepared or USER_LINE in prepared
    assert "Camera: static locked shot" in prepared


def test_heal_o3_element_submit_prompt_skipped_under_prompt_box_law():
    beat = _semi_canonical_arlo_beat()
    assert bg.heal_o3_element_submit_prompt(beat) is False
    assert USER_LINE in (beat.get("kling_o3_prompt") or "")


def test_resolve_element_o3_submit_prompt_preserves_user_line():
    beat = _semi_canonical_arlo_beat()
    prompt, spoken = resolve_element_o3_submit_prompt(beat)
    assert USER_LINE in prompt
    assert "CUSTOM USER LINE ONLY" in spoken
    assert CANON_COMPACT not in spoken


def test_submit_handler_uses_generation_intent_commit():
    text = BACKGROUND.read_text(encoding="utf-8")
    assert "build_generation_intent" in text
    assert "write_generation_intent" in text
    assert 'subprocess_env["MN_O3_INTENT_PATH"]' in text
    assert "ensure_operator_insert_char_ref_parity" not in text.split("handle_bg_submit_arlo_o3_voice")[1].split("def ")[0]


def test_finalize_proven_element_preserves_prompt_box_law(tmp_path):
    sidecar_path = tmp_path / "beat_generator_state.json"
    src_ref = {"abs_path": str(tmp_path / "char.png")}
    src_bg = {"abs_path": str(tmp_path / "bg.png")}
    (tmp_path / "char.png").write_bytes(b"x")
    (tmp_path / "bg.png").write_bytes(b"y")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_18",
                                "speaker": "Lorelai",
                                "reference_image": src_ref,
                                "bg_ref_image": src_bg,
                            },
                        ],
                    },
                },
            },
        },
    }
    sidecar_path.write_text("{}", encoding="utf-8")
    custom = (
        '@Image1 (Loral). Scene from @Image2.\n\n'
        'Loral speaks in a female voice: "Hello kiddo."\n\n'
        "Children's illustrated fantasy storybook style"
    )
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_30",
        "speaker": "Lorelai",
        "beat_plan_source": "operator_insert_v1",
        "kling_o3_prompt": custom,
    }
    bg.stamp_o3_prompt_box_law(beat, custom)
    bg.finalize_proven_element_beat(beat, sidecar, "Lorelai", event_id="2", phase="pre")
    assert bg.o3_prompt_box_law_active(beat)
    assert "female voice" in (beat.get("kling_o3_prompt") or "")
    assert beat.get("kling_o3_prompt") == custom


def test_heal_element_bound_voice_prompt_skipped_under_prompt_box_law():
    beat = _semi_canonical_arlo_beat()
    beat["kling_o3_prompt"] = (
        '@Image1 (Arlo). Scene from @Image2.\n\n'
        'Arlo speaks in a CUSTOM delivery pace: "CUSTOM USER LINE ONLY"\n\n'
        "Children's illustrated fantasy storybook style"
    )
    assert bg.heal_element_bound_voice_prompt(beat) is False
    assert "CUSTOM delivery pace" in (beat.get("kling_o3_prompt") or "")


def test_without_law_normalize_can_rewrite_voice_block():
    beat = _semi_canonical_arlo_beat()
    beat.pop("o3_prompt_box_law", None)
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, USER_PROMPT)
    assert USER_LINE in prepared or CANON_COMPACT in prepared
    assert prepared != USER_PROMPT or "Only @Image1 is visible" in prepared
