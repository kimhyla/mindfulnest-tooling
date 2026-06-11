#!/usr/bin/env python3
"""Single-pass Kling LipSync for Chipper Phase A review (no stitch).

Kim 2026-06-08: trial Kling smooth pass on element-bound idle; fight teeth separately.

Usage:
  python3 phase_a_chipper_kling_lipsync.py \\
    --base-clip-id chipper_idle_element_v1 \\
    --out Event_1/phase_a_idle_candidates/chipper_lipsync_h_kling_20260608T012000Z.mp4
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import load_api_keys  # noqa: E402
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402


def log(msg: str) -> None:
    print(f"[phase_a_kling] {msg}", flush=True)

DROPBOX_PROD = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)
_WAVESPEED_RAW_MB_CEILING = 22.0


def _event_dir() -> Path:
    return DROPBOX_PROD / "Event_1"


def _resolve_base(bases_dir: Path, base_clip_id: str) -> Path:
    raw = bases_dir / base_clip_id
    if raw.is_file():
        return raw
    for ext in ("mp4", "mov"):
        candidate = bases_dir / f"{base_clip_id}.{ext}"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"base clip not found: {base_clip_id}")


def _prep_video_for_kling(base_path: Path, audio_duration: float, tmp_dir: Path) -> Path:
    raw_dur = ffprobe_duration(base_path)
    raw_size_mb = base_path.stat().st_size / 1024 / 1024
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_video = tmp_dir / f"_kling_prep_{base_path.stem}.mp4"

    if raw_dur < audio_duration + 2.0 and raw_size_mb <= _WAVESPEED_RAW_MB_CEILING:
        log(
            f"Kling prep: send raw base {raw_dur:.1f}s / {raw_size_mb:.1f}MB "
            f"(Kling loops internally for {audio_duration:.1f}s audio)"
        )
        return base_path

    if raw_size_mb > _WAVESPEED_RAW_MB_CEILING:
        log(f"Kling prep: re-encode {raw_size_mb:.1f}MB -> 2Mbps for API ceiling")
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(base_path),
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", "2000k", "-maxrate", "2000k", "-bufsize", "4000k",
                "-an", "-movflags", "+faststart", str(tmp_video),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return tmp_video

    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import production_server as ps  # noqa: WPS433

    ps._trim_video_to_audio(base_path, tmp_video, audio_duration, trim_start=0.0)
    log(f"Kling prep: trimmed base {raw_dur:.1f}s -> {audio_duration:.1f}s")
    return tmp_video


def run_kling_lipsync(
    base_video: Path,
    audio: Path,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
) -> Path:
    work = tmp_dir or (out_path.parent / "_tmp_phase_a_kling")
    work.mkdir(parents=True, exist_ok=True)
    audio_dur = ffprobe_duration(audio)
    video = _prep_video_for_kling(base_video, audio_dur, work)

    keys = load_api_keys()
    client = LipSyncClient(keys["wavespeed"])
    log(f"Kling submit: video={video.name} audio={audio.name} ({audio_dur:.1f}s)")
    job_id = client.submit(video, audio)
    result = client.poll_until_done(job_id)
    status = (result.get("status") or "").lower()
    if status != "completed" or not result.get("outputs"):
        raise RuntimeError(f"Kling lipsync failed: status={status!r} raw={result}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    client.download(result["outputs"][0], out_path)
    log(
        f"Kling complete: {out_path.name} "
        f"({out_path.stat().st_size / 1024 / 1024:.1f} MB, "
        f"{ffprobe_duration(out_path):.2f}s)"
    )
    return out_path


def resolve_lipsync_base(bases_dir: Path, base_clip_id: str) -> Path:
    """Resolve Production/assets/lipsync_bases/<id>.mp4|.mov."""
    raw = bases_dir / base_clip_id
    if raw.is_file():
        return raw
    for ext in ("mp4", "mov"):
        candidate = bases_dir / f"{base_clip_id}.{ext}"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"base clip not found: {base_clip_id}")


def run_phase_a_base_clip_lipsync(
    base_video: Path,
    audio_raw: Path,
    out_path: Path,
    *,
    tmp_dir: Path | None = None,
) -> dict:
    """Lipsync on a pre-made broader idle base clip — no idle regen, no Ken Burns zoom."""
    import json
    from datetime import datetime, timezone

    from phase_a_av_post import (
        av_duration_gap,
        pad_video_to_match_audio,
        trim_av_lead_in,
        upscale_lipsync_to_bookend,
    )
    from production_server import _ffprobe_duration, _silcomp_audio

    base_video = base_video.expanduser().resolve()
    audio_raw = audio_raw.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    work = tmp_dir or (out_path.parent / "_tmp_phase_a_base_lipsync")
    work.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    log(f"base clip: {base_video.name}")
    log(f"audio: {audio_raw.name}")

    raw_dur = _ffprobe_duration(audio_raw)
    tmp_audio = work / f"base_audio_{ts}.mp3"
    audio_for_lipsync, audio_proc_meta = _silcomp_audio(
        audio_raw,
        tmp_audio,
        loudnorm=True,
        auto_preroll=True,
        max_audio_s=raw_dur + 2.0,
    )
    pr = audio_proc_meta.get("preroll_processing") or {}
    preroll_s = float(pr.get("preroll_added_s") or 0.0)

    ls_raw = work / f"lipsync_raw_{tag}.mp4"
    run_kling_lipsync(base_video, audio_for_lipsync, ls_raw, tmp_dir=work)

    ls_upscaled = work / f"lipsync_bookend_{tag}.mp4"
    upscale_lipsync_to_bookend(ls_raw, ls_upscaled)

    padded = work / f"lipsync_padded_{tag}.mp4"
    _, pad_s = pad_video_to_match_audio(ls_upscaled, padded)
    trim_av_lead_in(padded, out_path, preroll_s)

    v_final, a_final, gap_final = av_duration_gap(out_path)
    manifest = {
        "pipeline": "phase_a_base_clip_kling_lipsync",
        "base_clip": base_video.name,
        "audio_source": audio_raw.name,
        "preroll_added_s": round(preroll_s, 3),
        "video_pad_s": round(pad_s, 3),
        "final_av_gap_s": round(gap_final, 3),
        "output": out_path.name,
        "method": "base_clip_kling_lipsync",
        "zoom": False,
        "upscale_bookend": True,
        "bookend_resolution": "1660x1244",
    }
    out_path.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    log(f"DONE base-clip lipsync → {out_path.name} (v={v_final:.2f}s a={a_final:.2f}s)")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-clip-id", default="chipper_idle_element_v1")
    p.add_argument(
        "--audio",
        help="Override audio path (default: phase_a_voice_stem from production_state)",
    )
    p.add_argument(
        "--out",
        help="Output mp4 (default: phase_a_idle_candidates/chipper_lipsync_h_kling_<ts>.mp4)",
    )
    args = p.parse_args()

    event = _event_dir()
    bases = DROPBOX_PROD / "assets" / "lipsync_bases"
    base_path = _resolve_base(bases, args.base_clip_id)

    if args.audio:
        audio_path = Path(args.audio).expanduser()
    else:
        import json

        state = json.loads((event / "production_state.json").read_text())
        audio_name = state.get("phase_a_voice_stem_file")
        if not audio_name:
            log("FATAL: phase_a_voice_stem_file unset")
            return 1
        audio_path = event / audio_name

    if not audio_path.is_file():
        log(f"FATAL: audio not found: {audio_path}")
        return 1

    if args.out:
        out_path = Path(args.out).expanduser()
        if not out_path.is_absolute():
            out_path = DROPBOX_PROD / out_path
    else:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = event / "phase_a_idle_candidates" / f"chipper_lipsync_h_kling_{ts}.mp4"

    try:
        run_kling_lipsync(base_path, audio_path, out_path)
    except Exception as exc:  # noqa: BLE001
        log(f"FATAL: {type(exc).__name__}: {exc}")
        return 1
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
