"""Tests for phase_a_chipper_idle_lipsync helpers."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase_a_chipper_idle_lipsync import (  # noqa: E402
    BODY_PLATE_DEFAULT,
    PHASE_A_ZOOM_END,
    PHASE_A_ZOOM_RAMP_DELAY_SEC,
    PHASE_A_ZOOM_RAMP_SEC,
    _kling_idle_duration,
    _preroll_seconds,
    resolve_body_plate,
)
from production_server import KLING_MAX_DURATION_SEC, KLING_MIN_DURATION_SEC  # noqa: E402


def test_resolve_body_plate_default(tmp_path: Path) -> None:
    plate = tmp_path / BODY_PLATE_DEFAULT
    plate.write_bytes(b"png")
    got = resolve_body_plate(tmp_path, {})
    assert got == plate


def test_resolve_body_plate_from_state(tmp_path: Path) -> None:
    plate = tmp_path / "custom_plate.png"
    plate.write_bytes(b"png")
    got = resolve_body_plate(tmp_path, {"phase_a_chipper_body_plate_file": "custom_plate.png"})
    assert got == plate


def test_kling_idle_duration_short_audio() -> None:
    assert _kling_idle_duration(1.5) == KLING_MIN_DURATION_SEC


def test_kling_idle_duration_long_audio() -> None:
    assert _kling_idle_duration(43.0) == KLING_MAX_DURATION_SEC


def test_approved_zoom_constants() -> None:
    assert PHASE_A_ZOOM_END == 1.03
    assert PHASE_A_ZOOM_RAMP_SEC == 18.0
    assert PHASE_A_ZOOM_RAMP_DELAY_SEC == 1.5
