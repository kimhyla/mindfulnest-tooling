"""Phase A Arlo idle still resolution — blocks BACKGROUND folder mistakes."""
from __future__ import annotations

from pathlib import Path

import pytest

from phase_a_arlo_contract import (
    PHASE_A_ARLO_CANONICAL_STILL_REL,
    validate_phase_a_arlo_idle_still_path,
)


def test_arlo_lipsync_base_has_no_background_still_candidate() -> None:
    src = Path(__file__).resolve().parent.parent / "phase_a_arlo_lipsync_base.py"
    text = src.read_text(encoding="utf-8")
    assert "BACKGROUND" not in text
    assert "resolve_phase_a_arlo_idle_still" in text


def test_reject_background_folder_still(tmp_path: Path) -> None:
    bg = tmp_path / "NEW STYLE CHARACTERS" / "BACKGROUND"
    bg.mkdir(parents=True)
    wrong = bg / "ChatGPT Image Jun 21, 2026, 10_34_39 AM.png"
    wrong.write_bytes(b"png")
    with pytest.raises(ValueError, match="BACKGROUND"):
        validate_phase_a_arlo_idle_still_path(wrong)


def test_canonical_still_rel_is_arlo_folder() -> None:
    assert "ARLO" in PHASE_A_ARLO_CANONICAL_STILL_REL
    assert "BACKGROUND" not in PHASE_A_ARLO_CANONICAL_STILL_REL
    assert "01_12_53" in PHASE_A_ARLO_CANONICAL_STILL_REL
