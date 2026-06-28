"""Pre-submit prompt contradiction gate — verbatim box law + operator safety."""
from __future__ import annotations

import beat_generator as bg

EVENT3_LORAL_CONTRADICTORY = (
    "@Image1 (Loral). Scene from @Image2.\n\n"
    "Camera: static locked shot. The background is stable. No flowers. "
    "Nothing additional is added.\n\n"
    'Loral speaks: "I can\'t believe this."\n\n'
    "Children's illustrated fantasy storybook style, warm gold magical light, "
    "blooming Sweetroses in background.\n\n"
    "Loral stands wide-eyed, Sweetrose wreath visible behind her."
)

EVENT3_LORAL_CLEAN = (
    "@Image1 (Loral). Scene from @Image2.\n\n"
    "Camera: static locked shot. The background is stable. No flowers. "
    "Nothing additional is added.\n\n"
    'Loral speaks: "I can\'t believe this."\n\n'
    "Children's illustrated fantasy storybook style, warm gold magical light.\n\n"
    "Loral stands wide-eyed, glowing Rune-Stone visible behind her."
)


def test_lint_event3_loral_contradiction_fixture():
    warnings = bg.lint_kling_o3_prompt_contradictions(EVENT3_LORAL_CONTRADICTORY)
    assert warnings
    assert any("No flowers" in w for w in warnings)


def test_lint_clean_prompt_passes():
    assert bg.lint_kling_o3_prompt_contradictions(EVENT3_LORAL_CLEAN) == []


def test_validate_o3_submit_blocks_contradiction():
    ok, code, msg = bg.validate_o3_submit_prompt_for_mode(
        EVENT3_LORAL_CONTRADICTORY,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert not ok
    assert code == "PROMPT_SELF_CONTRADICTORY"
    assert "No flowers" in msg


def test_validate_o3_submit_allows_clean():
    ok, code, _msg = bg.validate_o3_submit_prompt_for_mode(
        EVENT3_LORAL_CLEAN,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
    )
    assert ok
    assert code == ""
