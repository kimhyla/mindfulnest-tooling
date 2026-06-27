#!/usr/bin/env python3
"""POV motion clip — Kling O3 Pro single-frame image-to-video + optional Beat Gen slot import.

Validated recipe: wand POV windshield-wiper (Jun 2026). Not Avatar Pro, not Element
native, not Still Insert Ken Burns.

Usage:
  # Generate only (writes manifest + raw + delivery mp4 under --out-dir):
  python3 run_o3_pov_motion_i2v.py \\
    --image /path/to/pov_still.png \\
    --out-dir ~/Projects/MindfulNest/.runtime_wand_wiper

  # Generate + import into Beat Gen slot (milestone sidecar):
  python3 run_o3_pov_motion_i2v.py \\
    --image /path/to/pov_still.png \\
    --out-dir ~/Projects/MindfulNest/.runtime_wand_wiper \\
    --import-beat bg_arc1_event3b_full_beat_10 \\
    --slot 2 \\
    --milestone milestone1_arc1 \\
    --event-dir Event_1

  # Import an existing delivery mp4 (skip WaveSpeed):
  python3 run_o3_pov_motion_i2v.py \\
    --delivery-mp4 /path/to/clip_delivery.mp4 \\
    --import-beat bg_arc1_event3b_full_beat_10 \\
    --slot 2 \\
    --milestone milestone1_arc1 \\
    --event-dir Event_1
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
REPO_ROOT = TOOLS.parent.parent  # mindfulnest-tooling
PROD_ROOT = TOOLS.parent  # Production/
for p in (str(TOOLS), str(PROD_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from PIL import Image

DEFAULT_PROMPT = (
    "First-person POV shot. Camera completely locked — no zoom, no pan, no camera move, "
    "no parallax drift. Child's hand at bottom-right of frame grips a magic wand with a "
    "large glowing green crystal tip. The hand and wand sweep smoothly left and right in "
    "wide arcs like windshield wipers — two full back-and-forth cycles over the clip. "
    "Enchanted forest background with mossy tree trunks, turquoise river, and stone pillars "
    "stays perfectly static. Subtle magical glow pulses from the green crystal on each pass. "
    "Hand anatomy stable; wand is rigid gnarled wood with small green leaves. "
    "No dialogue, no voice, no music, no ambient sound. No face visible. "
    "Avoid: camera movement, zoom, morphing trees, bending wand, extra hands, talking."
)

DELIVERY_W = 1280
DELIVERY_H = 720


def _dropbox_production() -> Path:
    from Production.lib.paths import dropbox_root

    return dropbox_root() / "Production"


def prepare_still(src: Path, out_dir: Path) -> Path:
    """Upscale still to 1280×720 (LANCZOS) — matches delivery + Kling min-side rules."""
    out_dir.mkdir(parents=True, exist_ok=True)
    still_720 = out_dir / "pov_start_1280x720.png"
    img = Image.open(src).convert("RGB")
    img.resize((DELIVERY_W, DELIVERY_H), Image.LANCZOS).save(still_720, format="PNG")
    return still_720


def generate_clip(
    *,
    image: Path,
    out_dir: Path,
    prompt: str,
    duration: int,
    tier: str,
    sound: bool,
) -> dict:
    from kling_o3_client import run_single_image_generation
    from kling_startend_pipeline import load_api_keys
    from video_delivery import encode_delivery_video

    out_dir.mkdir(parents=True, exist_ok=True)
    still_720 = prepare_still(image, out_dir)
    keys = load_api_keys()
    api_key = keys.get("wavespeed") or keys.get("WAVESPEED_API_KEY")
    if not api_key:
        raise SystemExit("WAVESPEED_API_KEY not found in API_KEYS_MASTER.md")

    ts = int(time.time())
    settings = {
        "model": f"kling-video-o3-{tier}/image-to-video",
        "tier": tier,
        "mode": "o3_image_to_video_single",
        "duration_s": duration,
        "sound": sound,
        "shot_type": "customize",
        "input_still": str(still_720),
        "input_resolution": f"{DELIVERY_W}x{DELIVERY_H}",
        "delivery_profile": "voice_first_upscale",
        "delivery_target": "1280x720 H.264 <=1.9Mbps +faststart + sharpen",
        "prompt": prompt,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")

    raw_mp4 = out_dir / f"pov_motion_o3_{tier}_{ts}_raw.mp4"
    print(f"[pov-i2v] Submitting O3 {tier} single-frame i2v ({duration}s, sound={sound})…", flush=True)
    result = run_single_image_generation(
        api_key,
        prompt,
        still_720,
        raw_mp4,
        duration=duration,
        speaker=None,
        sound=sound,
        tier=tier,
    )
    if not result.get("ok"):
        settings["result"] = result
        (out_dir / "manifest.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        raise SystemExit(f"Generation failed: {result}")

    delivery_mp4 = out_dir / f"pov_motion_o3_{tier}_{ts}_delivery.mp4"
    encode_delivery_video(
        raw_mp4,
        delivery_mp4,
        include_audio=sound,
        sharpen=True,
        delivery_profile="voice_first_upscale",
    )
    settings.update(
        {
            "task_id": result.get("task_id"),
            "video_url": result.get("video_url"),
            "raw_mp4": str(raw_mp4),
            "delivery_mp4": str(delivery_mp4),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    (out_dir / "manifest.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"[pov-i2v] Raw: {raw_mp4}")
    print(f"[pov-i2v] Delivery: {delivery_mp4}")
    return settings


def import_to_beat_slot(
    *,
    delivery_mp4: Path,
    beat_id: str,
    slot_index: int,
    milestone_id: str,
    event_dir_name: str,
    label: str,
    make_active: bool,
    generation: int | None,
) -> dict:
    import beat_generator as bg

    prod = _dropbox_production()
    event_dir = prod / event_dir_name
    milestone_dir = prod / "Milestones" / milestone_id
    bg.init_bg_paths(str(event_dir), milestone_dir=str(milestone_dir), library_event_dir=str(event_dir))

    clips_dir = bg.kling_o3_clips_dir(event_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)

    sidecar_probe = bg.read_sidecar()
    _, beat_probe = bg.find_beat(sidecar_probe, beat_id)
    if not beat_probe:
        raise SystemExit(f"Beat {beat_id!r} not found in sidecar")

    if generation is not None:
        gen = generation
    else:
        gens = [
            bg._kling_o3_gen_from_video_path(str(o.get("video_path") or ""))
            for o in (beat_probe.get("kling_o3_options") or [])
            if isinstance(o, dict)
        ]
        gens = [g for g in gens if g is not None]
        gen = (max(gens) + 1) if gens else 1

    dest_name = f"{beat_id}_g{gen}_pov_wand_wiper_delivery.mp4"
    dest_path = clips_dir / dest_name
    shutil.copy2(delivery_mp4, dest_path)
    print(f"[pov-i2v] Copied delivery → {dest_path}")

    now = datetime.now(timezone.utc).isoformat()

    def mutator(beat: dict, _sidecar: dict) -> None:
        if str(beat.get("beat_id") or "") != beat_id:
            return
        bg.assign_kling_o3_option_to_slot(
            beat,
            slot_index,
            video_path=str(dest_path.resolve()),
            label=label,
            source="o3_pov_motion_i2v",
            now=now,
            make_active=make_active,
        )
        bg.normalize_kling_o3_option_slots(beat, _sidecar)
        bg.persist_o3_disk_enrich_on_beat(beat, event_dir)

    ok, beat = bg.update_beat_locked(beat_id, mutator)
    if not ok:
        raise SystemExit(f"Failed to update sidecar for beat {beat_id!r}")

    payload = {
        "ok": True,
        "beat_id": beat_id,
        "slot_index": slot_index,
        "video_path": str(dest_path.resolve()),
        "make_active": make_active,
        "kling_o3_video_path": beat.get("kling_o3_video_path") if beat else None,
    }
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="POV motion via Kling O3 Pro i2v + Beat Gen import")
    ap.add_argument("--image", type=Path, help="Source POV still (PNG/JPEG)")
    ap.add_argument("--delivery-mp4", type=Path, help="Skip generate; import this delivery mp4")
    ap.add_argument("--out-dir", type=Path, default=Path.cwd() / ".runtime_pov_motion")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--duration", type=int, default=5, choices=[5, 7, 10])
    ap.add_argument("--tier", default="pro", choices=["pro", "std"])
    ap.add_argument("--sound", action="store_true", help="Request Kling ambient audio (default: silent)")
    ap.add_argument("--import-beat", help="beat_id to receive clip in a video container")
    ap.add_argument("--slot", type=int, default=2, choices=[0, 1, 2])
    ap.add_argument("--milestone", default="milestone1_arc1")
    ap.add_argument("--event-dir", default="Event_1", help="Event folder name under Production/")
    ap.add_argument("--label", default="POV wand wiper (O3 i2v)")
    ap.add_argument("--make-active", action="store_true", help="Select imported clip as active pointer")
    ap.add_argument("--generation", type=int, help="Force gN in destination filename")
    ap.add_argument("--generate-only", action="store_true")
    args = ap.parse_args()

    delivery_path: Path | None = args.delivery_mp4
    manifest: dict | None = None

    if not delivery_path:
        if not args.image or not args.image.is_file():
            ap.error("--image is required unless --delivery-mp4 is set")
        manifest = generate_clip(
            image=args.image,
            out_dir=args.out_dir,
            prompt=args.prompt,
            duration=args.duration,
            tier=args.tier,
            sound=args.sound,
        )
        delivery_path = Path(manifest["delivery_mp4"])

    if args.import_beat and not args.generate_only:
        import_to_beat_slot(
            delivery_mp4=delivery_path,
            beat_id=args.import_beat,
            slot_index=args.slot,
            milestone_id=args.milestone,
            event_dir_name=args.event_dir,
            label=args.label,
            make_active=args.make_active,
            generation=args.generation,
        )
    elif args.import_beat and args.generate_only:
        print("[pov-i2v] --generate-only: skipped Beat Gen import")


if __name__ == "__main__":
    main()
