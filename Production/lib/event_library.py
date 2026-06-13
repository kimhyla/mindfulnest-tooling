"""Per-event image/watercolor library paths + canonical image registry (arcs 1–2)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

REGISTRY_FILENAME = "canonical_image_registry.json"
_IMAGE_EXTS = (".webp", ".png", ".jpg", ".jpeg")


def event_images_dir(event_dir: Path | str) -> Path:
    return Path(event_dir) / "library" / "images"


def event_images_sources_dir(event_dir: Path | str) -> Path:
    return event_images_dir(event_dir) / "sources"


def event_images_crops_dir(event_dir: Path | str) -> Path:
    return event_images_dir(event_dir) / "crops"


def event_watercolors_dir(event_dir: Path | str) -> Path:
    return Path(event_dir) / "library" / "watercolors"


def canonical_images_dir(prod_root: Path | str) -> Path:
    return Path(prod_root) / "canonical_images"


def canonical_registry_path(prod_root: Path | str) -> Path:
    return Path(prod_root) / REGISTRY_FILENAME


def arc_number_from_event_id(event_id: str) -> int:
    """Map Event_N folder name to arc number (Event_1 → 1, Event_2 → 2)."""
    m = re.search(r"(\d+)", str(event_id))
    return int(m.group(1)) if m else 1


def ensure_event_library_dirs(event_dir: Path | str) -> None:
    ev = Path(event_dir)
    for d in (
        event_images_dir(ev),
        event_images_sources_dir(ev),
        event_images_crops_dir(ev),
        event_watercolors_dir(ev),
    ):
        d.mkdir(parents=True, exist_ok=True)


def load_canonical_registry(prod_root: Path | str) -> dict[str, Any]:
    path = canonical_registry_path(prod_root)
    if not path.is_file():
        return {"version": 0, "sets": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def canonical_meta_for_arc(prod_root: Path | str, arc_number: int) -> list[dict[str, Any]]:
    registry = load_canonical_registry(prod_root)
    out: list[dict[str, Any]] = []
    for entry in registry.get("sets") or []:
        arcs = entry.get("arc_numbers") or []
        if arc_number not in arcs:
            continue
        for img in entry.get("images") or []:
            if isinstance(img, dict) and img.get("filename"):
                out.append(img)
    return out


def is_canonical_image_path(abs_path: str, prod_root: Path | str) -> bool:
    if not abs_path:
        return False
    try:
        resolved = os.path.realpath(abs_path)
        root = os.path.realpath(str(canonical_images_dir(prod_root)))
        return os.path.commonpath([resolved, root]) == root
    except (OSError, ValueError):
        return False


def library_image_roots(event_dir: Path | str, prod_root: Path | str) -> list[str]:
    """Approved roots for image library path confinement (per active event)."""
    ev = Path(event_dir)
    prod = Path(prod_root)
    char_assets = prod / "Character_Assets"
    roots = [
        os.path.realpath(str(event_images_dir(ev))),
        os.path.realpath(str(event_images_sources_dir(ev))),
        os.path.realpath(str(event_images_crops_dir(ev))),
        os.path.realpath(str(canonical_images_dir(prod))),
    ]
    if char_assets.is_dir():
        roots.append(os.path.realpath(str(char_assets)))
    return roots


def resolve_library_image_path(
    image_key: str,
    event_dir: Path | str,
    prod_root: Path | str,
) -> str | None:
    normalized = image_key.replace(" ", "_")
    candidate_dirs = [
        event_images_dir(event_dir),
        event_images_sources_dir(event_dir),
        event_images_crops_dir(event_dir),
        canonical_images_dir(prod_root),
        Path(prod_root) / "Character_Assets",
    ]
    for d in candidate_dirs:
        if not d.is_dir():
            continue
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for fname in entries:
            if not fname.lower().endswith(_IMAGE_EXTS):
                continue
            stem = os.path.splitext(fname)[0]
            if stem == image_key or stem.replace(" ", "_") == normalized:
                return str(d / fname)
        for fname in entries:
            if not fname.lower().endswith(_IMAGE_EXTS):
                continue
            stem = os.path.splitext(fname)[0]
            if stem.startswith(image_key + "_") or stem.startswith(normalized + "_"):
                return str(d / fname)
    return None
