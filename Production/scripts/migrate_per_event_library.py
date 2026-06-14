#!/usr/bin/env python3
"""One-time migration: shared library → per-event Event_1 library + canonical images.

Moves:
  Production/beat_generator_stills/sources/* → Event_1/library/images/sources/
  Production/beat_generator_stills/crops/*   → Event_1/library/images/crops/
  Production/assets/watercolor_library/*     → Event_1/library/watercolors/

Installs canonical images + registry under Production/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore

HERE = Path(__file__).resolve().parent
TOOLING_ROOT = HERE.parent.parent
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

from Production.lib.paths import DROPBOX_ROOT, EVENT_DIR  # noqa: E402
from Production.lib.event_library import (  # noqa: E402
    canonical_images_dir,
    canonical_registry_path,
    ensure_event_library_dirs,
)

ASSETS = Path(
    "/Users/kimberlysmith/.cursor/projects/Users-kimberlysmith-Projects-MindfulNest/assets"
)

CANONICAL_SOURCES = [
    (
        "canonical_arlo_mirror_v1.png",
        ASSETS / "ChatGPT_Image_Jun_10__2026__10_25_11_AM-04977789-0caa-4dbb-a6e4-621e98ea1929.png",
    ),
    (
        "canonical_arlo_neutral_v1.png",
        DROPBOX_ROOT / "Production" / "Arlo" / "poses" / "arlo_canonical_neutral_vest.png",
    ),
    (
        "canonical_heartwood_grove_01.png",
        ASSETS / "ChatGPT_Image_Jun_3__2026__05_00_00_PM-808c0f01-d6d6-4d25-a77d-72e83dc6b2d3.png",
    ),
    (
        "canonical_heartwood_grove_02.png",
        ASSETS / "ChatGPT_Image_Jun_3__2026__05_01_56_PM__2_-63ae6fbb-6045-4ab3-a7b6-bd3b9dcd9385.png",
    ),
    (
        "canonical_heartwood_grove_03.png",
        ASSETS / "ChatGPT_Image_Jun_3__2026__05_01_56_PM__3_-fd4ec4eb-0a66-4c8a-ac8a-3da205d17ac5.png",
    ),
    (
        "canonical_heartwood_grove_04.png",
        ASSETS / "ChatGPT_Image_Jun_3__2026__05_01_57_PM__4_-585d524e-65c9-4299-964b-9107bed6b6ba.png",
    ),
]


def _convert_to_png(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Image is None:
        shutil.copy2(src, dest)
        return
    with Image.open(src) as im:
        im.convert("RGB").save(dest, format="PNG")


def _move_dir_contents(src_dir: Path, dest_dir: Path, dry_run: bool) -> int:
    if not src_dir.is_dir():
        return 0
    moved = 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if not item.is_file() or item.name.startswith("."):
            continue
        target = dest_dir / item.name
        if target.exists():
            print(f"[skip] already exists: {target}")
            continue
        print(f"[move] {item} -> {target}")
        if not dry_run:
            shutil.move(str(item), str(target))
        moved += 1
    return moved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    prod = DROPBOX_ROOT / "Production"
    event1 = EVENT_DIR(1)
    legacy_stills = prod / "beat_generator_stills"
    legacy_wc = prod / "assets" / "watercolor_library"

    ensure_event_library_dirs(event1)
    ensure_event_library_dirs(EVENT_DIR(2))

    img_root = event1 / "library" / "images"
    moved_sources = _move_dir_contents(
        legacy_stills / "sources", img_root / "sources", args.dry_run
    )
    moved_crops = _move_dir_contents(
        legacy_stills / "crops", img_root / "crops", args.dry_run
    )
    moved_wc = _move_dir_contents(
        legacy_wc, event1 / "library" / "watercolors", args.dry_run
    )

    can_dir = canonical_images_dir(prod)
    can_dir.mkdir(parents=True, exist_ok=True)
    installed = 0
    for dest_name, src in CANONICAL_SOURCES:
        dest = can_dir / dest_name
        if not src.is_file():
            print(f"[error] missing canonical source: {src}", file=sys.stderr)
            return 1
        print(f"[canonical] {src.name} -> {dest}")
        if not args.dry_run:
            _convert_to_png(src, dest)
        installed += 1

    registry_src = TOOLING_ROOT / "Production" / "canonical_image_registry.json"
    registry_dest = canonical_registry_path(prod)
    print(f"[registry] {registry_src} -> {registry_dest}")
    if not args.dry_run:
        shutil.copy2(registry_src, registry_dest)
        with registry_dest.open(encoding="utf-8") as f:
            json.load(f)

    print(
        json.dumps(
            {
                "ok": True,
                "moved_sources": moved_sources,
                "moved_crops": moved_crops,
                "moved_watercolors": moved_wc,
                "canonical_installed": installed,
                "event1_images_dir": str(img_root),
                "canonical_dir": str(can_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
