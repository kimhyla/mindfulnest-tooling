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


def test_phase_b_module_lipsync_uses_voice_first_delivery_profile():
    phases = Path(__file__).resolve().parent.parent / "server_handlers" / "phases.py"
    text = phases.read_text(encoding="utf-8")
    block = text.split("def _write_phase_b_lipsync_complete", 1)[1].split("\ndef ", 1)[0]
    assert "finalize_phase_module_lipsync_delivery" in block
    delivery = Path(__file__).resolve().parent.parent / "phase_module_lipsync_delivery.py"
    assert 'PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE = "voice_first_upscale"' in delivery.read_text(encoding="utf-8")


def test_voice_first_delivery_has_cap_stepdown_attempts():
    from video_delivery import _delivery_encode_attempts  # noqa: PLC0415

    attempts = _delivery_encode_attempts("voice_first_upscale", sharpen=True)
    assert len(attempts) >= 2
    bitrates = [a[1] for a in attempts]
    assert "1850k" in bitrates
    assert "1500k" in bitrates


def test_element_native_still_uses_standard_delivery_profile():
    pipeline = Path(__file__).resolve().parent.parent / "kling_o3_element_beat_pipeline.py"
    text = pipeline.read_text(encoding="utf-8")
    assert 'delivery_profile="voice_first_upscale"' not in text
    assert "encode_delivery_video(master, delivery" in text


def test_beat_avatar_pro_uses_phase_module_delivery_choke_point():
    avatar = Path(__file__).resolve().parent.parent / "beat_avatar_lipsync.py"
    text = avatar.read_text(encoding="utf-8")
    block = text.split("def encode_avatar_pro_delivery", 1)[1].split("\ndef ", 1)[0]
    assert "finalize_phase_module_lipsync_delivery" in block
    assert "sharpen=True" in block
