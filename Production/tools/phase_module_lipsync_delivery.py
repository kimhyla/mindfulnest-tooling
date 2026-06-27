#!/usr/bin/env python3
"""Phase A/B module lipsync → kid-facing delivery encode (category parity with beat lipsync).

Kling Sync returns sub-720 full-scene MP4 (~720×544). Beat-level lipsync runs
``voice_first_upscale`` after download (arlo_o3_voice_pipeline). Phase B module
lipsync previously saved raw Kling bytes — this module is the single choke point
for delivery encode on terminal module lipsync writes.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE = "voice_first_upscale"
PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1 = "PHASE_MODULE_LIPSYNC_DELIVERY_V1"
PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH = 1280
PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT = 720


def _probe_video_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    return int(stream.get("width") or 0), int(stream.get("height") or 0)


def _probe_bitrate(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    try:
        return int(json.loads(result.stdout).get("format", {}).get("bit_rate") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0


def finalize_phase_module_lipsync_delivery(
    path: Path,
    *,
    sharpen: bool = True,
    timeout_s: int = 900,
) -> dict:
    """In-place voice_first_upscale on a module lipsync MP4; returns delivery metadata."""
    from video_delivery import (  # noqa: PLC0415
        VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS,
        encode_delivery_video,
    )

    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"lipsync file not found: {path}")

    raw_w, raw_h = _probe_video_size(path)
    tmp = path.with_name(f"{path.stem}.delivery_tmp{path.suffix}")
    try:
        encode_delivery_video(
            path,
            tmp,
            include_audio=True,
            sharpen=sharpen,
            delivery_profile=PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
            timeout_s=timeout_s,
        )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    out_w, out_h = _probe_video_size(path)
    if (out_w, out_h) != (PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH, PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT):
        raise RuntimeError(
            f"delivery encode shape {out_w}x{out_h} != "
            f"{PHASE_MODULE_LIPSYNC_DELIVERY_WIDTH}x{PHASE_MODULE_LIPSYNC_DELIVERY_HEIGHT}"
        )
    bitrate = _probe_bitrate(path)
    if bitrate <= 0 or bitrate > VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS:
        raise RuntimeError(
            f"delivery bitrate {bitrate:,} bps outside (0, {VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS:,}]"
        )

    return {
        "path": str(path),
        "delivery_profile": PHASE_MODULE_LIPSYNC_DELIVERY_PROFILE,
        "delivery_recipe": PHASE_MODULE_LIPSYNC_DELIVERY_RECIPE_V1,
        "raw_width": raw_w,
        "raw_height": raw_h,
        "width": out_w,
        "height": out_h,
        "bitrate_bps": bitrate,
        "file_size_bytes": path.stat().st_size,
        "sharpen": sharpen,
    }
