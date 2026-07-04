"""Phase B module lipsync delivery encode — category parity with beat lipsync."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from phase_module_lipsync_delivery import (  # noqa: E402
    PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT,
    PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT,
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3,
    PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH,
    finalize_phase_module_lipsync_delivery,
)


def test_phase_module_lipsync_delivery_constants():
    assert PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE == "voice_first_upscale"
    assert PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3 == "PHASE_MODULE_LIPSYNC_DELIVERY_V3"
    assert PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT == PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3
    assert PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH == 1280
    assert PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT == 720


def test_adaptive_sacrifice_detects_arlo_probe_subtitle_band():
    from phase_module_lipsync_delivery import resolve_module_lipsync_sacrifice_ratio

    raw = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production/Event_4/"
        "phase_a_probe3s_20260630-170636_RAW_wavespeed.mp4"
    )
    if not raw.is_file():
        pytest.skip("Event_4 Arlo probe raw not on disk")
    ratio, source, band_top = resolve_module_lipsync_sacrifice_ratio(raw, 1072, ss=1.5)
    assert source == "adaptive_band"
    assert band_top is not None
    assert ratio > 0.12
    assert ratio <= 0.30


def test_adaptive_band_active_h_uses_band_top_not_capped_ratio():
    from phase_module_lipsync_delivery import (
        PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_EXTRA_SAFETY_PX,
        PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_PAD_PX,
        plan_module_lipsync_reframe_v3,
    )

    raw = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production/Event_3/"
        "phase_b_lipsync_20260627-175211.mp4"
    )
    if not raw.is_file():
        pytest.skip("Event_3 Phase B lipsync not on disk")
    plan = plan_module_lipsync_reframe_v3(raw)
    assert plan.get("sacrifice_source") == "adaptive_band"
    band_top = plan.get("subtitle_band_top_y")
    assert band_top is not None
    expected_active_h = max(
        1,
        int(band_top)
        - PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_PAD_PX
        - PHASE_MODULE_LIPSYNC_SUBTITLE_BAND_EXTRA_SAFETY_PX,
    )
    assert plan["active_h"] == expected_active_h
    assert plan["active_h"] < band_top
    assert plan["sacrifice_zone_ratio"] > 0.22


def test_adaptive_sacrifice_falls_back_on_clean_cedric_probe():
    from phase_module_lipsync_delivery import resolve_module_lipsync_sacrifice_ratio

    raw = Path(
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production/Event_4/"
        "phase_b_probe3s_20260630-164139_RAW_wavespeed.mp4"
    )
    if not raw.is_file():
        pytest.skip("Event_4 Cedric probe raw not on disk")
    ratio, source, band_top = resolve_module_lipsync_sacrifice_ratio(raw, 1072, ss=1.5)
    assert source == "fixed_min"
    assert ratio == pytest.approx(0.12)
    assert band_top is None


def test_phases_write_complete_calls_delivery_finalize():
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    block = src.split("def _write_phase_b_lipsync_complete", 1)[1].split("\ndef ", 1)[0]
    assert "finalize_phase_module_lipsync_delivery" in block
    assert "phase_{_p}_lipsync_delivery_profile" in block


def test_phase_preview_hash_includes_delivery_recipe():
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    assert "lipsync_delivery:" in src
    assert "PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT" in src


def test_finalize_phase_module_lipsync_delivery_invokes_voice_first(tmp_path: Path):
    raw = tmp_path / "phase_b_lipsync_test.mp4"
    raw.write_bytes(b"raw")

    delivery = tmp_path / "phase_b_lipsync_test.delivery_tmp.mp4"
    delivery.write_bytes(b"delivery")

    def _fake_encode(src, dst, **kwargs):
        assert kwargs.get("include_audio") is True
        assert "crop=" in kwargs.get("vf", "")
        dst.write_bytes(b"encoded")
        return dst

    with mock.patch(
        "video_delivery._run_single_delivery_encode",
        side_effect=_fake_encode,
    ) as enc, mock.patch(
        "phase_module_lipsync_delivery.plan_module_lipsync_reframe_v3",
        return_value={
            "mode": "canonical_v3",
            "frame_w": 1920,
            "frame_h": 1072,
            "active_h": 943,
            "sacrifice_zone_ratio": 0.12,
            "nose_y_px": 380,
            "nose_source": "probe",
            "target_nose_y_ratio": 0.30,
            "horizontal_bias": -0.10,
            "crop_w": 1676,
            "crop_h": 943,
            "crop_x": 98,
            "crop_y": 98,
            "bottom_crop_ratio": 0.12,
        },
    ), mock.patch(
        "phase_module_lipsync_delivery.plan_module_lipsync_reframe",
        side_effect=lambda p, **kw: {
            "mode": "canonical_v3",
            "frame_w": 1920,
            "frame_h": 1072,
            "active_h": 943,
            "sacrifice_zone_ratio": 0.12,
            "nose_y_px": 380,
            "nose_source": "probe",
            "target_nose_y_ratio": 0.30,
            "horizontal_bias": -0.10,
            "crop_w": 1676,
            "crop_h": 943,
            "crop_x": 98,
            "crop_y": 98,
            "bottom_crop_ratio": 0.12,
        },
    ), mock.patch(
        "phase_module_lipsync_delivery._probe_video_size",
        side_effect=[(1920, 1072), (1280, 720)],
    ), mock.patch(
        "phase_module_lipsync_delivery._probe_bitrate",
        return_value=1_800_000,
    ), mock.patch(
        "video_delivery._has_audio",
        return_value=True,
    ):
        meta = finalize_phase_module_lipsync_delivery(
            raw,
            delivery_recipe=PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3,
        )

    enc.assert_called_once()
    assert raw.read_bytes() == b"encoded"
    assert meta["delivery_profile"] == PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE
    assert meta["delivery_recipe"] == PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V3
    assert meta["raw_width"] == 1920
    assert meta["width"] == 1280
    assert "force_original_aspect_ratio=increase" not in enc.call_args.kwargs.get("vf", "")


def test_stitch_bake_core_calls_phase_b_delivery_preflight():
    editor = Path(__file__).resolve().parent.parent / "server_handlers" / "stitch_editor.py"
    text = editor.read_text(encoding="utf-8")
    block = text.split("def _run_stitch_bake_core", 1)[1].split("\ndef ", 1)[0]
    assert "ensure_phase_b_stitch_slot_for_bake" in block
    assert "STITCH_BAKE_PHASE_B_DELIVERY_V1" in (
        Path(__file__).resolve().parent.parent / "server_handlers" / "phases.py"
    ).read_text(encoding="utf-8")


def test_plan_module_lipsync_reframe_v2_letterbox_on_pillarbox():
    from phase_module_lipsync_delivery import (
        PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2,
        plan_module_lipsync_reframe,
    )

    with mock.patch(
        "phase_module_lipsync_delivery._probe_video_size",
        return_value=(720, 544),
    ), mock.patch(
        "phase_module_lipsync_delivery.probe_avatar_pro_content_crop",
        return_value=(544, 544, 88, 0),
    ):
        plan = plan_module_lipsync_reframe(
            Path("/fake/pillarbox.mp4"),
            delivery_recipe=PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V2,
        )
    assert plan["mode"] == "letterbox"


def test_finalize_real_tiny_mp4(tmp_path: Path):
    """Integration: ffmpeg round-trip on a minimal synthetic clip."""
    src = tmp_path / "tiny_src.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=720x544:rate=24:duration=0.5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(src),
        ],
        check=True,
        timeout=60,
    )
    meta = finalize_phase_module_lipsync_delivery(src)
    assert meta["width"] == 1280
    assert meta["height"] == 720
    assert meta["bitrate_bps"] > 0
