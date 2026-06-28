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
import sys
from pathlib import Path

_CRED_LIB = Path(__file__).resolve().parent / "credentials_lib"
if str(_CRED_LIB) not in sys.path:
    sys.path.insert(0, str(_CRED_LIB))
from video_encode_policy import (  # noqa: E402
    VIDEO_QUALITY_CRF,
    VIDEO_QUALITY_GRADFUN_VF,
    VIDEO_QUALITY_PRESET_BAKE,
)

DELIVERY_WIDTH = 1280
DELIVERY_HEIGHT = 720
DELIVERY_FPS = 24
DELIVERY_VIDEO_BITRATE = "1500k"
DELIVERY_MAXRATE = "1800k"
DELIVERY_BUFSIZE = "3000k"
DELIVERY_AUDIO_BITRATE = "128k"
DELIVERY_MAX_BITRATE_BPS = 1_900_000
# Voice-first: lipsync raw is often 832x464 — use full LD-296 budget + lanczos upscale.
VOICE_FIRST_DELIVERY_VIDEO_BITRATE = "1850k"
VOICE_FIRST_DELIVERY_MAXRATE = "1900k"
VOICE_FIRST_DELIVERY_BUFSIZE = "3800k"
VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS = DELIVERY_MAX_BITRATE_BPS
# Module-final lean kid-facing delivery (stitch bake second pass).
# LD-283: 60 MB target / 80 MB hard ceiling — ~380 s module ≈ 1.2 Mbps total budget.
MODULE_FINAL_LEAN_VIDEO_BITRATE = "1050k"
MODULE_FINAL_LEAN_MAXRATE = "1200k"
MODULE_FINAL_LEAN_BUFSIZE = "2400k"
MODULE_FINAL_LEAN_MAX_BITRATE_BPS = 1_200_000
# Stronger gradfun on lean pass only (fireplace/stone gradients); normalize keeps policy default.
MODULE_FINAL_LEAN_GRADFUN_VF = "gradfun=strength=1.5:radius=8"
MODULE_FINAL_LEAN_DELIVERY_V1 = "MODULE_FINAL_LEAN_DELIVERY_V1"
MODULE_FINAL_LEAN_DELIVERY_V2 = "MODULE_FINAL_LEAN_DELIVERY_V2"
# V3 — 1050k/1200k within 60 MB target + stronger lean-pass gradfun (VIDEO_QUALITY_V1).
MODULE_FINAL_LEAN_DELIVERY_V3 = "MODULE_FINAL_LEAN_DELIVERY_V3"
MODULE_FINAL_LEAN_DELIVERY_CURRENT = MODULE_FINAL_LEAN_DELIVERY_V3
# STITCH_MP4_PLAYBACK_TIMESTAMPS_V1 — QuickTime-safe non-negative video DTS on all exports.
STITCH_MP4_PLAYBACK_TIMESTAMPS_V1 = "STITCH_MP4_PLAYBACK_TIMESTAMPS_V1"
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

VOICE_FIRST_UPSCALE_VF = (
    f"scale={DELIVERY_WIDTH}:{DELIVERY_HEIGHT}:flags=lanczos+accurate_rnd+full_chroma_int:"
    f"force_original_aspect_ratio=decrease,"
    f"pad={DELIVERY_WIDTH}:{DELIVERY_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
    "setsar=1:1,"
    f"fps={DELIVERY_FPS}"
)

VOICE_FIRST_UPSCALE_UNSHARP = "unsharp=5:5:0.62:3:3:0.26"
DELIVERY_UNSHARP = "unsharp=5:5:0.50:3:3:0.22"


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


def _delivery_profile_encode_limits(profile: str) -> tuple[str, str, str, int]:
    """Return (video_bitrate, maxrate, bufsize, max_bitrate_bps) for a delivery profile."""
    normalized = (profile or "standard").strip().lower()
    if normalized == "module_final_lean":
        return (
            MODULE_FINAL_LEAN_VIDEO_BITRATE,
            MODULE_FINAL_LEAN_MAXRATE,
            MODULE_FINAL_LEAN_BUFSIZE,
            MODULE_FINAL_LEAN_MAX_BITRATE_BPS,
        )
    if normalized == "voice_first_upscale":
        return (
            VOICE_FIRST_DELIVERY_VIDEO_BITRATE,
            VOICE_FIRST_DELIVERY_MAXRATE,
            VOICE_FIRST_DELIVERY_BUFSIZE,
            VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS,
        )
    return (
        DELIVERY_VIDEO_BITRATE,
        DELIVERY_MAXRATE,
        DELIVERY_BUFSIZE,
        DELIVERY_MAX_BITRATE_BPS,
    )


def _ensure_delivery_playback_timestamps_capped(
    path: Path,
    *,
    delivery_profile: str,
    timeout_s: int = 900,
) -> Path:
    """Timestamp heal for capped delivery MP4s — copy remux only, never unconstrained re-encode."""
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        _remux_mp4_copy_safe,
        mp4_operator_playback_timestamps_safe,
    )

    path = Path(path)
    if mp4_operator_playback_timestamps_safe(path):
        return path

    _remux_mp4_copy_safe(path, timeout_s=timeout_s)
    return path


def ensure_mp4_playback_timestamps(
    path: Path,
    *,
    timeout_s: int = 900,
    delivery_profile: str | None = None,
) -> Path:
    """Canonical post-export pass: browser-safe timestamps (DTS near 0 + zero-based A/V start).

    When ``delivery_profile`` is set, timestamp healing preserves LD-296 / lean bitrate caps
    instead of the unconstrained CRF path in ``normalize_mp4_browser_playback_timeline``.
    """
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        mp4_is_playable,
        mp4_operator_playback_timestamps_safe,
        normalize_mp4_browser_playback_timeline,
    )

    path = Path(path)
    if not path.is_file() or not mp4_is_playable(path):
        return path
    if mp4_operator_playback_timestamps_safe(path):
        return path
    if delivery_profile:
        return _ensure_delivery_playback_timestamps_capped(
            path,
            delivery_profile=delivery_profile,
            timeout_s=timeout_s,
        )
    normalize_mp4_browser_playback_timeline(path, timeout_s=timeout_s)
    return path


def _probe_video_size(path: Path) -> tuple[int, int]:
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    streams = json.loads(probe.stdout).get("streams") or [{}]
    stream = streams[0] if streams else {}
    return int(stream.get("width") or 0), int(stream.get("height") or 0)


def _delivery_vf_for_source(path: Path) -> str:
    width, height = _probe_video_size(path)
    if width == DELIVERY_WIDTH and height == DELIVERY_HEIGHT:
        return f"fps={DELIVERY_FPS},setsar=1:1"
    return DELIVERY_VF


def _module_final_lean_vf(path: Path) -> str:
    """Bake final pass — scale/pad + stronger gradfun for fireplace/soft BG (VQ-V3)."""
    return f"{_delivery_vf_for_source(path)},{MODULE_FINAL_LEAN_GRADFUN_VF}"


def _voice_first_upscale_vf(*, sharpen: bool) -> str:
    vf = VOICE_FIRST_UPSCALE_VF
    if sharpen:
        vf = f"{vf},{VOICE_FIRST_UPSCALE_UNSHARP}"
    return vf


def _delivery_encode_attempts(profile: str, *, sharpen: bool) -> list[tuple[str, str, str, str, int]]:
    """Return ordered (vf, video_bitrate, maxrate, bufsize, max_bitrate_bps) attempts."""
    normalized = (profile or "standard").strip().lower()
    if normalized == "voice_first_upscale":
        cap = VOICE_FIRST_DELIVERY_MAX_BITRATE_BPS
        attempts: list[tuple[str, str, str, str, int]] = [
            (
                _voice_first_upscale_vf(sharpen=sharpen),
                VOICE_FIRST_DELIVERY_VIDEO_BITRATE,
                VOICE_FIRST_DELIVERY_MAXRATE,
                VOICE_FIRST_DELIVERY_BUFSIZE,
                cap,
            ),
            (
                _voice_first_upscale_vf(sharpen=sharpen),
                DELIVERY_VIDEO_BITRATE,
                DELIVERY_MAXRATE,
                DELIVERY_BUFSIZE,
                cap,
            ),
        ]
        if sharpen:
            attempts.append(
                (
                    _voice_first_upscale_vf(sharpen=False),
                    DELIVERY_VIDEO_BITRATE,
                    DELIVERY_MAXRATE,
                    DELIVERY_BUFSIZE,
                    cap,
                )
            )
        return attempts
    vf = DELIVERY_VF
    if sharpen:
        vf = f"{vf},{DELIVERY_UNSHARP}"
    return [(vf, DELIVERY_VIDEO_BITRATE, DELIVERY_MAXRATE, DELIVERY_BUFSIZE,
             DELIVERY_MAX_BITRATE_BPS)]


def _run_single_delivery_encode(
    src: Path,
    tmp: Path,
    *,
    vf,
    video_bitrate: str,
    maxrate: str,
    bufsize: str,
    max_bitrate_bps: int,
    include_audio: bool,
    use_lean_quality_encode: bool,
    timeout_s: int,
) -> None:
    if callable(vf):
        vf = vf(src)
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
    cmd += ["-vf", vf]
    if use_lean_quality_encode:
        cmd += [
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-preset", VIDEO_QUALITY_PRESET_BAKE, "-g", "48",
            "-b:v", video_bitrate,
            "-maxrate", maxrate,
            "-bufsize", bufsize,
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-preset", "medium", "-g", "48",
            "-b:v", video_bitrate,
            "-maxrate", maxrate,
            "-bufsize", bufsize,
        ]
    if include_audio:
        cmd += ["-c:a", "aac", "-b:a", DELIVERY_AUDIO_BITRATE, "-ac", "1", "-ar", "44100"]
    else:
        cmd += ["-an"]
    cmd += [
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        str(tmp),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_s)
    bitrate = _probe_bitrate(tmp)
    if bitrate <= 0 or bitrate > max_bitrate_bps:
        raise RuntimeError(
            f"delivery bitrate {bitrate:,} bps exceeds {max_bitrate_bps:,} bps"
        )


def encode_delivery_video(
    src: Path,
    dst: Path,
    *,
    include_audio: bool = True,
    sharpen: bool = False,
    delivery_profile: str = "standard",
    timeout_s: int = 300,
) -> Path:
    """Encode a compact kid-facing delivery MP4 from any source video.

    ``delivery_profile``:
    - ``standard`` — LD-296 default (~1.5 Mbps target, bicubic scale)
    - ``voice_first_upscale`` — lanczos upscale + full 1.9 Mbps cap for sub-720 lipsync raw
    - ``module_final_lean`` — stitch module-final second pass (~1050 kbps target, 1200k cap)
    """
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.parent / f"{dst.stem}.tmp.{os.getpid()}{dst.suffix}"
    profile = (delivery_profile or "standard").strip().lower()
    use_lean_quality_encode = profile == "module_final_lean"

    if profile == "module_final_lean":
        if sharpen:
            def vf_factory(path):  # type: ignore[misc]
                return f"{_module_final_lean_vf(path)},{DELIVERY_UNSHARP}"
        else:
            vf_factory = _module_final_lean_vf
        attempts = [
            (
                vf_factory,
                MODULE_FINAL_LEAN_VIDEO_BITRATE,
                MODULE_FINAL_LEAN_MAXRATE,
                MODULE_FINAL_LEAN_BUFSIZE,
                MODULE_FINAL_LEAN_MAX_BITRATE_BPS,
            ),
            (
                vf_factory,
                "900k",
                "1050k",
                "2100k",
                MODULE_FINAL_LEAN_MAX_BITRATE_BPS,
            ),
        ]
    elif profile == "voice_first_upscale":
        attempts = _delivery_encode_attempts(profile, sharpen=sharpen)
    else:
        vf = DELIVERY_VF
        if sharpen:
            vf = f"{vf},{DELIVERY_UNSHARP}"
        attempts = [(vf, DELIVERY_VIDEO_BITRATE, DELIVERY_MAXRATE, DELIVERY_BUFSIZE,
                     DELIVERY_MAX_BITRATE_BPS)]

    last_err: RuntimeError | None = None
    try:
        for vf, video_bitrate, maxrate, bufsize, max_bitrate_bps in attempts:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            try:
                _run_single_delivery_encode(
                    src,
                    tmp,
                    vf=vf_factory if profile == "module_final_lean" else vf,
                    video_bitrate=video_bitrate,
                    maxrate=maxrate,
                    bufsize=bufsize,
                    max_bitrate_bps=max_bitrate_bps,
                    include_audio=include_audio,
                    use_lean_quality_encode=use_lean_quality_encode,
                    timeout_s=timeout_s,
                )
                os.replace(tmp, dst)
                ensure_mp4_playback_timestamps(
                    dst,
                    timeout_s=timeout_s,
                    delivery_profile=profile,
                )
                final_bitrate = _probe_bitrate(dst)
                if final_bitrate <= 0 or final_bitrate > max_bitrate_bps:
                    raise RuntimeError(
                        f"post-timestamp delivery bitrate {final_bitrate:,} bps exceeds "
                        f"{max_bitrate_bps:,} bps"
                    )
                return dst
            except RuntimeError as exc:
                if "bitrate" in str(exc) and profile in ("voice_first_upscale", "module_final_lean"):
                    last_err = exc
                    continue
                raise
        if last_err is not None:
            raise last_err
        raise RuntimeError("encode_delivery_video: no attempts configured")
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def encode_module_final_lean(src: Path, dst: Path, *, timeout_s: int = 900) -> Path:
    """Lean kid-facing module final — gradfun + slow preset within 1200k cap (VQ-V3)."""
    return encode_delivery_video(
        src,
        dst,
        delivery_profile="module_final_lean",
        timeout_s=timeout_s,
    )


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
