#!/usr/bin/env python3
"""Tiny local proof for Chipper beak-only Rhubarb animation.

This is deliberately not the production Phase A button path. It makes a small,
disposable review packet so failure is visible in minutes and never mutates
production_state.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from rhubarb_processor import (  # noqa: E402
    composite_static_plate_rhubarb,
    default_rhubarb_bin,
)

DROPBOX_PROD = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)
REVIEW_TIMES_S = (0.5, 1.5, 2.5, 3.5, 4.5)


def _run(cmd: list[str], *, timeout: int = 120) -> None:
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(r.stdout.strip() or "0")


def _load_sprites(event_dir: Path, config: dict) -> dict[str, Path]:
    sprites_dir = event_dir / config.get("sprites_dir", "chipper_beak_sprites")
    sprites = {letter: sprites_dir / f"chipper_beak_{letter}.png" for letter in "ABCDEF"}
    missing = [str(path) for path in sprites.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing beak sprites: {missing}")
    return sprites


def _make_audio_snippet(src: Path, dst: Path, *, start_s: float, duration_s: float) -> None:
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}",
        "-i", str(src),
        "-ar", "44100", "-ac", "1", "-c:a", "libmp3lame", "-q:a", "2",
        str(dst),
    ])


def _make_static_original(plate: Path, audio: Path, dst: Path, *, fps: float) -> None:
    duration_s = _ffprobe_duration(audio)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", f"{fps:.3f}", "-t", f"{duration_s:.3f}",
        "-i", str(plate),
        "-i", str(audio),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart",
        str(dst),
    ])


def _make_side_by_side(left: Path, right: Path, dst: Path) -> None:
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(left), "-i", str(right),
        "-filter_complex",
        (
            "[0:v]scale=640:480,setsar=1[l];"
            "[1:v]scale=640:480,setsar=1[r];"
            "[l][r]hstack=inputs=2[v]"
        ),
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart",
        str(dst),
    ])


def _extract_frames(video: Path, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[str] = []
    for t in REVIEW_TIMES_S:
        dst = out_dir / f"t{t:.1f}s.png"
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(dst),
        ])
        frames.append(str(dst))
    return frames


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--event-dir", type=Path, default=DROPBOX_PROD / "Event_1")
    ap.add_argument("--audio", type=Path, default=None)
    ap.add_argument("--plate", type=Path, default=None)
    ap.add_argument("--start-s", type=float, default=0.7)
    ap.add_argument("--duration-s", type=float, default=5.0)
    ap.add_argument("--fps", type=float, default=24.0)
    args = ap.parse_args()

    event_dir = args.event_dir.expanduser().resolve()
    config_path = event_dir / "chipper_beak_config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"missing config: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sprites = _load_sprites(event_dir, config)

    plate = (args.plate or event_dir / config.get("body_plate", "phase_a_chipper_body_plate_v1.png")).resolve()
    audio = (args.audio or event_dir / "phase_a_voice_stem_20260606-234239.mp3").resolve()
    if not plate.is_file():
        raise FileNotFoundError(f"missing plate: {plate}")
    if not audio.is_file():
        raise FileNotFoundError(f"missing audio: {audio}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = event_dir / "phase_a_beak_rig_proofs" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_snip = out_dir / "proof_audio.mp3"
    original = out_dir / "proof_original_static.mp4"
    rig = out_dir / "proof_beak_rig.mp4"
    side_by_side = out_dir / "proof_side_by_side.mp4"

    _make_audio_snippet(audio, audio_snip, start_s=args.start_s, duration_s=args.duration_s)
    _make_static_original(plate, audio_snip, original, fps=args.fps)
    result = composite_static_plate_rhubarb(
        plate_path=plate,
        audio_path=audio_snip,
        beak_config=config,
        sprites=sprites,
        output_path=rig,
        fps=args.fps,
        rhubarb_bin=default_rhubarb_bin(),
    )
    _make_side_by_side(original, rig, side_by_side)
    frames = _extract_frames(side_by_side, out_dir / "frames")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": "phase_a_beak_rig_tiny_proof",
        "mutates_production_state": False,
        "event_dir": str(event_dir),
        "audio_source": str(audio),
        "audio_start_s": args.start_s,
        "audio_duration_s": round(_ffprobe_duration(audio_snip), 3),
        "plate": str(plate),
        "config": str(config_path),
        "sprites": {k: str(v) for k, v in sprites.items()},
        "rhubarb": result,
        "outputs": {
            "audio": str(audio_snip),
            "original_static": str(original),
            "beak_rig": str(rig),
            "side_by_side": str(side_by_side),
            "frames": frames,
        },
        "review_instruction": (
            "Reject if the beak looks pasted on, if face/body pixels jump, "
            "or if mouth timing does not visibly track the short audio."
        ),
    }
    manifest_path = out_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "manifest": str(manifest_path), **manifest["outputs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
