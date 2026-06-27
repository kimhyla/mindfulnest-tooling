"""Canonical Phase A/B watercolor asset contract — keys, resolve, URLs.

Single module for list APIs, serve handlers, ffmpeg bake, and client parity tests.
Legacy files keep human filename stems on disk; new uploads get slug filenames.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

WC_STATIC_EXTS = (".png", ".webp")
WC_ANIM_EXTS = (".mov", ".mp4")
WC_ALL_EXTS = WC_STATIC_EXTS + WC_ANIM_EXTS

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug_watercolor_key(name: str) -> str:
    """Stable slug for new uploads — lowercase, underscores, no spaces."""
    stem = Path(name).stem if "." in name else name
    slug = _SLUG_RE.sub("_", stem.lower()).strip("_")
    return slug or "watercolor"


def watercolor_file_api_path(key: str) -> str:
    """Relative GET path for static thumb / PNG serve (query param key)."""
    return f"/api/phase/watercolor_file?key={urllib.parse.quote(key, safe='')}"


def watercolor_serve_api_path(key: str) -> str:
    """Relative GET path for phase_b/watercolor/<key> serve (path segment)."""
    return f"/api/phase_b/watercolor/{urllib.parse.quote(key, safe='')}"


def _kind_for_ext(ext: str) -> str:
    return "animation" if ext.lower() in (".mov", ".mp4") else "static"


def resolve_watercolor_path(
    library_dir: Path | str,
    key: str,
    *,
    prefer_animation: bool = True,
) -> Path:
    """Resolve cue/list key to an on-disk file under library_dir.

    prefer_animation=False (thumb/static overlay PNG): static exts first.
    prefer_animation=True (serve/bake): MP4/MOV over PNG when both exist.
    """
    if not key or not isinstance(key, str):
        raise ValueError(f"key must be non-empty string, got {key!r}")
    key = urllib.parse.unquote(key)
    lib = Path(library_dir)
    if not lib.is_dir():
        raise FileNotFoundError(f"watercolor library dir missing: {lib}")

    key_path = Path(key)
    if key_path.suffix.lower() in WC_ALL_EXTS:
        candidate = lib / key_path.name
        if candidate.is_file():
            return candidate.resolve()
        raise FileNotFoundError(f"watercolor asset not found: {candidate}")

    exts = WC_ALL_EXTS if prefer_animation else WC_STATIC_EXTS
    matches = [m for m in lib.glob(f"{key}.*") if m.suffix.lower() in exts]
    if matches:
        if prefer_animation:
            return _pick_preferred_match(matches).resolve()
        return matches[0].resolve()

    # Slug alias (legacy list keys with underscores vs spaced filenames)
    slug = slug_watercolor_key(key)
    if slug != key:
        matches = [m for m in lib.glob(f"{slug}.*") if m.suffix.lower() in exts]
        if matches:
            if prefer_animation:
                return _pick_preferred_match(matches).resolve()
            return matches[0].resolve()

    key_lower = key.lower()
    for f in lib.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in exts and not (
            prefer_animation and f.suffix.lower() in WC_ANIM_EXTS
        ):
            continue
        if f.stem == key or f.stem.lower() == key_lower:
            return f.resolve()
        if slug_watercolor_key(f.stem) == slug:
            return f.resolve()

    if not prefer_animation:
        return resolve_watercolor_path(library_dir, key, prefer_animation=True)

    raise FileNotFoundError(
        f"watercolor asset not found for key={key!r} under {lib}",
    )


def _pick_preferred_match(matches: list[Path]) -> Path:
    """Prefer animated MP4/MOV over static PNG when multiple extensions share a stem."""
    anim = next((m for m in matches if m.suffix.lower() in WC_ANIM_EXTS), None)
    png = next((m for m in matches if m.suffix.lower() in WC_STATIC_EXTS), None)
    return anim or png or matches[0]


def _animation_thumb_stem(key: str, static_stems: set[str]) -> str:
    base = re.sub(r"_animated_\d{8}-\d{6}$", "", key)
    return base if base in static_stems else key


def list_watercolor_items(library_dir: Path | str) -> list[dict]:
    """Inventory rows for cr_library + phase/watercolor_list (same shape)."""
    wc_dir = Path(library_dir)
    if not wc_dir.is_dir():
        return []

    static_stems = {
        p.stem
        for p in wc_dir.iterdir()
        if p.is_file() and p.suffix.lower() in WC_STATIC_EXTS and not p.name.startswith("_smoketest_")
    }
    items: list[dict] = []
    for f in sorted(wc_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in WC_ALL_EXTS:
            continue
        if f.name.startswith("_smoketest_") or f.stat().st_size == 0:
            continue
        key = f.stem
        kind = _kind_for_ext(ext)
        thumb_key = _animation_thumb_stem(key, static_stems) if kind == "animation" else key
        items.append({
            "key": key,
            "filename": f.name,
            "ext": ext.lstrip("."),
            "kind": kind,
            "tier": "watercolor",
            "tags": ["watercolor"],
            "asset_type": "watercolor_static" if kind == "static" else "watercolor_animation",
            "thumb_url": watercolor_file_api_path(thumb_key),
            "animation_url": watercolor_serve_api_path(key) if kind == "animation" else None,
            "mtime": int(f.stat().st_mtime),
            "size_bytes": f.stat().st_size,
            "abs_path": str(f.resolve()),
        })
    return items


def upload_watercolor_filename(original_filename: str) -> str:
    """Destination filename for new watercolor uploads (slug + preserve ext)."""
    base = Path(original_filename).name
    ext = Path(base).suffix.lower()
    if ext not in WC_STATIC_EXTS:
        ext = ".png"
    return f"{slug_watercolor_key(base)}{ext}"
