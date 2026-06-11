"""Intro export: slow fades on last two intro boundaries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def test_intro_export_pair_fades_on_last_two_boundaries():
    assert bg._intro_export_pair_fades(1, 1500, 2800) == []
    assert bg._intro_export_pair_fades(2, 1500, 2800) == [2800]
    assert bg._intro_export_pair_fades(3, 1500, 2800) == [1500, 2800]
    assert bg._intro_export_pair_fades(10, 1500, 2800) == [
        0, 0, 0, 0, 0, 0, 0, 1500, 2800,
    ]
    assert bg._intro_export_pair_fades(5, 0, 0) == []


def test_load_intro_pair_fade_ms_defaults():
    assert bg._load_intro_pre_penultimate_pair_fade_ms() >= 1000
    assert bg._load_intro_final_pair_fade_ms() >= 2000


def test_intro_visual_fade_shorter_than_pair_budget():
    assert bg._intro_visual_fade_out_s(1500) == pytest.approx(0.6)
    assert bg._intro_visual_fade_in_s(2800) == pytest.approx(0.6)
    assert bg._intro_visual_fade_out_s(0) == 0.0


def test_stitch_slot_mapping():
    assert bg.stitch_slot_for_bg_phase("pre") == "intro"
    assert bg.stitch_slot_for_bg_phase("post") == "resolution"
    assert bg.stitch_slot_for_bg_phase("phase_a") == "phase_a"
    assert bg.resolve_bg_export_stitch_slot(phase="full", video_role="intro") == "intro"
