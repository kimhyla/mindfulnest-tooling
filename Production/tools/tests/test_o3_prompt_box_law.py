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


def test_submit_handler_stamps_prompt_box_law_and_subprocess_env():
    text = BACKGROUND.read_text(encoding="utf-8")
    assert "stamp_o3_prompt_box_law" in text
    assert 'subprocess_env["MN_O3_PROMPT_BOX_LAW"] = "1"' in text
    assert "upgrade_element_bound_voice_prompt" in text
    assert "if not explicit_user_prompt:" in text
    assert "Prompt-box law still skips heal_o3" in text


def test_without_law_normalize_can_rewrite_voice_block():
    beat = _semi_canonical_arlo_beat()
    beat.pop("o3_prompt_box_law", None)
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, USER_PROMPT)
    assert USER_LINE in prepared or CANON_COMPACT in prepared
    assert prepared != USER_PROMPT or "Only @Image1 is visible" in prepared
