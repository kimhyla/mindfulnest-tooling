#!/usr/bin/env python3
"""Prepare Chipper beak sprites from Kim's ChatGPT stills.

Classifies 6 Jun 7 2026 mouth-variation PNGs into Preston Blair A–F,
crops beak region, removes white background, writes chipper_beak_*.png.

Usage:
  python3 phase_a_chipper_beak_prep.py
  python3 phase_a_chipper_beak_prep.py --source-dir "..." --event-dir "..."
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
DROPBOX_PROD = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
)

# Verified classification from visual inspection (Jun 8 2026).
# Source: NEW STYLE CHARACTERS/CHIPPER/ChatGPT Image Jun 7, 2026, 11_17_* PM (*.png)
CLASSIFICATION: list[dict] = [
    {
        "phoneme": "A",
        "source_suffix": "11_17_46 PM (1).png",
        "mouth_shape": "closed_rest",
        "also_maps": ["X"],
        "notes": "Beak fully closed, neutral rest pose. Used for silence (X) too.",
    },
    {
        "phoneme": "B",
        "source_suffix": "11_17_46 PM (2).png",
        "mouth_shape": "slightly_parted",
        "notes": "Small gap at beak tip; Preston Blair B (F/V fricatives).",
    },
    {
        "phoneme": "C",
        "source_suffix": "11_17_47 PM (3).png",
        "mouth_shape": "open_medium",
        "also_maps": ["G"],
        "notes": "Moderate open with tongue visible; maps Rhubarb G→C.",
    },
    {
        "phoneme": "D",
        "source_suffix": "11_17_47 PM (4).png",
        "mouth_shape": "wide_open",
        "also_maps": ["H"],
        "notes": "Widest open beak; vowels ah/oh; maps Rhubarb H→D.",
    },
    {
        "phoneme": "E",
        "source_suffix": "11_17_48 PM (5).png",
        "mouth_shape": "small_round_o",
        "notes": "Small circular O mouth; oo/w sounds.",
    },
    {
        "phoneme": "F",
        "source_suffix": "11_17_48 PM (6).png",
        "mouth_shape": "lower_beak_down",
        "notes": "Lower beak dropped, tongue visible; L/TH variant.",
    },
]

# Normalized crop on 1254×1254 bust stills (beak + lower face, excludes eyes).
BEAK_CROP_FRAC = {
    "x0": 0.36,
    "y0": 0.52,
    "x1": 0.64,
    "y1": 0.74,
}


def log(msg: str) -> None:
    print(f"[beak_prep] {msg}", flush=True)


def _white_to_alpha(img: Image.Image, threshold: int = 235) -> Image.Image:
    rgba = img.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= threshold and g >= threshold and b >= threshold:
                px[x, y] = (r, g, b, 0)
    return rgba.filter(ImageFilter.GaussianBlur(radius=0.5))


def _crop_beak(img: Image.Image) -> Image.Image:
    w, h = img.size
    x0 = int(BEAK_CROP_FRAC["x0"] * w)
    y0 = int(BEAK_CROP_FRAC["y0"] * h)
    x1 = int(BEAK_CROP_FRAC["x1"] * w)
    y1 = int(BEAK_CROP_FRAC["y1"] * h)
    return img.crop((x0, y0, x1, y1))


def find_source(source_dir: Path, suffix: str) -> Path:
    matches = [p for p in source_dir.iterdir() if p.name.endswith(suffix)]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected exactly one file ending with {suffix!r} in {source_dir}, "
            f"found {len(matches)}: {[p.name for p in matches]}"
        )
    return matches[0]


def run_prep(*, source_dir: Path, event_dir: Path) -> dict:
    sprites_dir = event_dir / "chipper_beak_sprites"
    sprites_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[dict] = []
    for entry in CLASSIFICATION:
        src = find_source(source_dir, entry["source_suffix"])
        crop = _crop_beak(Image.open(src))
        rgba = _white_to_alpha(crop)
        out_name = f"chipper_beak_{entry['phoneme']}.png"
        out_path = sprites_dir / out_name
        rgba.save(out_path)
        log(f"{entry['phoneme']} ← {src.name} → {out_path.name} ({rgba.size[0]}×{rgba.size[1]})")
        outputs.append({
            **entry,
            "source_file": src.name,
            "output_file": out_name,
            "pixel_size": list(rgba.size),
        })

    # Beak placement on 1280×960 body plate — measured from dark-beak centroid.
    config = {
        "character": "chipper",
        "version": 1,
        "beak_cx_frac": 0.535,
        "beak_cy_frac": 0.460,
        "sprite_w_frac": 0.22,
        "sprite_h_frac": 0.14,
        "sprites_dir": "chipper_beak_sprites",
        "body_plate": "phase_a_chipper_body_plate_v1.png",
        "beak_crop_frac": BEAK_CROP_FRAC,
        "note": "Placement from body_plate dark-beak centroid; tune beak_cy_frac if overlay sits high/low.",
    }
    config_path = event_dir / "chipper_beak_config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    log(f"config: {config_path.name}")

    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dir": str(source_dir),
        "sprites_dir": str(sprites_dir),
        "classification": outputs,
        "config_file": config_path.name,
        "preston_blair_map": {
            "A": "M,B,P,rest,silence(X)",
            "B": "F,V",
            "C": "open + G fallback",
            "D": "wide vowels + H fallback",
            "E": "OO,W",
            "F": "L,TH",
        },
    }
    manifest_path = event_dir / "chipper_beak_classification.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    log(f"manifest: {manifest_path.name}")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare Chipper Rhubarb beak sprites")
    ap.add_argument(
        "--source-dir",
        type=Path,
        default=DROPBOX_PROD / "NEW STYLE CHARACTERS" / "CHIPPER",
    )
    ap.add_argument("--event-dir", type=Path, default=DROPBOX_PROD / "Event_1")
    args = ap.parse_args()
    if not args.source_dir.is_dir():
        log(f"FATAL: source dir missing: {args.source_dir}")
        return 1
    run_prep(source_dir=args.source_dir, event_dir=args.event_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
