"""AUTO_LOUDNORM_V1 — speech-bus loudnorm before ambient/SFX mix.

See Production/docs/TECH_SPEC_AUTO_LOUDNORM_V1.md.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from credentials_lib.ffmpeg_stitch import _has_audio_stream

STITCH_SPEECH_LOUDNORM_V1 = "STITCH_SPEECH_LOUDNORM_V1"
DEFAULT_SPEECH_LUFS = -19.0
DEFAULT_SPEECH_TP = -1.5
DEFAULT_SPEECH_LRA = 11.0


def speech_loudnorm_fingerprint(src: Path, *, recipe: str = STITCH_SPEECH_LOUDNORM_V1) -> str:
    """Stable cache key from source file identity + recipe."""
    st = src.stat()
    raw = f"{recipe}|{src.resolve()}|{st.st_mtime_ns}|{st.st_size}"
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]


def speech_loudnorm_cache_path(cache_dir: Path, src: Path, *, recipe: str = STITCH_SPEECH_LOUDNORM_V1) -> Path:
    fp = speech_loudnorm_fingerprint(src, recipe=recipe)
    return cache_dir / f"speech_ln_{fp}{src.suffix}"


def slot_video_skips_layer_b_speech_loudnorm(video_path: str) -> bool:
    """Layer A already leveled per-beat clips inside Beat Gen concat exports."""
    name = Path(video_path).name
    return "_kling_o3_" in name or name.endswith("_kling_o3.mp4")


def apply_speech_loudnorm_to_mp4(
    input_path: Path,
    *,
    output_path: Path | None = None,
    cache_dir: Path | None = None,
    target_lufs: float = DEFAULT_SPEECH_LUFS,
    target_tp: float = DEFAULT_SPEECH_TP,
    target_lra: float = DEFAULT_SPEECH_LRA,
    force: bool = False,
    recipe: str = STITCH_SPEECH_LOUDNORM_V1,
) -> tuple[Path, bool]:
    """Level speech audio only (`-c:v copy`). Returns (path, applied).

    Skips when no audio stream. Uses cache_dir output when provided and hash matches.
    """
    src = input_path.resolve()
    if not src.is_file():
        raise FileNotFoundError(f"speech loudnorm input missing: {src}")

    if not _has_audio_stream(src):
        return src, False

    out = output_path
    if out is None and cache_dir is not None:
        out = speech_loudnorm_cache_path(cache_dir, src, recipe=recipe)
    if out is None:
        out = src.with_name(f"{src.stem}_speech_ln{src.suffix}")

    out = out.resolve()
    if out.is_file() and not force:
        if out.stat().st_mtime >= src.stat().st_mtime and out.stat().st_size > 0:
            return out, False

    cache_dir and cache_dir.mkdir(parents=True, exist_ok=True)
    safe_in = os.path.realpath(str(src))
    safe_out = os.path.realpath(str(out))
    af = f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}:print_format=summary"
    cmd = [
        "ffmpeg", "-y",
        "-i", safe_in,
        "-af", af,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        safe_out,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"speech loudnorm ffmpeg failed: {err}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("speech loudnorm ffmpeg timed out (>600s)") from exc

    if not out.is_file() or out.stat().st_size <= 0:
        raise RuntimeError(f"speech loudnorm produced no output: {out}")

    return out, True


def apply_speech_loudnorm_export_beat_clip(
    clip_path: Path,
    *,
    beat_id: str,
    scratch_dir: Path,
    force: bool = False,
) -> Path:
    """Layer A — per-beat before Beat Gen concat."""
    out_dir = scratch_dir / "_speech_ln"
    out_dir.mkdir(parents=True, exist_ok=True)
    fp = speech_loudnorm_fingerprint(clip_path)
    cached = out_dir / f"{beat_id}_speech_ln_{fp}.mp4"
    leveled, applied = apply_speech_loudnorm_to_mp4(
        clip_path,
        output_path=cached,
        force=force,
    )
    if applied:
        print(f"[export] speech loudnorm {beat_id} ok → {leveled.name}", flush=True)
    return leveled
