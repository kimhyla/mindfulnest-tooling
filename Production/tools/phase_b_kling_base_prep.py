"""Phase B Kling lipsync base prep — auto-size video to match audio stem.

Uses the approved Cedric bookend loop unit (~29s) when the selected base is
shorter than the stem. Never loops arbitrary short Kling idles (pleat source).
Long pre-built bases are trimmed only.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from phase_a_av_post import crossfade_loop_video
from production_server import _ffprobe_duration

WAVESPEED_RAW_MB_CEILING = 22.0
_PREP_CODE = "PHASE_B_KLING_AUTO_BOOKEND_UNIT_V1"


class PhaseBLoopUnitMissingError(FileNotFoundError):
    """Bookend loop unit not found under lipsync_bases."""


def resolve_phase_b_loop_unit(bases_dir: Path) -> Path:
    """Return the approved ~29s bookend unit used for auto extension."""
    from phase_b_cedric_contract import (  # noqa: WPS433
        PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID,
        PHASE_B_CEDRIC_LOOP_UNIT_FALLBACK_IDS,
    )

    bases_dir = bases_dir.expanduser().resolve()
    for clip_id in (PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID, *PHASE_B_CEDRIC_LOOP_UNIT_FALLBACK_IDS):
        candidate = bases_dir / f"{clip_id}.mp4"
        if candidate.is_file():
            return candidate
    raise PhaseBLoopUnitMissingError(
        f"Phase B bookend loop unit not found under {bases_dir}. "
        f"Expected {PHASE_B_CEDRIC_LOOP_UNIT_CLIP_ID}.mp4"
    )


def kling_submit_video_bitrate_bps(duration_s: float, *, mb_ceiling: float = WAVESPEED_RAW_MB_CEILING) -> int:
    """Pick a video bitrate that keeps a silent looped base under the API size cap."""
    safe_s = max(float(duration_s), 1.0)
    budget_bits = mb_ceiling * 1024 * 1024 * 8 * 0.92
    bps = int(budget_bits / safe_s)
    return max(800_000, min(2_000_000, bps))


def _reencode_for_kling_submit(src: Path, dst: Path, *, video_bitrate_bps: int) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    rate_k = max(800, video_bitrate_bps // 1000)
    maxrate_k = min(2000, int(rate_k * 1.15))
    bufsize_k = maxrate_k * 2
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-c:v", "libx264", "-preset", "fast",
            "-b:v", f"{rate_k}k", "-maxrate", f"{maxrate_k}k", "-bufsize", f"{bufsize_k}k",
            "-an", "-movflags", "+faststart", str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return dst


def _trim_to_duration(src: Path, dst: Path, duration_s: float) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src),
            "-t", f"{duration_s:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
            str(dst),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return dst


def _fit_submit_size(src: Path, work_path: Path, *, duration_s: float) -> tuple[Path, dict]:
    """Return a path under 22MB for Kling upload, re-encoding if needed."""
    size_mb = src.stat().st_size / 1024 / 1024
    if size_mb <= WAVESPEED_RAW_MB_CEILING:
        return src, {"submit_size_mb": round(size_mb, 2)}
    out = work_path.with_name(f"{work_path.stem}_reenc{work_path.suffix}")
    bps = kling_submit_video_bitrate_bps(duration_s)
    _reencode_for_kling_submit(src, out, video_bitrate_bps=bps)
    return out, {
        "submit_size_mb": round(out.stat().st_size / 1024 / 1024, 2),
        "video_bitrate_bps": bps,
    }


def prep_phase_b_kling_base_video(
    base_path: Path,
    target_video_s: float,
    work_path: Path,
    *,
    bases_dir: Path | None = None,
) -> tuple[Path, dict]:
    """Build Kling submit video exactly sized to ``target_video_s`` (stem + tailroom)."""
    base_path = base_path.expanduser().resolve()
    work_path = work_path.expanduser().resolve()
    work_path.parent.mkdir(parents=True, exist_ok=True)
    target = float(target_video_s)
    bases_dir = (bases_dir or base_path.parent).expanduser().resolve()

    base_dur = _ffprobe_duration(base_path)
    meta: dict = {
        "code": _PREP_CODE,
        "base_clip": base_path.name,
        "base_duration_s": round(base_dur, 3),
        "target_video_s": round(target, 3),
    }

    if base_dur + 0.05 >= target:
        trimmed = work_path.with_name(f"{work_path.stem}_trim{work_path.suffix}")
        _trim_to_duration(base_path, trimmed, target)
        submit, size_meta = _fit_submit_size(trimmed, work_path, duration_s=target)
        meta.update({
            "strategy": "trim_long_base",
            "submit_path": submit.name,
            **size_meta,
        })
        return submit, meta

    unit = resolve_phase_b_loop_unit(bases_dir)
    unit_dur = _ffprobe_duration(unit)
    looped = work_path.with_name(f"{work_path.stem}_from_unit{work_path.suffix}")
    crossfade_loop_video(unit, looped, target, xfade_s=0.7)
    looped_dur = _ffprobe_duration(looped)
    submit, size_meta = _fit_submit_size(looped, work_path, duration_s=looped_dur)
    meta.update({
        "strategy": "auto_loop_bookend_unit",
        "loop_unit": unit.name,
        "loop_unit_duration_s": round(unit_dur, 3),
        "looped_duration_s": round(looped_dur, 3),
        "submit_path": submit.name,
        **size_meta,
    })
    return submit, meta
