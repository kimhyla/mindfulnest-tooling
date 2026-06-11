#!/usr/bin/env python3
"""Build phase_a_chipper_closeup_crop_v4.png — desk scene (v3) + hidden-hands neutral.

Image-swap only: same 800×600 miracle framing; replaces claw-hand bird pixels with
Jun 8 chipper_canonical_neutral.png (feather-tip wings). Does not touch pipeline code.

v2 composite (2026-06-09): direct alpha paste + slight alpha dilation — no ellipse blur
(the v1 brown halo came from Gaussian-blurring the desk under a large oval mask).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
EVENT = PROD / "Event_1"
V3 = EVENT / "phase_a_chipper_closeup_crop_v3.png"
NEUTRAL = PROD / "Chipper/poses/chipper_canonical_neutral.png"
OUT = EVENT / "phase_a_chipper_closeup_crop_v4.png"
MANIFEST = EVENT / "phase_a_chipper_closeup_crop_v4.manifest.json"

# Bird footprint on v3 closeup (800×600).
BIRD_MASK_CENTER = (500, 300)
BIRD_MASK_AXES = (210, 270)
TARGET_BIRD_HEIGHT = 500
DESK_FOOT_Y = 532
# Dilate neutral alpha to fully cover old claw pixels at wing edges.
ALPHA_DILATE_PX = 9
# Tight feather on old-bird removal (not the v1 16+22px desk smear).
REMOVE_FEATHER_PX = 4


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def neutral_rgba(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)
    white = (arr[:, :, 0] > 235) & (arr[:, :, 1] > 235) & (arr[:, :, 2] > 235)
    arr[white, 3] = 0
    return Image.fromarray(arr)


def build_v4() -> dict:
    if not V3.is_file():
        sys.exit(f"FATAL: missing {V3}")
    if not NEUTRAL.is_file():
        sys.exit(f"FATAL: missing {NEUTRAL}")

    v3 = Image.open(V3).convert("RGBA")
    if v3.size != (800, 600):
        sys.exit(f"FATAL: v3 size {v3.size}, expected (800, 600)")

    neutral = neutral_rgba(NEUTRAL)
    scale = TARGET_BIRD_HEIGHT / neutral.height
    nw, nh = int(neutral.width * scale), int(neutral.height * scale)
    bird = neutral.resize((nw, nh), Image.LANCZOS)

    # Slight alpha dilation covers v3 claw fringe without blurring the desk plate.
    alpha = bird.split()[3]
    k = ALPHA_DILATE_PX if ALPHA_DILATE_PX % 2 else ALPHA_DILATE_PX + 1
    alpha = alpha.filter(ImageFilter.MaxFilter(k))
    bird.putalpha(alpha)

    paste_x = BIRD_MASK_CENTER[0] - nw // 2
    paste_y = DESK_FOOT_Y - nh

    # Hard-clear old claw-hand bird: fill removal oval with local desk tone (not whole-scene blur).
    remove = Image.new("L", v3.size, 0)
    draw = ImageDraw.Draw(remove)
    draw.ellipse(
        (
            BIRD_MASK_CENTER[0] - BIRD_MASK_AXES[0],
            BIRD_MASK_CENTER[1] - BIRD_MASK_AXES[1],
            BIRD_MASK_CENTER[0] + BIRD_MASK_AXES[0],
            BIRD_MASK_CENTER[1] + BIRD_MASK_AXES[1],
        ),
        fill=255,
    )
    if REMOVE_FEATHER_PX > 0:
        remove = remove.filter(ImageFilter.GaussianBlur(radius=REMOVE_FEATHER_PX))

    desk_patch = np.array(v3.crop((220, 520, 680, 598)))[:, :, :3]
    desk_color = desk_patch.mean(axis=(0, 1)).astype(np.uint8)

    arr = np.array(v3.convert("RGB"))
    m = np.array(remove, dtype=np.float32) / 255.0
    for c in range(3):
        arr[:, :, c] = (arr[:, :, c] * (1 - m) + desk_color[c] * m).astype(np.uint8)
    base = Image.fromarray(arr).convert("RGBA")
    base.paste(bird, (paste_x, paste_y), bird)

    out_rgb = base.convert("RGB")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out_rgb.save(OUT, format="PNG", optimize=True)

    manifest = {
        "artifact": "phase_a_chipper_closeup_crop_v4.png",
        "classification": "hidden_hands_desk_still_v4",
        "method": "v3_desk_scene + jun8_neutral_composite_v3_desk_fill",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size": list(out_rgb.size),
        "composite_v3": {
            "alpha_dilate_px": ALPHA_DILATE_PX,
            "remove_feather_px": REMOVE_FEATHER_PX,
            "target_bird_height": TARGET_BIRD_HEIGHT,
            "desk_fill_not_scene_blur": True,
        },
        "sources": {
            "v3": {"path": str(V3.relative_to(PROD)), "md5": md5(V3)},
            "neutral": {"path": str(NEUTRAL.relative_to(PROD)), "md5": md5(NEUTRAL)},
        },
        "output_md5": md5(OUT),
        "pipeline_note": "Miracle pipeline unchanged — swap still only; base regen uses phase_a_chipper_lipsync_base.py",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    m = build_v4()
    print(json.dumps(m, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
