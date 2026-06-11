#!/usr/bin/env python3
"""Focused Arlo parity smokes for native Kling lip-sync vs WaveSpeed."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))

import beat_generator as bg_sidecar  # noqa: E402
from kling_native_lipsync_experiment import run_experiment  # noqa: E402
from lib.paths import EVENT_DIR  # noqa: E402


EVENT1 = Path(EVENT_DIR(1))
BEAT_10_INPUT = (
    EVENT1
    / "kling_o3_clips/bg_arc1_event1_pre_beat_10_arlo_pro_silent_o3_base_delivery_input.mp4"
)
BEAT_10_AUDIO = (
    EVENT1
    / "story_scene_tts_v2/storyboard_v59_prod/line_10_arlo_voice_lipsync_padded.mp3"
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def encode_720p(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", "slow", "-an", "-movflags", "+faststart",
        str(dst),
    ]
    subprocess.run(cmd, check=True, timeout=300)
    return dst


def run_case(
    *,
    case_id: str,
    route_id: str,
    video: Path,
    audio: Path,
    output_root: Path,
    model_name: str | None = None,
) -> dict:
    import os

    prev = os.environ.get("KLING_LIP_SYNC_MODEL_NAME")
    if model_name:
        os.environ["KLING_LIP_SYNC_MODEL_NAME"] = model_name
    else:
        os.environ.pop("KLING_LIP_SYNC_MODEL_NAME", None)
    try:
        manifest = run_experiment(
            route_id=route_id,
            beat_id=None,
            input_video=video,
            input_audio=audio,
            attempt_id=f"{case_id.lower()}_{utc_stamp()}",
            output_root=output_root,
            return_on_fail=True,
        )
    finally:
        if prev is None:
            os.environ.pop("KLING_LIP_SYNC_MODEL_NAME", None)
        else:
            os.environ["KLING_LIP_SYNC_MODEL_NAME"] = prev
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-dir", type=Path, default=EVENT1)
    args = parser.parse_args()
    bg_sidecar.init_bg_paths(args.event_dir)

    stamp = utc_stamp()
    root = args.event_dir / "kling_native_lipsync_experiments" / f"_arlo_parity_{stamp}"
    root.mkdir(parents=True, exist_ok=True)

    video_720 = root / "arlo_delivery_input_1280x720.mp4"
    encode_720p(BEAT_10_INPUT, video_720)

    cases = [
        ("AP-01", "native_kling_lip_sync_a2v", BEAT_10_INPUT, None, "Native URL on current 1920x1080 delivery input"),
        ("AP-02", "native_kling_lip_sync_a2v", video_720, None, "Native URL on 1280x720 re-encode of same clip"),
        ("AP-03", "wavespeed_kling_lipsync_baseline", video_720, None, "WaveSpeed control on 1280x720 re-encode"),
        ("AP-04", "native_kling_lip_sync_a2v", video_720, "kling-v2-master", "Native with model_name=kling-v2-master"),
        ("AP-05", "native_kling_lip_sync_a2v", video_720, "kling-v2-6", "Native with model_name=kling-v2-6"),
    ]

    results = []
    for case_id, route_id, video, model_name, purpose in cases:
        print(f"[parity] starting {case_id} route={route_id} video={video.name}", flush=True)
        manifest = run_case(
            case_id=case_id,
            route_id=route_id,
            video=video,
            audio=BEAT_10_AUDIO,
            output_root=root,
            model_name=model_name,
        )
        entry = {
            "case_id": case_id,
            "purpose": purpose,
            "route_id": route_id,
            "model_name": model_name,
            "manifest_path": str(Path(manifest["work_dir"]) / "manifest.json"),
            "status": manifest.get("status"),
            "passed_gate": manifest.get("passed_gate"),
            "error": manifest.get("error"),
            "error_code": manifest.get("error_code"),
            "poll_error": (manifest.get("poll") or {}).get("error"),
            "raw_min_dimension": (manifest.get("raw_profile") or {}).get("min_dimension"),
        }
        results.append(entry)
        print(json.dumps(entry, indent=2), flush=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(root),
        "source_video_1080": str(BEAT_10_INPUT),
        "source_video_720": str(video_720),
        "audio": str(BEAT_10_AUDIO),
        "cases": results,
    }
    report_path = root / "arlo_parity_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
