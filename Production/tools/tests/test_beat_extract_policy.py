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
