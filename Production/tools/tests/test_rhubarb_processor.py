"""Tests for rhubarb_processor phoneme lookup and sprite resolution."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rhubarb_processor import (  # noqa: E402
    lookup_phoneme,
    resolve_phoneme_sprite,
)


def test_lookup_phoneme_at_boundary() -> None:
    cues = [{"start": 0.0, "end": 0.5, "value": "B"}, {"start": 0.5, "end": 1.0, "value": "D"}]
    assert lookup_phoneme(cues, 0.0) == "B"
    assert lookup_phoneme(cues, 0.49) == "B"
    assert lookup_phoneme(cues, 0.5) == "D"
    assert lookup_phoneme(cues, -0.1) == "X"
    assert lookup_phoneme(cues, 1.5) == "X"


def test_lookup_phoneme_empty() -> None:
    assert lookup_phoneme([], 0.0) == "X"


def test_resolve_phoneme_sprite_x_to_a(tmp_path: Path) -> None:
    a = tmp_path / "chipper_beak_A.png"
    a.write_bytes(b"x")
    sprites = {"A": a}
    got = resolve_phoneme_sprite("X", sprites)
    assert got == a


def test_resolve_phoneme_sprite_g_to_c(tmp_path: Path) -> None:
    c = tmp_path / "chipper_beak_C.png"
    c.write_bytes(b"x")
    sprites = {"C": c}
    assert resolve_phoneme_sprite("G", sprites) == c


def test_run_rhubarb_integration() -> None:
    """Run Rhubarb on Phase A voice stem if binary + audio exist."""
    from rhubarb_processor import default_rhubarb_bin, run_rhubarb

    rhubarb = default_rhubarb_bin()
    if not Path(rhubarb).is_file():
        pytest.skip("rhubarb binary not installed")

    dropbox = Path.home() / (
        "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1"
    )
    stems = sorted(dropbox.glob("phase_a_voice_stem_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not stems:
        pytest.skip("no phase_a_voice_stem in Dropbox")

    cues = run_rhubarb(stems[0], rhubarb_bin=rhubarb)
    assert len(cues) > 10
    assert all("start" in c and "end" in c and "value" in c for c in cues)
