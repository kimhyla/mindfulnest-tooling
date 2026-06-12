#!/usr/bin/env python3
"""Phase A A/V post-processing helpers (dependency-ordered pipeline stages).

Classification:
  A — crossfade_loop_video           idle base extension (no hard concat seams)
  B — pad_video_to_match_audio       Kling lipsync A/V duration repair
  C — apply_smooth_zoom              Ken Burns 2× prescale zoompan (jitter-free)
  D — trim_av_lead_in                strip lipsync preroll before stitch
  D2 — trim_av_trailing_silence      cut ByteDance post-pad lip tail after speech ends
  E — upscale_lipsync_to_bookend     Kling ~720×544 → bookend resolution (sharp stitch)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from production_server import _ffprobe_duration  # noqa: E402

DEFAULT_FPS = 24
DEFAULT_LOOP_XFADE_S = 0.35
# Match wide fly-in/out Kling native output (4:3) so stitch normalize downscales sharply.
BOOKEND_WIDTH = 1660
BOOKEND_HEIGHT = 1244
# Kling LipSync returns ~720×544 regardless of input base resolution.
KLING_LIPSYNC_UPSCALE_THRESHOLD_W = 1000
# Hold after last detected speech before hard cut — enough for a natural close, not
# the full ByteDance LIPSYNC_PAD_END neutral-return animation (~2.5s).
TRAILING_SPEECH_HOLD_S = 0.75  # was 0.15 — avoid clipping last syllable before tail trim
_SILENCE_DETECT_NOISE_DB = "-32dB"
_SILENCE_DETECT_MIN_S = 0.20


def log(msg: str) -> None:
    print(f"[phase_a_av_post] {msg}", flush=True)


def _stream_duration(path: Path, codec_type: str) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", f"{codec_type}:0",
            "-show_entries", "stream=duration", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return 0.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def av_duration_gap(path: Path) -> tuple[float, float, float]:
    """Return (video_s, audio_s, gap audio-video). gap>0 => video shorter."""
    v = _stream_duration(path, "v")
    a = _stream_duration(path, "a")
    if v <= 0:
        v = _ffprobe_duration(path)
    return v, a, max(0.0, a - v)


def crossfade_loop_video(
    src: Path,
    dst: Path,
    target_s: float,
    *,
    xfade_s: float = DEFAULT_LOOP_XFADE_S,
    fps: int = DEFAULT_FPS,
) -> Path:
    """Extend idle base by crossfading repeats (replaces hard concat forward_loop)."""
    src = src.expanduser().resolve()
    dst = dst.expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_dur = _ffprobe_duration(src)
    if src_dur <= 0:
        raise ValueError(f"invalid source duration: {src}")

    if src_dur >= target_s:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(src), "-t", f"{target_s:.3f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-an", "-r", str(fps),
                "-movflags", "+faststart", str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        log(f"crossfade loop: trim only {src_dur:.1f}s -> {target_s:.1f}s")
        return dst

    xfade_s = min(xfade_s, max(0.1, src_dur * 0.08))
    step = max(0.05, src_dur - xfade_s)
    copies = 1
    while copies * src_dur - (copies - 1) * xfade_s < target_s + 0.05:
        copies += 1
        if copies > 64:
            raise RuntimeError("crossfade_loop_video: too many copies")

    inputs: list[str] = []
    for _ in range(copies):
        inputs.extend(["-i", str(src)])

    fc_parts: list[str] = []
    prev_label = "0:v"
    timeline = src_dur
    for i in range(1, copies):
        offset = max(0.0, timeline - xfade_s)
        out_tag = f"vx{i}"
        fc_parts.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:duration={xfade_s:.3f}"
            f":offset={offset:.3f}[{out_tag}]"
        )
        prev_label = out_tag
        timeline += step
    fc_parts.append(f"[{prev_label}]fps={fps},format=yuv420p[vout]")
    filter_complex = ";".join(fc_parts)

    tmp = dst.with_suffix(".tmp.mp4")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-t", f"{target_s:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-an",
        "-movflags", "+faststart", str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-800:] or "crossfade_loop ffmpeg failed")
    tmp.replace(dst)
    log(
        f"crossfade loop: {src_dur:.1f}s x {copies} xfade={xfade_s:.2f}s "
        f"-> {dst.name} ({_ffprobe_duration(dst):.1f}s)"
    )
    return dst


def pad_video_to_match_audio(src: Path, dst: Path | None = None) -> tuple[Path, float]:
    """Clone-pad video when shorter than audio. Returns (path, pad_seconds)."""
    src = src.expanduser().resolve()
    if dst is None:
        dst = src.with_name(f"{src.stem}_padded{src.suffix}")
    else:
        dst = dst.expanduser().resolve()

    v_dur, a_dur, gap = av_duration_gap(src)
    if gap <= 0.04:
        if dst != src:
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-c", "copy", str(dst),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        log(f"pad skip: video={v_dur:.3f}s audio={a_dur:.3f}s gap={gap:.3f}s")
        return (dst if dst.is_file() else src), 0.0

    tmp = dst.with_suffix(".tmp.mp4")
    filter_complex = f"[0:v]tpad=stop_mode=clone:stop_duration={gap:.3f}[vout]"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(tmp),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    tmp.replace(dst)
    log(f"pad video +{gap:.3f}s (v={v_dur:.3f} a={a_dur:.3f}) -> {dst.name}")
    return dst, gap


def _probe_video_width(path: Path) -> int:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return 0
    try:
        return int(float(r.stdout.strip()))
    except ValueError:
        return 0


def upscale_lipsync_to_bookend(
    src: Path,
    dst: Path | None = None,
    *,
    width: int = BOOKEND_WIDTH,
    height: int = BOOKEND_HEIGHT,
    fps: int = DEFAULT_FPS,
) -> Path:
    """Upscale Kling LipSync output (~720×544) to bookend resolution before stitch.

    Uses 2× prescale + lanczos (same quality trick as apply_smooth_zoom) without
    Ken Burns crop/zoom so anatomy framing stays identical to the base clip.
    """
    src = src.expanduser().resolve()
    if dst is None:
        dst = src.with_name(f"{src.stem}_bookend{src.suffix}")
    else:
        dst = dst.expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    src_w = _probe_video_width(src)
    if src_w >= KLING_LIPSYNC_UPSCALE_THRESHOLD_W:
        if dst != src:
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-c", "copy", str(dst),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        log(f"upscale skip: already {src_w}px wide -> {dst.name}")
        return dst

    prescale_w = width * 2
    prescale_h = height * 2
    vf = (
        f"scale={prescale_w}:{prescale_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={prescale_w}:{prescale_h},"
        f"scale={width}:{height}:flags=lanczos,setsar=1:1,fps={fps}"
    )
    tmp = dst.with_suffix(".tmp.mp4")
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(tmp),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-800:] or "upscale_lipsync_to_bookend ffmpeg failed")
    tmp.replace(dst)
    out_w = _probe_video_width(dst)
    log(f"upscale {src_w}px -> {out_w}px ({width}x{height}) -> {dst.name}")
    return dst


def trim_av_lead_in(src: Path, dst: Path, lead_s: float) -> Path:
    """Frame-accurate trim of preroll dead air from both streams."""
    src = src.expanduser().resolve()
    dst = dst.expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if lead_s <= 0.01:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(src), "-c", "copy", str(dst),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return dst

    tmp = dst.with_suffix(".tmp.mp4")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{lead_s:.3f}", "-i", str(src),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart",
            str(tmp),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    tmp.replace(dst)
    log(f"trim lead-in {lead_s:.3f}s -> {dst.name} ({_ffprobe_duration(dst):.2f}s)")
    return dst


def detect_trailing_silence_start(
    media_path: Path,
    *,
    noise_db: str = _SILENCE_DETECT_NOISE_DB,
    min_silence_s: float = _SILENCE_DETECT_MIN_S,
) -> float | None:
    """Return timeline position (s) where the final trailing silence begins."""
    media_path = media_path.expanduser().resolve()
    r = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(media_path),
            "-af", f"silencedetect=noise={noise_db}:d={min_silence_s}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    starts: list[float] = []
    for line in r.stderr.splitlines():
        if "silence_start:" not in line:
            continue
        try:
            starts.append(float(line.split("silence_start:")[1].strip().split()[0]))
        except (ValueError, IndexError):
            continue
    if not starts:
        return None
    total = _ffprobe_duration(media_path)
    last = starts[-1]
    # Ignore mid-file pauses — only trim a tail that runs to (or nearly to) EOF.
    if total - last >= 0.12:
        return last
    return None


def trim_av_trailing_silence(
    src: Path,
    dst: Path,
    *,
    hold_after_speech_s: float = TRAILING_SPEECH_HOLD_S,
) -> tuple[Path, float]:
    """Cut trailing silence + post-pad lip motion; keep a short hold after last speech."""
    src = src.expanduser().resolve()
    dst = dst.expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    total = _ffprobe_duration(src)
    silence_start = detect_trailing_silence_start(src)
    if silence_start is None:
        target = total
    else:
        target = min(total, silence_start + hold_after_speech_s)
    trimmed_s = max(0.0, total - target)
    if trimmed_s < 0.08:
        if dst != src:
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-c", "copy", str(dst),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        log(f"trailing trim skip: tail {trimmed_s:.3f}s (< 80ms)")
        return (dst if dst.is_file() else src), 0.0

    tmp = dst.with_suffix(".tmp.mp4")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src), "-t", f"{target:.3f}",
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart",
            str(tmp),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    tmp.replace(dst)
    log(
        f"trailing trim -{trimmed_s:.3f}s "
        f"(speech_end~{silence_start:.2f}s hold={hold_after_speech_s:.2f}s) "
        f"-> {dst.name} ({_ffprobe_duration(dst):.2f}s)"
    )
    return dst, trimmed_s


def apply_smooth_zoom(
    src: Path,
    dst: Path | None = None,
    *,
    zoom_start: float = 1.0,
    zoom_end: float = 1.08,
    ramp_sec: float = 14.0,
    ramp_delay_sec: float = 1.0,
    focal_x: float = 0.5,
    focal_y: float = 0.47,
    fps: int = DEFAULT_FPS,
) -> Path:
    """Ken Burns-style smooth zoom (2× prescale, single zoompan pass)."""
    src = src.expanduser().resolve()
    if dst is None:
        dst = src.with_name(f"{src.stem}_zoom{src.suffix}")
    else:
        dst = dst.expanduser().resolve()

    duration_s = _ffprobe_duration(src)
    delay_frames = max(int(round(ramp_delay_sec * fps)), 0)
    ramp_frames = max(int(round(ramp_sec * fps)), 1)

    zs, ze = zoom_start, zoom_end
    if delay_frames > 0:
        z_expr = (
            f"if(lte(on,{delay_frames}),{zs:.6f},"
            f"if(lte(on,{delay_frames + ramp_frames}),"
            f"{zs:.6f}+({ze:.6f}-{zs:.6f})*(on-{delay_frames})/{ramp_frames},"
            f"{ze:.6f}))"
        )
    else:
        z_expr = (
            f"if(lte(on,{ramp_frames}),"
            f"{zs:.6f}+({ze:.6f}-{zs:.6f})*on/{ramp_frames},"
            f"{ze:.6f})"
        )

    x_expr = f"iw*{focal_x:.4f}-(iw/zoom/2)"
    y_expr = f"ih*{focal_y:.4f}-(ih/zoom/2)"

    vf = (
        "scale=2560:1440:force_original_aspect_ratio=increase,"
        "crop=2560:1440,"
        f"zoompan=z='{z_expr}':d=1:x='{x_expr}':y='{y_expr}':"
        f"s=1280x720:fps={fps}"
    )

    tmp = dst.with_suffix(".tmp.mp4")
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(tmp),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-800:] or "smooth zoom ffmpeg failed")
    tmp.replace(dst)
    log(
        f"smooth zoom {zs:.2f}->{ze:.2f} delay={ramp_delay_sec:.1f}s "
        f"ramp={ramp_sec:.1f}s -> {dst.name}"
    )
    return dst
