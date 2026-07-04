"""Unit tests for beat_extract_policy cast + staging post-process."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from beat_extract_policy import (  # noqa: E402
    apply_cast_text,
    canon_plan_speaker,
    classify_beat_type,
    humanize_kling_body_parts,
    humanize_kling_body_parts_on_beat,
    normalize_plan_row,
    postprocess_beats_plan,
    postprocess_plan_result,
    repair_corrupted_plan_dialogue,
)


def test_apply_cast_text_replaces_luna_and_chipper():
    text = "Luna the Owl meets Chipper and Guide Bird at the runestone."
    out = apply_cast_text(text)
    assert "Lorelai" in out
    assert "Arlo" in out
    assert "Luna" not in out
    assert "Chipper" not in out
    assert "Guide Bird" not in out


def test_apply_cast_text_lemur_peace_prize():
    assert "Lemur Peace Prize" in apply_cast_text("She won the Owl Peace Prize!")


def test_canon_plan_speaker_legacy_aliases():
    assert canon_plan_speaker("luna") == "Lorelai"
    assert canon_plan_speaker("laurel") == "Lorelai"
    assert canon_plan_speaker("Chipper") == "Arlo"
    assert canon_plan_speaker("Guide Bird") == "Arlo"


def test_classify_beat_type_inscription_is_stage_still():
    row = {
        "beat_type": "stage_direction",
        "speaker": "[Stage Direction]",
        "dialogue_text": "",
        "scene_notes": "Inscription 1 — Feel what's real. Still insert.",
    }
    assert classify_beat_type(row) == "stage_still"


def test_classify_legacy_stage_direction_action_is_dialogue():
    row = {
        "beat_type": "stage_direction",
        "speaker": "[Stage Direction]",
        "dialogue_text": "[Cold open: baby bunny nose pokes from burrow — HICCUP]",
        "scene_notes": "",
    }
    assert classify_beat_type(row) == "dialogue"


def test_normalize_event5_legacy_beat1_coerces_to_benson_dialogue():
    row, _warnings = normalize_plan_row({
        "beat_index": 1,
        "beat_type": "stage_direction",
        "speaker": "[Stage Direction]",
        "dialogue_text": (
            "[Cold open: baby bunny nose pokes from burrow — HICCUP — eyes wide, "
            "ears shoot up, dives back. Repeats once. Physical comedy, no dialogue.]"
        ),
        "emotion": "neutral",
        "scene_notes": "",
    }, beat_index=1)
    assert row["beat_type"] == "dialogue"
    assert row["speaker"] == "Benson"
    assert "hiccup" in row["dialogue_text"].lower()
    assert "baby bunny" in row["scene_notes"].lower() or "burrow" in row["scene_notes"].lower()


def test_normalize_benson_action_script_format():
    row, _warnings = normalize_plan_row({
        "beat_index": 1,
        "beat_type": "dialogue",
        "speaker": "Benson",
        "dialogue_text": "(hiccup — nose pokes from burrow, eyes wide, dives back; repeats)",
        "emotion": "comedic, startled",
        "scene_notes": "Baby bunny at burrow lip, ears trembling.",
    }, beat_index=1)
    assert row["beat_type"] == "dialogue"
    assert row["speaker"] == "Benson"
    assert row["emotion"] == "comedic, startled"


def test_classify_beat_type_dialogue_stays_dialogue():
    row = {
        "beat_type": "dialogue",
        "speaker": "Lorelai",
        "dialogue_text": "Hello!",
        "scene_notes": "eyes widen",
    }
    assert classify_beat_type(row) == "dialogue"


def test_repair_corrupted_plan_dialogue_strips_double_bracket_prefix():
    speaker, dialogue = repair_corrupted_plan_dialogue(
        "Character [[curious, polite]]: Tessa [[curious, polite]]: Hello ...",
        "Tessa",
    )
    assert speaker == "Tessa"
    assert dialogue == "Hello ..."
    assert "[[" not in dialogue


def test_normalize_plan_row_strips_bracketed_emotion():
    row, _warnings = normalize_plan_row({
        "speaker": "Tessa",
        "dialogue_text": "Character [[curious, polite]]: Tessa [[curious, polite]]: Hello ...",
        "emotion": "[curious, polite]",
        "beat_type": "dialogue",
    }, beat_index=3)
    assert row["speaker"] == "Tessa"
    assert row["dialogue_text"] == "Hello ..."
    assert row["emotion"] == "curious, polite"


def test_normalize_plan_row_cast_and_staging_warning():
    row, warnings = normalize_plan_row({
        "speaker": "Luna",
        "dialogue_text": "Hi there",
        "emotion": "bright",
        "scene_notes": "camera zooms in as Luna walks across the room",
        "beat_type": "dialogue",
    }, beat_index=1)
    assert row["speaker"] == "Lorelai"
    assert row["beat_type"] == "dialogue"
    assert any("banned staging" in w for w in warnings)


def test_postprocess_beats_plan_reindexes_and_casts():
    rows, warnings = postprocess_beats_plan([
        {"speaker": "Luna", "dialogue_text": "Hi", "beat_index": 5},
        {"speaker": "Chipper", "dialogue_text": "Hey", "beat_index": 2},
    ])
    assert [r["beat_index"] for r in rows] == [1, 2]
    assert rows[0]["speaker"] == "Lorelai"
    assert rows[1]["speaker"] == "Arlo"
    assert isinstance(warnings, list)


def test_postprocess_plan_result_includes_staging_warnings():
    result = postprocess_plan_result(
        {
            "story_summary": "Luna discovers the MindfulNest with Chipper.",
            "beats_plan": [{
                "speaker": "Luna",
                "dialogue_text": "Wow!",
                "scene_notes": "smile",
                "beat_type": "dialogue",
            }],
        },
        {"arc_number": 1, "event_id": "2", "phase": "pre"},
    )
    assert "Lorelai" in result["story_summary"]
    assert "Chipper" not in result["story_summary"]
    assert result["cast_policy"] == "Lorelai+Arlo (Luna/Chipper retired)"
    assert "staging_warnings" in result
    assert result["gold_reference_used"] is True


def test_humanize_kling_body_parts_flipper_and_paw():
    assert "one hand" in humanize_kling_body_parts(
        "one flipper rises in a gentle wave", speaker="Tessa",
    )
    assert "one hand" in humanize_kling_body_parts(
        "one paw holds a rolled map", speaker="Lorelai",
    )


def test_normalize_identity_footer_canonicalizes_after_humanize_drift():
    import beat_generator as bg

    drifted = humanize_kling_body_parts(
        "Match @Image1 character appearance, proportions, shell, flippers, and facial expression",
        speaker="Tessa",
    )
    assert "hands" in drifted
    fixed = bg.normalize_kling_o3_identity_footer(drifted)
    assert fixed == bg.KLING_O3_IDENTITY_LOCK
    assert "flipper" not in fixed.lower()
    assert "shell" not in fixed.lower()


def test_humanize_kling_body_parts_keeps_tail_and_shell():
    text = "small sheepish shrug of one hand on her shell, tail still"
    out = humanize_kling_body_parts(
        "small sheepish shrug of one flipper on her shell, tail still",
        speaker="Tessa",
    )
    assert out == text


def test_humanize_kling_body_parts_skips_bird_speakers():
    raw = "subtle wing-flutter at chest level"
    assert humanize_kling_body_parts(raw, speaker="Chipper") == raw


def test_normalize_plan_row_humanizes_scene_notes():
    row, _ = normalize_plan_row({
        "speaker": "Tessa",
        "dialogue_text": "Hello",
        "emotion": "polite",
        "scene_notes": "one flipper rises in a small gentle wave",
        "beat_type": "dialogue",
    }, beat_index=2)
    assert "flipper" not in row["scene_notes"].lower()
    assert "hand" in row["scene_notes"].lower()


def test_normalize_plan_row_strips_kling_boilerplate_from_scene_notes():
    dialogue = (
        "Oh! Hello there. Good ta meet ya. I'm Bramble — from HoneyPot. "
        "I was just looking for a spot to take my cubs camping."
    )
    bloated = (
        "@Image1 (Bramble). Scene from @Image2. Bramble stands near the MindfulNest ruins, "
        "extending one large hand outward in a friendly shake gesture, a broad grin spreading "
        "across his face. Voice line: Bramble speaks in a warm, jovial rumble: [delighted] "
        f"\"Oh! Hello there. Good ta meet ya. [pause] I'm Bramble — from HoneyPot. "
        "I was just looking for a spot to take my cubs camping.\" "
        "Children's illustrated fantasy storybook style."
    )
    row, _ = normalize_plan_row({
        "speaker": "Bramble",
        "dialogue_text": dialogue,
        "emotion": "delighted, easygoing",
        "scene_notes": bloated,
        "beat_type": "dialogue",
    }, beat_index=3)
    assert "Voice line:" not in row["scene_notes"]
    assert "@Image1" not in row["scene_notes"]
    assert "storybook style" not in row["scene_notes"].lower()
    assert dialogue not in row["scene_notes"]
    assert "friendly shake gesture" in row["scene_notes"].lower()


def test_humanize_kling_body_parts_on_beat_sidecar_fields():
    beat = {
        "speaker": "Tessa",
        "dialogue_text": "[one flipper wave]",
        "scene_notes": "one flipper rises",
        "kling_o3_prompt": "small front flippers and one flipper rising",
    }
    assert humanize_kling_body_parts_on_beat(beat) is True
    assert "flipper" not in beat["kling_o3_prompt"].lower()
    assert humanize_kling_body_parts_on_beat(beat) is False


def test_beat_continuity_reaction_first_injects_prompt():
    from beat_extract_policy import apply_beat_continuity_chain

    beats = [
        {
            "speaker": "Lorelai",
            "dialogue_text": "Oh! Hi! Who are you three?",
            "emotion": "excited",
            "beat_type": "dialogue",
            "kling_o3_prompt": "@Image1 (Loral) reacts. Scene from @Image2.\n\nLine.",
        },
        {
            "speaker": "Tessa",
            "dialogue_text": "Oh, hello. I'm Tessa.",
            "emotion": "neutral",
            "beat_type": "dialogue",
            "kling_o3_prompt": "@Image1 (Tessa) listens. Scene from @Image2.\n\nLine.",
        },
    ]
    apply_beat_continuity_chain(beats)
    assert beats[1].get("beat_continuity_v1") == "BEAT_CONTINUITY_V1"
    assert "Continuity:" in beats[1]["kling_o3_prompt"]
    assert "Before speaking, Tessa" in beats[1]["kling_o3_prompt"]
    assert "Who are you" not in beats[1]["kling_o3_prompt"]
    assert "has just heard" not in beats[1]["kling_o3_prompt"]
    assert beats[1]["emotion"] != "neutral"


def test_build_beats_from_approved_plan_applies_continuity():
    import beat_generator as bg

    plan = [
        {
            "beat_index": 1,
            "speaker": "Lorelai",
            "dialogue_text": "Hello there?",
            "emotion": "curious",
            "beat_type": "dialogue",
            "scene_notes": "waves",
        },
        {
            "beat_index": 2,
            "speaker": "Tessa",
            "dialogue_text": "Hi, I'm Tessa.",
            "emotion": "neutral",
            "beat_type": "dialogue",
            "scene_notes": "smiles",
        },
    ]
    prompts = {
        1: '@Image1 (Loral) waves. Scene from @Image2.\n\nLoral speaks: "Hello there?"',
        2: '@Image1 (Tessa) smiles. Scene from @Image2.\n\nTessa speaks: "Hi, I\'m Tessa."',
    }
    beats = bg.build_beats_from_approved_plan(
        plan, prompts, arc_number=1, event_id="2", phase="pre",
    )
    assert len(beats) == 2
    assert beats[1].get("kling_o3_prior_beat_context")
    assert "Before speaking, Tessa" in beats[1]["kling_o3_prompt"]
    assert "Hello there" not in beats[1]["kling_o3_prompt"]


def test_strip_auto_injected_continuity_blocks_single_quote_variant():
    from beat_extract_policy import strip_auto_injected_continuity_blocks

    auto = (
        "Continuity: Oliver has just heard Loral say: 'Who are you?' (do not repeat the line). "
        "Before speaking, Oliver shows a brief natural reaction (curious, attentive) — "
        "a nod, glance, or listening beat — then delivers the line."
    )
    prompt = f"@Image1 (Oliver). Scene from @Image2.\n\n{auto}\n\nOliver speaks: \"Hi.\""
    assert strip_auto_injected_continuity_blocks(prompt).count("Continuity:") == 0
    action_auto = "Continuity: Before speaking, Oliver nods, then delivers the line."
    prompt2 = f"@Image1 (Oliver). Scene from @Image2.\n\n{action_auto}\n\nOliver speaks: \"Hi.\""
    assert strip_auto_injected_continuity_blocks(prompt2).count("Continuity:") == 0
    from beat_extract_policy import strip_auto_injected_continuity_blocks

    auto = (
        'Continuity: Oliver has just heard Loral say: "Hello.". '
        "Before speaking, Oliver shows a brief natural reaction (attentive) — "
        "a nod, glance, or listening beat — then delivers the line."
    )
    prompt = (
        "@Image1 (Oliver). Scene from @Image2.\n\n"
        f"{auto}\n\n{auto}\n\n"
        "Oliver speaks: \"Hi.\""
    )
    cleaned = strip_auto_injected_continuity_blocks(prompt)
    assert cleaned.count("Continuity:") == 0
    assert "Oliver speaks" in cleaned


def test_apply_beat_continuity_chain_idempotent_no_stack():
    from beat_extract_policy import apply_beat_continuity_chain

    beats = [
        {
            "speaker": "Oliver",
            "dialogue_text": "You did it.",
            "kling_o3_prompt": (
                '@Image1 (Oliver). Scene from @Image2.\n\n'
                'Oliver speaks: "You did it."'
            ),
        },
        {
            "speaker": "Lorelai",
            "dialogue_text": "Who are you?",
            "kling_o3_prompt": '@Image1 (Loral). Scene from @Image2.\n\nLoral speaks: "Who?"',
        },
    ]
    apply_beat_continuity_chain(beats)
    once = beats[1]["kling_o3_prompt"]
    apply_beat_continuity_chain(beats)
    twice = beats[1]["kling_o3_prompt"]
    assert once.count("Continuity:") == 1
    assert twice.count("Continuity:") == 1
    assert "Before speaking, Loral" in twice
    assert "You did it" not in twice


def test_apply_beat_continuity_chain_skips_prompt_box_law_and_strips_stack():
    from beat_extract_policy import apply_beat_continuity_chain

    auto = (
        'Continuity: Oliver has just heard Loral say: "You did it.". '
        "Before speaking, Oliver shows a brief natural reaction (attentive) — "
        "a nod, glance, or listening beat — then delivers the line."
    )
    beats = [
        {
            "speaker": "Lorelai",
            "dialogue_text": "Hello?",
            "kling_o3_prompt": '@Image1 (Loral). Scene from @Image2.\n\nLoral speaks: "Hello?"',
        },
        {
            "speaker": "Oliver",
            "dialogue_text": "I am Oliver.",
            "o3_prompt_box_law": True,
            "kling_o3_prior_beat_context": auto,
            "beat_continuity_v1": "BEAT_CONTINUITY_V1",
            "kling_o3_prompt": (
                "@Image1 (Oliver). Scene from @Image2.\n\n"
                f"{auto}\n\n{auto}\n\n"
                'Oliver speaks: "I am Oliver."'
            ),
        },
    ]
    apply_beat_continuity_chain(beats)
    b2 = beats[1]
    assert b2["kling_o3_prompt"].count("Continuity:") == 0
    assert "kling_o3_prior_beat_context" not in b2
    assert "beat_continuity_v1" not in b2


def test_apply_beat_continuity_chain_skips_operator_scene_continuity():
    from beat_extract_policy import apply_beat_continuity_chain

    beats = [
        {
            "speaker": "Oliver",
            "dialogue_text": "You did it.",
            "kling_o3_prompt": '@Image1 (Oliver). Scene from @Image2.\n\nOliver speaks: "You did it."',
        },
        {
            "speaker": "Lorelai",
            "dialogue_text": "Hello ... Who are you?",
            "kling_o3_prompt": (
                "@Image1 (Loral) Continuity: Loral has just witnessed an unexpected stranger "
                "entering (off screen).\n\n"
                "Loral — Lorelai — Loral tilts her head. Scene from @Image2.\n\n"
                'Loral speaks: "Hello ... Who are you?"'
            ),
        },
    ]
    apply_beat_continuity_chain(beats)
    prompt = beats[1]["kling_o3_prompt"]
    assert prompt.count("Continuity:") == 1
    assert "witnessed an unexpected stranger" in prompt
    assert "has just heard" not in prompt


def test_build_reaction_first_context_block_action_only_no_prior_quote():
    from beat_extract_policy import build_reaction_first_context_block

    prior = {
        "speaker": "Lorelai",
        "dialogue_text": "You did it. I can't believe you actually did it.",
        "kling_o3_prompt": (
            "@Image1 (Loral). Scene from @Image2.\n\n"
            'Loral speaks: "Hello ... Who are you?"'
        ),
    }
    current = {"speaker": "Oliver", "dialogue_text": "I am Oliver."}
    block = build_reaction_first_context_block(prior, current)
    assert block is not None
    assert block.startswith("Continuity: Before speaking, Oliver")
    assert "then delivers the line." in block
    assert "Hello" not in block
    assert "You did it" not in block
    assert "has just heard" not in block


def test_normalize_canonical_prompt_vocabulary_rune_stone_dash():
    import kling_o3_prompt as o3p

    assert o3p.normalize_canonical_prompt_vocabulary(
        "You woke up a runestone near the runestones.",
    ) == "You woke up a rune-stone near the rune-stones."
    assert o3p.normalize_canonical_prompt_vocabulary(
        "The Rune Stones have been dark.",
    ) == "The rune-stones have been dark."
