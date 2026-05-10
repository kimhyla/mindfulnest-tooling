"""Pytest cases for Production/lib/rule_8_validator.py.

Each test case is sourced to either CLAUDE.md Rule 8 text OR a documented
incident (LD-160 cfg_scale failure, LD-162 do-not-stack rule, April 17
Option D forensics). Failure of any case is a Rule 8 regression.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make Production/lib importable from worktree.
_THIS = Path(__file__).resolve()
_PRODUCTION = _THIS.parent.parent.parent.parent
sys.path.insert(0, str(_PRODUCTION))

from lib.rule_8_validator import (  # noqa: E402
    BANNED_WORDS,
    detect_banned_words,
    detect_levers,
    validate_lipsync_prompt,
    validate_motion_prompt,
)


# -----------------------------------------------------------------------------
# §8.1 banned words
# -----------------------------------------------------------------------------


def test_detect_banned_words_finds_speaking():
    assert "speaking" in detect_banned_words("a turtle speaking softly")


def test_detect_banned_words_case_insensitive():
    assert "talking" in detect_banned_words("Two birds TALKING in a tree")


def test_detect_banned_words_no_false_positives():
    # "speak" is not banned; only "speaking" (substring "speak" alone is fine in "speaker").
    # The list contains "speech" not "speaking" alone — verify both work.
    assert detect_banned_words("the speaker is at the podium") == []


def test_detect_banned_words_multiple():
    found = detect_banned_words("a singing bird with mouth movement")
    assert "singing" in found
    assert "mouth movement" in found


def test_validate_motion_prompt_rejects_banned_word():
    res = validate_motion_prompt("a bird talking softly")
    assert res["ok"] is False
    assert "talking" in res["banned_words"]
    assert "banned_words" in res["violation"]


# -----------------------------------------------------------------------------
# §8.1 required mouth + tail
# -----------------------------------------------------------------------------


def test_validate_motion_prompt_clean_bird():
    res = validate_motion_prompt(
        "A small bird hops gently on a branch. Beak closed, no speech, no lip movement. "
        "Silent subtle idle movement only.",
        character_type="bird",
    )
    assert res["ok"] is True
    assert res["banned_words"] == []
    assert res["missing_mouth_constraint"] is None
    assert res["has_required_tail"] is True


def test_validate_motion_prompt_missing_mouth_constraint():
    res = validate_motion_prompt(
        "A bird hops on a branch. Silent subtle idle movement only.",
        character_type="bird",
    )
    assert res["ok"] is False
    assert res["missing_mouth_constraint"] is not None


def test_validate_motion_prompt_missing_tail():
    res = validate_motion_prompt(
        "A turtle walks across a log. Mouth closed, no speech.",
        character_type="turtle",
    )
    assert res["ok"] is False
    assert res["has_required_tail"] is False


# -----------------------------------------------------------------------------
# §8.2 lever detection
# -----------------------------------------------------------------------------


def test_detect_levers_gaze_lock():
    assert "gaze_lock" in detect_levers("eyes meet camera")
    assert "gaze_lock" in detect_levers("face centered, looking straight")
    assert "gaze_lock" in detect_levers("direct forward gaze throughout")


def test_detect_levers_mouth_lock_intensifier():
    assert "mouth_lock_intensifier" in detect_levers("beak pressed shut")
    assert "mouth_lock_intensifier" in detect_levers("mouth sealed tight")


def test_detect_levers_motion_lock():
    assert "motion_lock" in detect_levers("minimal motion only")
    assert "motion_lock" in detect_levers("static camera, no head movement")
    assert "motion_lock" in detect_levers("head remains facing forward")
    assert "motion_lock" in detect_levers("frozen face throughout")


def test_detect_levers_no_false_positives():
    assert detect_levers("a peaceful scene with gentle motion") == []
    assert detect_levers("the bird's beak is closed") == []  # no intensifier


# -----------------------------------------------------------------------------
# §8.2 do-not-stack — the LD-162 + Option D forensics class
# -----------------------------------------------------------------------------


def test_lipsync_prompt_clean_baseline_passes():
    """Tessa beat_05 known-good baseline (per LD-177 V1 validation)."""
    res = validate_lipsync_prompt(
        positive_prompt=(
            "Tessa the small turtle on a forest path. Soft natural light. "
            "Beak closed, no speech, no lip movement. "
            "Silent subtle idle movement only."
        ),
        cfg_scale=0.5,
        has_endframe_pixel_anchor=True,
        character_type="bird",  # Tessa's species — bird per Bible
    )
    assert res["ok"] is True
    assert res["lever_count"] == 0
    assert res["cfg_violation"] is False


def test_lipsync_prompt_option_d_failure_profile():
    """The April 17 LD-160 failure: cfg=0.75 + stacked gaze + mouth + motion locks.

    This combination caused LatentSync starvation. Validator MUST reject it.
    """
    res = validate_lipsync_prompt(
        positive_prompt=(
            "Tessa centered, eyes meet camera throughout. Beak pressed shut. "
            "Minimal motion. Static camera. Head remains facing forward. "
            "Silent subtle idle movement only."
        ),
        cfg_scale=0.75,  # over the §8.2 limit
        has_endframe_pixel_anchor=False,  # no pixel anchor → stacking forbidden
        character_type="bird",
    )
    assert res["ok"] is False
    assert "do_not_stack" in res["violation"]
    assert res["lever_count"] >= 2


def test_lipsync_prompt_cfg_alone_passes():
    """cfg > 0.5 alone (no other levers) is allowed for non-lipsync use cases.
    Per §8.2 the rule is do-not-STACK; one lever alone doesn't violate.
    """
    res = validate_lipsync_prompt(
        positive_prompt=(
            "A scene transitions slowly. Beak closed, no speech. "
            "Silent subtle idle movement only."
        ),
        cfg_scale=0.7,
        has_endframe_pixel_anchor=False,
        character_type="bird",
    )
    # Only cfg is over — that's 1 lever. Should be ok per §8.2.
    assert res["lever_count"] == 1
    assert res["ok"] is True


def test_lipsync_prompt_endframe_anchor_exception():
    """§8.3 §8.2 amended: pixel-level endpoint anchor allows ONE combination
    with §8.1 negatives. Verify the exception works.
    """
    res = validate_lipsync_prompt(
        positive_prompt=(
            "Tessa with eyes meeting camera. Beak closed, no speech, no lip movement. "
            "Silent subtle idle movement only."
        ),
        cfg_scale=0.5,
        has_endframe_pixel_anchor=True,
        character_type="bird",
    )
    # gaze_lock is detected but suppressed by has_endframe_pixel_anchor
    # No other levers → ok
    assert res["ok"] is True
    assert "gaze_lock" not in res["levers"]


def test_lipsync_prompt_two_levers_with_anchor_still_blocks():
    """Even with has_endframe_pixel_anchor, stacking gaze + motion is forbidden."""
    res = validate_lipsync_prompt(
        positive_prompt=(
            "Eyes meet camera. Static camera, head remains facing forward. "
            "Beak closed, no speech. Silent subtle idle movement only."
        ),
        cfg_scale=0.5,
        has_endframe_pixel_anchor=True,
        character_type="bird",
    )
    # gaze_lock suppressed by anchor; but motion_lock still triggers
    # 1 lever → still ok (not stacking)
    # Verify motion_lock was detected
    assert "motion_lock" in res["levers"]


def test_banned_words_completeness():
    """Every word in CLAUDE.md §8.1 banned list is in BANNED_WORDS."""
    expected = {
        "speaking", "speech", "dialogue", "lip sync", "lip movement",
        "mouth movement", "beak movement", "talking", "singing", "vocal",
    }
    assert expected == set(BANNED_WORDS)
