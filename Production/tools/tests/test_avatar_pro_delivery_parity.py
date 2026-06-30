"""Beat Gen Avatar Pro delivery must share Phase A/B module encode choke point."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from beat_avatar_lipsync import encode_avatar_pro_delivery  # noqa: E402
from phase_module_lipsync_delivery import (  # noqa: E402
    PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
    PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT,
    finalize_phase_module_lipsync_delivery,
)


def test_beat_avatar_encode_delegates_to_phase_module_finalize():
    src = (TOOLS / "beat_avatar_lipsync.py").read_text(encoding="utf-8")
    block = src.split("def encode_avatar_pro_delivery", 1)[1].split("\ndef ", 1)[0]
    assert "finalize_phase_module_lipsync_delivery" in block
    assert "sharpen=True" in block
    assert 'profile = "standard"' not in block
    assert "sharpen=False" not in block


def test_avatar_pipeline_metadata_uses_module_delivery_fields():
    pipeline = (TOOLS / "arlo_avatar_beat_pipeline.py").read_text(encoding="utf-8")
    assert "encode_avatar_pro_delivery(raw, delivery_target)" in pipeline
    assert "delivery_meta.get(\"delivery_profile\")" in pipeline
    assert "standard when raw" not in pipeline


def test_encode_avatar_pro_delivery_invokes_shared_finalize(tmp_path: Path):
    raw = tmp_path / "beat_g2_avatar_pro.mp4"
    delivery = tmp_path / "beat_g2_avatar_pro_delivery.mp4"
    raw.write_bytes(b"raw-bytes")

    fake_meta = {
        "delivery_profile": PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
        "delivery_recipe": PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_CURRENT,
        "sharpen": True,
        "width": 1280,
        "height": 720,
    }

    with mock.patch(
        "phase_module_lipsync_delivery.finalize_phase_module_lipsync_delivery",
        return_value=fake_meta,
    ) as finalize:
        out, meta = encode_avatar_pro_delivery(raw, delivery)

    finalize.assert_called_once()
    assert finalize.call_args.kwargs.get("sharpen") is True
    assert out == delivery
    assert delivery.read_bytes() == b"raw-bytes"
    assert raw.read_bytes() == b"raw-bytes"
    assert meta["delivery_profile"] == "voice_first_upscale"
    assert meta["sharpen"] is True


@pytest.mark.integration
def test_encode_avatar_pro_delivery_real_ffmpeg_matches_phase_b_recipe(tmp_path: Path):
    """Golden: high-res Avatar raw → 1280x720 voice_first_upscale + sharpen (same as Phase B)."""
    raw = tmp_path / "avatar_raw.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1920x1072:rate=24:duration=0.4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(raw),
        ],
        check=True,
        timeout=60,
    )
    delivery = tmp_path / "avatar_raw_delivery.mp4"
    out, meta = encode_avatar_pro_delivery(raw, delivery)
    assert out.is_file()
    assert out.stat().st_size > 0
    assert meta["delivery_profile"] == PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE
    assert meta["sharpen"] is True
    assert meta["width"] == 1280
    assert meta["height"] == 720
    # Raw master untouched when delivery is a separate path.
    assert raw.stat().st_size > 0
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    import json

    stream = json.loads(probe.stdout)["streams"][0]
    assert int(stream["width"]) == 1280
    assert int(stream["height"]) == 720
