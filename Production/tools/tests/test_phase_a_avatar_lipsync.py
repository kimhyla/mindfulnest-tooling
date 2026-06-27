"""Phase A Avatar Pro contract tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from phase_a_arlo_contract import PHASE_A_ARLO_CANONICAL_STILL_REL
from phase_a_avatar_lipsync import (
    ARLO_WIZARD_DESK_PROMPT,
    AVATAR_USD_PER_SEC,
    PHASE_A_AVATAR_ROUTE_CODE,
    PHASE_A_LIPSYNC_METHOD_AVATAR,
    PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
    estimate_avatar_pro_usd,
    resolve_phase_a_arlo_avatar_still,
)


def test_estimate_avatar_pro_usd_matches_measured_job():
    # Event_2 probe: $1.12 / ~10s stem slice
    assert AVATAR_USD_PER_SEC == pytest.approx(0.1122, rel=1e-3)
    assert estimate_avatar_pro_usd(10.0) == pytest.approx(1.12, rel=0.02)
    assert estimate_avatar_pro_usd(23.0) == pytest.approx(2.58, rel=0.02)


def test_resolve_phase_a_arlo_avatar_still(tmp_path: Path):
    prod = tmp_path / "Production"
    still = prod / PHASE_A_ARLO_CANONICAL_STILL_REL
    still.parent.mkdir(parents=True, exist_ok=True)
    still.write_bytes(b"\x89PNG\r\n\x1a\n")
    event = prod / "Event_TEST"
    event.mkdir(parents=True)
    got = resolve_phase_a_arlo_avatar_still(event, prod)
    assert got == still.resolve()


def test_resolve_phase_a_arlo_avatar_still_missing(tmp_path: Path):
    prod = tmp_path / "Production"
    event = prod / "Event_TEST"
    event.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        resolve_phase_a_arlo_avatar_still(event, prod)


def test_phase_a_lipsync_method_constant():
    assert PHASE_A_LIPSYNC_METHOD_AVATAR == "kling_avatar_pro_v1"
    assert PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM == "single_full_stem_v1"
    assert PHASE_A_AVATAR_ROUTE_CODE == "PHASE_A_SINGLE_SHOT_STATIC_BG_V1"


def test_arlo_wizard_desk_prompt_frozen_bg():
    assert "TRIPOD LOCK" in ARLO_WIZARD_DESK_PROMPT
    assert "Arlo" in ARLO_WIZARD_DESK_PROMPT
    assert "static camera" in ARLO_WIZARD_DESK_PROMPT.lower()
