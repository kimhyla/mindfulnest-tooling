#!/usr/bin/env python3
"""Shared MindfulNest kid-facing video delivery encoder.

Source/master files may be larger or higher resolution, but anything intended
for playback/stitch/export should pass through this LD-284/LD-296-aligned
profile: 1280x720, H.264 High, yuv420p, 24fps, AAC, +faststart, <=1.9 Mbps.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

DELIVERY_WIDTH = 1280
DELIVERY_HEIGHT = 720
DELIVERY_FPS = 24
DELIVERY_VIDEO_BITRATE = "1500k"
DELIVERY_MAXRATE = "1800k"
DELIVERY_BUFSIZE = "3000k"
DELIVERY_AUDIO_BITRATE = "128k"
DELIVERY_MAX_BITRATE_BPS = 1_900_000
LIPSYNC_INPUT_WIDTH = 1920
LIPSYNC_INPUT_HEIGHT = 1080
LIPSYNC_INPUT_VIDEO_BITRATE = "4500k"
LIPSYNC_INPUT_MAXRATE = "5500k"
LIPSYNC_INPUT_BUFSIZE = "9000k"

DELIVERY_VF = (
    f"scale={DELIVERY_WIDTH}:{DELIVERY_HEIGHT}:force_original_aspect_ratio=decrease,"
    f"pad={DELIVERY_WIDTH}:{DELIVERY_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
    "setsar=1:1,"
    f"fps={DELIVERY_FPS}"
)


def _has_audio(path: Path) -> bool:
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        return False
    try:
        return bool(json.loads(probe.stdout).get("streams"))
    except json.JSONDecodeError:
        return False


def _probe_bitrate(path: Path) -> int:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    try:
        return int(json.loads(probe.stdout).get("format", {}).get("bit_rate") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0


def encode_delivery_video(
    src: Path,
    dst: Path,
    *,
    include_audio: bool = True,
    sharpen: bool = False,
    timeout_s: int = 300,
) -> Path:
    """Encode a compact kid-facing delivery MP4 from any source video."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    vf = DELIVERY_VF
    if sharpen:
        vf = f"{vf},unsharp=5:5:0.45:3:3:0.20"

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
    ]
    has_audio = include_audio and _has_audio(src)
    if include_audio and not has_audio:
        cmd += [
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-shortest", "-map", "0:v:0", "-map", "1:a:0",
        ]
    cmd += [
        "-vf", vf,
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-g", "48",
        "-b:v", DELIVERY_VIDEO_BITRATE,
        "-maxrate", DELIVERY_MAXRATE,
        "-bufsize", DELIVERY_BUFSIZE,
    ]
    if include_audio:
        cmd += ["-c:a", "aac", "-b:a", DELIVERY_AUDIO_BITRATE, "-ac", "1", "-ar", "44100"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", str(tmp)]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
        bitrate = _probe_bitrate(tmp)
        if bitrate > DELIVERY_MAX_BITRATE_BPS:
            raise RuntimeError(
                f"delivery bitrate {bitrate:,} bps exceeds {DELIVERY_MAX_BITRATE_BPS:,} bps"
            )
        os.replace(tmp, dst)
        return dst
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def encode_lipsync_input(src: Path, dst: Path) -> Path:
    """Create the canonical silent input submitted to Kling LipSync.

    Kling LipSync exposes no output-resolution parameter. Its public schema says
    output follows a 720p/1080p source video, but real WaveSpeed/Kling smokes have
    returned 832x464 even from 1920x1080 input. Submit 1920x1080 as the best
    available source, then require the post-lipsync >=720p quality gate before any
    kid-facing delivery clip can be approved.
    """
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    vf = (
        f"scale={LIPSYNC_INPUT_WIDTH}:{LIPSYNC_INPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={LIPSYNC_INPUT_WIDTH}:{LIPSYNC_INPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1:1,"
        f"fps={DELIVERY_FPS}"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", "slow", "-g", "48",
        "-b:v", LIPSYNC_INPUT_VIDEO_BITRATE,
        "-maxrate", LIPSYNC_INPUT_MAXRATE,
        "-bufsize", LIPSYNC_INPUT_BUFSIZE,
        "-an",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        os.replace(tmp, dst)
        return dst
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
