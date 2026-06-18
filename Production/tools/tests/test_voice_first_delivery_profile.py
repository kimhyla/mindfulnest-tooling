"""Voice-first delivery encode — lanczos upscale + full LD-296 bitrate budget."""
from __future__ import annotations

from pathlib import Path

import video_delivery as vd


def test_voice_first_profile_uses_lanczos_and_full_bitrate_budget():
    src = Path(__file__).resolve().parent.parent / "video_delivery.py"
    text = src.read_text(encoding="utf-8")
    assert "voice_first_upscale" in text
    assert "flags=lanczos" in text
    assert vd.VOICE_FIRST_DELIVERY_MAXRATE == "1900k"
    assert vd.VOICE_FIRST_DELIVERY_VIDEO_BITRATE == "1850k"


def test_arlo_pipeline_requests_voice_first_delivery_profile():
    pipeline = Path(__file__).resolve().parent.parent / "arlo_o3_voice_pipeline.py"
    text = pipeline.read_text(encoding="utf-8")
    assert 'delivery_profile="voice_first_upscale"' in text


def test_element_native_still_uses_standard_delivery_profile():
    pipeline = Path(__file__).resolve().parent.parent / "kling_o3_element_beat_pipeline.py"
    text = pipeline.read_text(encoding="utf-8")
    assert 'delivery_profile="voice_first_upscale"' not in text
    assert "encode_delivery_video(master, delivery" in text
