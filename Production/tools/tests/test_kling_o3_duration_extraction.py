"""O3 duration must follow full spoken dialogue, not truncated apostrophe false positives."""
from __future__ import annotations

import beat_generator as bg


def _validate_prepared(speaker: str, prompt: str) -> list[str]:
    from tools import kling_o3_prompt as o3p

    prepared = bg.prepare_kling_o3_prompt_for_submit({"speaker": speaker}, prompt)
    return o3p.validate_element_bound_voice_prompt(speaker, prepared)

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


ARLO_BEAT24_QUOTED_STAGING = (
    'Arlo speaks in a warm calm conversational pace, steady and natural, clear delivery, '
    "brisk but not rushed, not bubbly or hyper, not slow, not dramatic, not childlike or "
    'baby-talk: "OK, Kiddo . Lorelai\'s our best chance. [Faces camera; gentle inviting nod '
    '— rooted in place.]"'
)


def test_quoted_voice_line_strips_performance_staging_from_spoken():
    spoken = bg.extract_spoken_dialogue_from_kling_prompt(ARLO_BEAT24_QUOTED_STAGING)
    assert spoken.startswith("OK, Kiddo")
    assert "Lorelai's our best chance" in spoken
    assert "Faces camera" not in spoken
    assert "rooted in place" not in spoken


def test_heal_spoken_staging_rewrites_prompt_quote():
    beat = {
        "speaker": "Arlo",
        "dialogue_text": (
            "OK, Kiddo . Lorelai's our best chance. [Faces camera; gentle inviting nod "
            "— rooted in place.]"
        ),
        "kling_o3_prompt": ARLO_BEAT24_QUOTED_STAGING,
    }
    assert bg.heal_spoken_staging_in_voice_prompt(beat) is True
    assert "Faces camera" not in beat["kling_o3_prompt"]
    assert "Faces camera" not in beat["dialogue_text"]


BEAT24_BODY_STAGING = """@Image1 (Arlo) Arlo — Transition to Spell. Scene from @Image2.

Camera: static shot, stable eye-level medium shot.
[Faces camera; gentle inviting nod, expression knowing and warmly conspiratorial — rooted in place.] [Faces camera directly ; gentle knowing smile — rooted in place, all warmth in face and that one quiet hand gesture.]"

Arlo speaks in a warm calm conversational pace, steady and natural, clear delivery, brisk but not rushed, not bubbly or hyper, not slow, not dramatic, not childlike or baby-talk: "OK, Kiddo . Lorelai's our best chance to solve this mystery. She knows so much about the MindfulNest! [pause] But [pause] she seems kinda stressed out. Let's see if the Great Wizard can teach you a Magic Spell for calming down, so she can help us figure it out!"

Children's illustrated fantasy storybook style, warm soft lighting."""


def test_strip_performance_staging_from_prompt_body():
    cleaned = bg.strip_performance_staging_from_kling_prompt(BEAT24_BODY_STAGING)
    assert "Faces camera" not in cleaned
    assert "Camera:" not in cleaned
    assert "warm calm conversational pace" in cleaned
    assert bg.prompt_body_has_performance_staging(BEAT24_BODY_STAGING) is True
    assert bg.prompt_body_has_performance_staging(cleaned) is False


def test_normalize_o3_element_bound_prompt_strips_arlo_transition_prose(monkeypatch):
    monkeypatch.setattr(
        "kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    beat = {
        "speaker": "Arlo",
        "dialogue_text": (
            "OK, Kiddo . Lorelai's our best chance to solve this mystery. "
            "She knows so much about the MindfulNest!"
        ),
        "kling_o3_prompt": ARLO_TRANSITION_PROMPT,
    }
    normalized = bg.normalize_o3_element_bound_prompt(beat, beat["kling_o3_prompt"])
    assert "speaks directly to the camera" not in normalized.lower()
    assert "Camera:" not in normalized
    assert "not bubbly or hyper" in normalized
    assert "gesture toward the lens" not in normalized.lower()
    assert bg.prompt_body_has_performance_staging(normalized) is False


def test_heal_o3_element_submit_prompt_persists_minimal_arlo_shell(monkeypatch):
    monkeypatch.setattr(
        "kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    beat = {
        "speaker": "Arlo",
        "dialogue_text": "OK, Kiddo . Lorelai's our best chance.",
        "kling_o3_prompt": ARLO_TRANSITION_PROMPT,
    }
    assert bg.heal_o3_element_submit_prompt(beat) is True
    assert "speaks directly to the camera" not in beat["kling_o3_prompt"].lower()
    assert "Camera:" not in beat["kling_o3_prompt"]


def test_normalize_rebuilds_tessa_beat2_prose_shell(monkeypatch):
    monkeypatch.setattr(
        "kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    beat2 = """@Image1 (Tessa) Tessa — arc 1 event 2 pre, beat 02. Scene from @Image2.

Tessa holds a soft polite smile, one small hand rising in a gentle wave hello.

((Faces camera directly; warm welcome))

Tessa speaks in a warm gentle conversational pace, soft and vulnerable but clear, natural delivery, steady and not slow, not dragging, not whispered, not childlike or baby-talk: "Hello there . how are you?"

Children's illustrated fantasy storybook style, warm golden Everdale light."""
    beat = {
        "speaker": "Tessa",
        "dialogue_text": "Hello there . how are you?",
        "kling_o3_prompt": beat2,
    }
    prepared = bg.prepare_kling_o3_prompt_for_submit(beat, beat2)
    assert "wave hello" not in prepared.lower()
    assert "Faces camera" not in prepared
    assert "Hello there . how are you?" in prepared
    assert bg.prompt_body_has_performance_staging(prepared) is False
    assert _validate_prepared("Tessa", beat2) == []


def test_validate_does_not_block_healable_body_staging(monkeypatch):
    from tools import kling_o3_prompt as o3p

    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    errs = o3p.validate_element_bound_voice_prompt("Arlo", BEAT24_BODY_STAGING)
    assert not any("performance staging" in e.lower() for e in errs)
    prepared = bg.prepare_kling_o3_prompt_for_submit(
        {
            "speaker": "Arlo",
            "dialogue_text": "OK, Kiddo . Lorelai's our best chance.",
        },
        BEAT24_BODY_STAGING,
    )
    assert bg.prompt_body_has_performance_staging(prepared) is False
    beat = {
        "speaker": "Arlo",
        "dialogue_text": "OK, Kiddo . Lorelai's our best chance.",
        "kling_o3_prompt": BEAT24_BODY_STAGING,
    }
    assert bg.heal_spoken_staging_in_voice_prompt(beat) is True
    assert "Faces camera" not in beat["kling_o3_prompt"]
