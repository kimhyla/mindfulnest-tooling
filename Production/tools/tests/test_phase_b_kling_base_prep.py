"""PHASE_B_KLING_CROSSFADE_LOOP_V1 — short Cedric base must loop before Kling submit."""
from __future__ import annotations

from pathlib import Path

import phase_b_kling_base_prep as prep


def test_kling_submit_bitrate_fits_22mb_for_two_minute_loop():
    bps = prep.kling_submit_video_bitrate_bps(125.0)
    implied_mb = bps * 125.0 / 8 / 1024 / 1024
    assert implied_mb <= prep.WAVESPEED_RAW_MB_CEILING


def test_phases_handler_uses_kling_base_loop_not_avatar_pro():
    src = Path(__file__).resolve().parent.parent / "server_handlers" / "phases.py"
    block = src.read_text(encoding="utf-8").split("def handle_phase_b_lipsync", 1)[1]
    block = block.split("\ndef _write_phase_b_lipsync_complete", 1)[0]
    assert "submit_avatar_pro" not in block
    assert "prep_phase_b_kling_base_video" in block
    assert "LipSyncClient" in block


def test_prep_module_exports_code_constant():
    assert prep._PREP_CODE == "PHASE_B_KLING_CROSSFADE_LOOP_V1"
