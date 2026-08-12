#!/usr/bin/env python3
"""One-shot installer for versioned Arlo layered runtime assets."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from PIL import Image
import numpy as np

_DROPBOX = Path(
    os.environ.get(
        "MN_DROPBOX_ROOT",
        str(Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"),
    )
)
ROOT = _DROPBOX / "Production" / "NEW STYLE CHARACTERS"
ARLO = ROOT / "ARLO"
KEY_RGB = (6, 239, 10)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    ARLO.mkdir(parents=True, exist_ok=True)
    src_idle = ROOT / "arlo idle.mp4"
    dst_idle = ARLO / "arlo_fullbody_idle_green_1916x1080_v1.mp4"
    if not dst_idle.exists():
        shutil.copy2(src_idle, dst_idle)
        print("installed idle", dst_idle, dst_idle.stat().st_size)
    else:
        print("idle exists", dst_idle.stat().st_size)

    key = ARLO / "arlo_key_canvas_1280x720_v1.png"
    image = Image.new("RGB", (1280, 720), KEY_RGB)
    image.save(key)
    pixels = np.asarray(image)
    assert pixels.shape == (720, 1280, 3)
    assert (pixels == KEY_RGB).all()
    print("installed key canvas", key, key.stat().st_size)

    plate = ARLO / "arlo_room_plate_chair_study_1280x720_v2.png"
    if not plate.is_file():
        raise SystemExit(f"missing room plate: {plate}")

    for path in sorted(ARLO.glob("*.png")):
        print("png:", path.name, path.stat().st_size)

    manifest = {
        "schema_version": 1,
        "profile": "arlo",
        "route": "PHASE_A_ARLO_LAYERED_ROUTE_V1",
        "assets": {
            "idle": {
                "path": (
                    "NEW STYLE CHARACTERS/ARLO/"
                    "arlo_fullbody_idle_green_1916x1080_v1.mp4"
                ),
                "role": "fullbody_green_idle",
                "sha256": sha256_file(dst_idle),
                "bytes": dst_idle.stat().st_size,
                "width": 1916,
                "height": 1080,
                "fps": 24,
                "duration_s": 15.041667,
            },
            "room_plate": {
                "path": (
                    "NEW STYLE CHARACTERS/ARLO/"
                    "arlo_room_plate_chair_study_1280x720_v2.png"
                ),
                "role": "static_room_plate_chair_study",
                "sha256": sha256_file(plate),
                "bytes": plate.stat().st_size,
                "width": 1280,
                "height": 720,
            },
            "key_canvas": {
                "path": "NEW STYLE CHARACTERS/ARLO/arlo_key_canvas_1280x720_v1.png",
                "role": "pure_key_canvas",
                "sha256": sha256_file(key),
                "bytes": key.stat().st_size,
                "width": 1280,
                "height": 720,
                "key_rgb": list(KEY_RGB),
            },
        },
    }
    manifest_path = ARLO / "arlo_layered_assets_v1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("wrote manifest", manifest_path)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
