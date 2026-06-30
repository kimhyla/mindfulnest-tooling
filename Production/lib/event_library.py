"""Per-event image/watercolor library paths + canonical image registry."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

REGISTRY_FILENAME = "canonical_image_registry.json"
BASELINE_REGISTRY_FILENAME = "baseline_image_registry.json"
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


def baseline_images_dir(prod_root: Path | str) -> Path:
    return Path(prod_root) / "assets" / "image_library" / "baseline"


def baseline_registry_path(prod_root: Path | str) -> Path:
    return Path(prod_root) / BASELINE_REGISTRY_FILENAME


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


_WC_SEED_EXTS = (".png", ".webp", ".mp4", ".mov")


def _list_watercolor_seed_files(wc_dir: Path) -> list[Path]:
    if not wc_dir.is_dir():
        return []
    return sorted(
        p
        for p in wc_dir.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in _WC_SEED_EXTS
    )


def _default_watercolor_template_dir(prod_root: Path) -> Path | None:
    """First Event_* dir (sorted) whose library/watercolors/ is non-empty."""
    events_root = prod_root / "Production" if (prod_root / "Production").is_dir() else prod_root
    for event_dir in sorted(events_root.glob("Event_*")):
        if not event_dir.is_dir() or event_dir.name.endswith("_Plans"):
            continue
        wc_dir = event_watercolors_dir(event_dir)
        if _list_watercolor_seed_files(wc_dir):
            return event_dir
    return None


def seed_event_watercolors_if_empty(
    event_dir: Path | str,
    *,
    template_event_dir: Path | str | None = None,
    prod_root: Path | str | None = None,
) -> int:
    """Copy template watercolor assets when target event has none (EVENT_WC_SEED_V1).

    Returns number of files copied. Skips when target already has watercolor files.
    """
    import shutil

    ev = Path(event_dir)
    target = event_watercolors_dir(ev)
    target.mkdir(parents=True, exist_ok=True)
    if _list_watercolor_seed_files(target):
        return 0

    template = Path(template_event_dir) if template_event_dir else None
    if template is None:
        root = Path(prod_root) if prod_root else ev.parent
        template = _default_watercolor_template_dir(root)
    if template is None:
        return 0

    src_dir = event_watercolors_dir(template)
    copied = 0
    for src in _list_watercolor_seed_files(src_dir):
        dest = target / src.name
        if dest.exists():
            continue
        shutil.copy2(src, dest)
        copied += 1
    return copied


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
        if not entry.get("apply_to_all_events"):
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


def load_baseline_registry(prod_root: Path | str) -> dict[str, Any]:
    path = baseline_registry_path(prod_root)
    if not path.is_file():
        return {"version": 0, "images": []}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_baseline_meta(prod_root: Path | str) -> list[dict[str, Any]]:
    """Shared BG still metadata rows — apply_to_all_events baseline set."""
    registry = load_baseline_registry(prod_root)
    if not registry.get("apply_to_all_events", True):
        return []
    out: list[dict[str, Any]] = []
    for img in registry.get("images") or []:
        if isinstance(img, dict) and img.get("filename"):
            out.append(img)
    return out


def is_baseline_image_path(abs_path: str, prod_root: Path | str) -> bool:
    if not abs_path:
        return False
    try:
        resolved = os.path.realpath(abs_path)
        root = os.path.realpath(str(baseline_images_dir(prod_root)))
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
    baseline_dir = baseline_images_dir(prod)
    if baseline_dir.is_dir():
        roots.append(os.path.realpath(str(baseline_dir)))
    if char_assets.is_dir():
        roots.append(os.path.realpath(str(char_assets)))
    # Element @Image1 pose PNGs live under Production/<Char>/poses/ — not in
    # per-event library/ but must render Char ref thumbnails after migrate align.
    try:
        for child in prod.iterdir():
            if not child.is_dir():
                continue
            poses = child / "poses"
            if poses.is_dir():
                roots.append(os.path.realpath(str(poses)))
    except OSError:
        pass
    stills_root = prod / "beat_generator_stills"
    if stills_root.is_dir():
        roots.append(os.path.realpath(str(stills_root)))
        for sub in ("crops", "sources"):
            sub_dir = stills_root / sub
            if sub_dir.is_dir():
                roots.append(os.path.realpath(str(sub_dir)))
    return roots


def resolve_ref_image_open_path(abs_path: str, approved_roots: list[str]) -> str:
    """Return realpath safe to open when abs_path is under an approved root, else ''."""
    if not isinstance(abs_path, str) or not abs_path:
        return ""
    try:
        resolved = os.path.realpath(abs_path)
    except OSError:
        return ""
    if not resolved:
        return ""
    for root in approved_roots:
        if not root:
            continue
        try:
            root_resolved = os.path.realpath(root)
        except OSError:
            continue
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            return resolved
    return ""


def ref_image_thumb_b64(abs_path: str, approved_roots: list[str]) -> str | None:
    """Render a JPEG data-URI thumbnail for an approved ref image path."""
    safe_path = resolve_ref_image_open_path(abs_path, approved_roots)
    if not safe_path or not os.path.isfile(safe_path):
        return None
    try:
        import base64
        import io

        from PIL import Image

        with Image.open(safe_path) as im:
            im.thumbnail((200, 150), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except (OSError, ImportError, ValueError):
        return None


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
        baseline_images_dir(prod_root),
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
