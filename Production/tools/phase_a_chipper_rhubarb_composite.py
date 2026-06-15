#!/usr/bin/env python3
"""Phase A Chipper middle — Rhubarb beak compositing on frozen body plate.

Tier B pipeline: no Kling/ByteDance lipsync API calls.

Usage:
  python3 phase_a_chipper_rhubarb_composite.py
  python3 phase_a_chipper_rhubarb_composite.py --audio Event_1/phase_a_voice_stem_*.mp3
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from rhubarb_processor import composite_static_plate_rhubarb, default_rhubarb_bin  # noqa: E402

DROPBOX_PROD = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)


def log(msg: str) -> None:
    print(f"[phase_a_rhubarb] {msg}", flush=True)


def _load_config(event_dir: Path) -> dict:
    path = event_dir / "chipper_beak_config.json"
    if not path.is_file():
        raise SystemExit(
            f"Missing {path.name} — run phase_a_chipper_beak_prep.py first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_sprites(event_dir: Path, config: dict) -> dict[str, Path]:
    sprites_dir = event_dir / config.get("sprites_dir", "chipper_beak_sprites")
    sprites: dict[str, Path] = {}
    for letter in "ABCDEF":
        p = sprites_dir / f"chipper_beak_{letter}.png"
        if p.is_file():
            sprites[letter] = p
    if not sprites:
        raise SystemExit(f"No sprites in {sprites_dir}")
    return sprites


def _newest_voice_stem(event_dir: Path) -> Path:
    matches = sorted(
        event_dir.glob("phase_a_voice_stem_*.mp3"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise SystemExit(f"No phase_a_voice_stem_*.mp3 in {event_dir}")
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase A Rhubarb beak composite")
    ap.add_argument("--event-dir", type=Path, default=DROPBOX_PROD / "Event_1")
    ap.add_argument("--audio", type=Path, default=None)
    ap.add_argument("--plate", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--fps", type=float, default=25.0)
    args = ap.parse_args()

    event_dir = args.event_dir
    config = _load_config(event_dir)
    sprites = _load_sprites(event_dir, config)

    plate = args.plate or event_dir / config.get("body_plate", "phase_a_chipper_body_plate_v1.png")
    audio = args.audio or _newest_voice_stem(event_dir)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or event_dir / "phase_a_idle_candidates" / f"chipper_lipsync_rhubarb_{ts}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    if not plate.is_file():
        log(f"FATAL: body plate missing: {plate}")
        return 1
    if not audio.is_file():
        log(f"FATAL: audio missing: {audio}")
        return 1

    rhubarb_bin = default_rhubarb_bin()
    log(f"rhubarb: {rhubarb_bin}")
    log(f"plate: {plate.name}")
    log(f"audio: {audio.name}")
    log(f"sprites: {len(sprites)} ({', '.join(sorted(sprites))})")

    result = composite_static_plate_rhubarb(
        plate_path=plate,
        audio_path=audio,
        beak_config=config,
        sprites=sprites,
        output_path=out,
        fps=args.fps,
        rhubarb_bin=rhubarb_bin,
    )

    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline": "rhubarb_tier_b",
        "output": out.name,
        "plate": plate.name,
        "audio": audio.name,
        "config": "chipper_beak_config.json",
        **result,
    }
    manifest_path = out.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    log(f"output: {out} ({result['duration_s']}s, {result['mouth_cue_count']} cues)")
    log(f"phonemes: {result.get('phoneme_distribution', {})}")
    log(f"manifest: {manifest_path.name}")
    print(json.dumps({"ok": True, "output": str(out), **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
