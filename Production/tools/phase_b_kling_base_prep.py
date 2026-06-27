"""Phase B Kling lipsync base prep — crossfade-loop short idle bases before submit.

PHASE_B_KLING_CROSSFADE_LOOP_V1: Kling's internal loop of a ~10s Cedric idle base
produces visible background rippling after the first cycle. Phase A already
crossfade-loops before ByteDance/Kling; Phase B must do the same, then re-encode
to stay under WaveSpeed's ~22MB raw data-URI ceiling.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from phase_a_av_post import crossfade_loop_video
from production_server import _ffprobe_duration

WAVESPEED_RAW_MB_CEILING = 22.0
_PREP_CODE = "PHASE_B_KLING_CROSSFADE_LOOP_V1"


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


def prep_phase_b_kling_base_video(
    base_path: Path,
    target_video_s: float,
    work_path: Path,
) -> tuple[Path, dict]:
    """Crossfade-loop (when needed) and size-cap encode for Kling Sync submit."""
    base_path = base_path.expanduser().resolve()
    work_path = work_path.expanduser().resolve()
    work_path.parent.mkdir(parents=True, exist_ok=True)

    raw_dur = _ffprobe_duration(base_path)
    raw_size_mb = base_path.stat().st_size / 1024 / 1024
    meta: dict = {
        "code": _PREP_CODE,
        "base_duration_s": round(raw_dur, 3),
        "target_video_s": round(float(target_video_s), 3),
        "raw_size_mb": round(raw_size_mb, 2),
    }

    looped = work_path.with_name(f"{work_path.stem}_xfade{work_path.suffix}")
    if raw_dur + 0.05 >= float(target_video_s):
        if raw_size_mb <= WAVESPEED_RAW_MB_CEILING:
            meta["strategy"] = "send_raw_trimmed_base"
            return base_path, meta
        out = work_path.with_name(f"{work_path.stem}_reenc{work_path.suffix}")
        bps = kling_submit_video_bitrate_bps(raw_dur)
        _reencode_for_kling_submit(base_path, out, video_bitrate_bps=bps)
        meta.update({
            "strategy": "reencode_short_base",
            "submit_path": out.name,
            "video_bitrate_bps": bps,
            "submit_size_mb": round(out.stat().st_size / 1024 / 1024, 2),
        })
        return out, meta

    crossfade_loop_video(base_path, looped, float(target_video_s))
    looped_mb = looped.stat().st_size / 1024 / 1024
    looped_dur = _ffprobe_duration(looped)
    meta["looped_size_mb"] = round(looped_mb, 2)
    meta["looped_duration_s"] = round(looped_dur, 3)

    if looped_mb <= WAVESPEED_RAW_MB_CEILING:
        meta["strategy"] = "crossfade_loop_send"
        meta["submit_path"] = looped.name
        return looped, meta

    bps = kling_submit_video_bitrate_bps(looped_dur)
    _reencode_for_kling_submit(looped, work_path, video_bitrate_bps=bps)
    submit_mb = work_path.stat().st_size / 1024 / 1024
    if submit_mb > WAVESPEED_RAW_MB_CEILING:
        raise RuntimeError(
            f"crossfade-looped base still {submit_mb:.1f}MB > "
            f"{WAVESPEED_RAW_MB_CEILING}MB after {bps:,} bps re-encode"
        )
    meta.update({
        "strategy": "crossfade_loop_reencode",
        "submit_path": work_path.name,
        "video_bitrate_bps": bps,
        "submit_size_mb": round(submit_mb, 2),
    })
    return work_path, meta
