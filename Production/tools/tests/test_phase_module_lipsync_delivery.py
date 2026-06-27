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
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1,
    PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH,
    finalize_phase_module_lipsync_delivery,
)


def test_phase_module_lipsync_delivery_constants():
    assert PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE == "voice_first_upscale"
    assert PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1 == "PHASE_MODULE_LIPSYNC_DELIVERY_V1"
    assert PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH == 1280
    assert PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT == 720


def test_phases_write_complete_calls_delivery_finalize():
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    block = src.split("def _write_phase_b_lipsync_complete", 1)[1].split("\ndef ", 1)[0]
    assert "finalize_phase_module_lipsync_delivery" in block
    assert "phase_{_p}_lipsync_delivery_profile" in block


def test_phase_preview_hash_includes_delivery_recipe():
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    assert "lipsync_delivery:" in src
    assert "PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1" in src


def test_finalize_phase_module_lipsync_delivery_invokes_voice_first(tmp_path: Path):
    raw = tmp_path / "phase_b_lipsync_test.mp4"
    raw.write_bytes(b"raw")

    delivery = tmp_path / "phase_b_lipsync_test.delivery_tmp.mp4"
    delivery.write_bytes(b"delivery")

    def _fake_encode(src, dst, **kwargs):
        assert kwargs.get("delivery_profile") == "voice_first_upscale"
        assert kwargs.get("sharpen") is True
        dst.write_bytes(b"encoded")
        return dst

    with mock.patch(
        "video_delivery.encode_delivery_video",
        side_effect=_fake_encode,
    ) as enc, mock.patch(
        "phase_module_lipsync_delivery._probe_video_size",
        side_effect=[(720, 544), (1280, 720)],
    ), mock.patch(
        "phase_module_lipsync_delivery._probe_bitrate",
        return_value=1_800_000,
    ):
        meta = finalize_phase_module_lipsync_delivery(raw)

    enc.assert_called_once()
    assert raw.read_bytes() == b"encoded"
    assert meta["delivery_profile"] == PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE
    assert meta["raw_width"] == 720
    assert meta["width"] == 1280


def test_stitch_bake_core_calls_phase_b_delivery_preflight():
    editor = Path(__file__).resolve().parent.parent / "server_handlers" / "stitch_editor.py"
    text = editor.read_text(encoding="utf-8")
    block = text.split("def _run_stitch_bake_core", 1)[1].split("\ndef ", 1)[0]
    assert "ensure_phase_b_stitch_slot_for_bake" in block
    assert "STITCH_BAKE_PHASE_B_DELIVERY_V1" in (
        Path(__file__).resolve().parent.parent / "server_handlers" / "phases.py"
    ).read_text(encoding="utf-8")


@pytest.mark.integration
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
