"""Canonical smooth Ken Burns — all still-insert paths must share one filter."""
from __future__ import annotations

import beat_generator as bg
import ken_burns_render as kb


def test_ken_burns_smooth_vf_no_zoompan():
    vf = kb.ken_burns_smooth_vf(
        zoom_start=1.0,
        zoom_end=kb.DEFAULT_KEN_BURNS_ZOOM_END,
        duration_s=5.0,
    )
    assert "zoompan" not in vf
    assert "flags=lanczos" in vf
    assert "scale=3840:2160" in vf
    assert "min(t/5.000000,1)" in vf


def test_beat_generator_wrapper_delegates_to_canonical_module():
    vf = bg._ken_burns_zoompan_vf(
        pan_x_pct=50,
        pan_y_pct=50,
        zoom_start=1.0,
        zoom_end=1.06,
        total_frames=120,
        fps=24,
        duration_s=5.0,
    )
    assert "zoompan" not in vf
    assert "scale=1280:720" in vf


def test_still_insert_default_zoom_end_matches_canonical():
    assert kb.DEFAULT_KEN_BURNS_ZOOM_END == 1.06
