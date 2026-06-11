"""Regression gates for Kling LipSync input resolution.

Kling LipSync exposes no output-resolution parameter in the WaveSpeed wrapper.
Repeated provider smokes returned 832x464 even from 1080p input, so Beat Gen
must submit the best available 1920x1080 lipsync source and still reject any
sub-720p output before kid-facing delivery.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import video_delivery

TOOLS = Path(__file__).resolve().parent.parent


def test_lipsync_input_uses_1080p_source_but_delivery_stays_720p() -> None:
    assert video_delivery.DELIVERY_WIDTH == 1280
    assert video_delivery.DELIVERY_HEIGHT == 720
    assert video_delivery.LIPSYNC_INPUT_WIDTH == 1920
    assert video_delivery.LIPSYNC_INPUT_HEIGHT == 1080


def test_lipsync_encoder_does_not_reuse_delivery_profile() -> None:
    src = inspect.getsource(video_delivery.encode_lipsync_input)
    assert "LIPSYNC_INPUT_WIDTH" in src
    assert "LIPSYNC_INPUT_HEIGHT" in src
    assert "encode_delivery_video(src, dst" not in src
    assert "Kling LipSync exposes no output-resolution parameter" in src
    assert "require the post-lipsync >=720p quality gate" in src


def test_arlo_pipeline_records_lipsync_input_profile_metadata() -> None:
    pipeline_src = (TOOLS / "arlo_o3_voice_pipeline.py").read_text(encoding="utf-8")
    assert "kling_o3_voice_fix_lipsync_input_profile" in pipeline_src
    assert '"resolution": "1920x1080"' in pipeline_src
    assert "Kling LipSync has no resolution parameter" in pipeline_src
    assert "reject any sub-720p provider output" in pipeline_src
