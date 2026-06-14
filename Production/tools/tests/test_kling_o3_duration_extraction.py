"""O3 duration must follow full spoken dialogue, not truncated apostrophe false positives."""
from __future__ import annotations

import beat_generator as bg

ARLO_TRANSITION_PROMPT = """@Image1 (Arlo) Arlo — Transition to Spell. Arlo speaks directly to the camera; the child viewer is off-screen. Scene from @Image2.

Camera: static locked shot, no zoom, no dolly, no pan, no camera movement, stable eye-level medium shot.

Arlo [warm, conspiratorial, to camera]: OK, Kiddo ... help us solve this mystery. Lorelai's our best chance. She knows so much about Everdale! But ... she's so tense, she can't think straight. Let's see if the Great Wizard can teach you a Magic Spell for focusing power... [Faces camera; gentle inviting nod — rooted in place.]

Children's illustrated fantasy storybook style, warm soft lighting."""

LONG_SPEAKS_PROMPT = (
    'Arlo speaks in a warm calm conversational pace: "Guys .... she\'s right. The Great Wizard '
    "told me. He said there was a terrible storm in Ancient Everdale, a long time ago. "
    'Lightning struck, and... the whole system failed. The Rune Stones have been dark ever since."'
)


def test_apostrophe_in_dialogue_does_not_false_positive_single_quote_extract():
    spoken = bg.extract_spoken_dialogue_from_kling_prompt(
        "Arlo speaks: Lorelai's our best chance today.",
    )
    assert "Lorelai" in spoken
    assert spoken.startswith("Lorelai")


def test_bracket_tag_prompt_extracts_full_line_not_apostrophe_tail():
    spoken = bg.extract_spoken_dialogue_from_kling_prompt(ARLO_TRANSITION_PROMPT)
    assert spoken.startswith("OK, Kiddo")
    assert "Lorelai's our best chance" in spoken
    assert "Magic Spell" in spoken
    assert "Faces camera" not in spoken


def test_bracket_tag_transition_resolves_to_12s():
    assert bg.resolve_kling_o3_submit_duration({}, ARLO_TRANSITION_PROMPT) == 12


def test_speaks_quoted_long_line_still_resolves_to_12s():
    assert bg.resolve_kling_o3_submit_duration({}, LONG_SPEAKS_PROMPT) == 12


def test_stale_sidecar_dialogue_does_not_shrink_duration_when_prompt_is_long():
    beat = {
        "dialogue_text": "s our best chance. She knows so much about Everdale!",
        "kling_o3_duration": 8,
    }
    assert bg.resolve_kling_o3_submit_duration(beat, ARLO_TRANSITION_PROMPT) == 12


LORELAI_BEAT09_PROMPT = """@Image1 (Laurel) Lorelai — arc 1 event 2 pre, beat 09. Scene from @Image2.

Camera: Slow zoom in, stable eye-level medium shot.  Laurel looks directly at the camera as she speaks

Laurel speaks in a slow, dramatic, friendly, scholarly tone: "[dramatic, scholarly, friendly, conspiratorial] Well, the ancient world was powered by Light-Magic. [pause] And the Light Magic came through the Rune stones. That's why I'm here, I'm researching the MindfulNest ... for my school project."

Children's illustrated fantasy storybook style, warm golden Everdale light."""


def test_lorelai_beat09_thirty_word_pause_line_resolves_to_12s():
    beat = {
        "dialogue_text": (
            "[dramatic, scholarly, friendly, conspiratorial] Well, the ancient world was "
            "powered by Light-Magic. [pause] And the Light Magic came through the Rune "
            "stones. That's why I'm here, I'm researching the MindfulNest . for my school project."
        ),
        "kling_o3_duration": 8,
    }
    assert bg.resolve_kling_o3_submit_duration(beat, LORELAI_BEAT09_PROMPT) == 12


def test_short_single_chunk_still_caps_at_8s():
    short = 'Laurel speaks in a warm excited conversational pace: "Oh my goodness!"'
    assert bg.resolve_kling_o3_submit_duration({}, short) <= 8
