"""LIBRARY_PANEL_CLASSIFICATION_V1 — server authority for library panel tabs.

Every GET /api/cr/library row carries ``panel_tabs`` so the client never
infers visibility from Directus ``asset_type`` or duplicated tier maps.
"""

from __future__ import annotations

from typing import Any

# Mirrors LibraryPanel.tsx LIBRARY_TIERS (Kim BS3 lock 2026-05-06).
LIBRARY_PANEL_TABS: tuple[str, ...] = (
    "images",
    "ambient",
    "sfx",
    "transitions",
    "watercolors",
)

_IMAGES_DISK_TIERS = frozenset({"source", "cropped", "character_master", "element_pose"})


def panel_tabs_for_cr_library_row(item: dict[str, Any]) -> list[str]:
    """Return panel tab ids for one cr_library list row (may be empty)."""
    tier = str(item.get("tier") or "")
    if tier == "canonical":
        return []
    if tier == "watercolor":
        return ["watercolors"]
    if tier in _IMAGES_DISK_TIERS:
        return ["images"]
    tags = item.get("tags") or []
    if isinstance(tags, list) and "watercolor" in tags:
        return ["watercolors"]
    asset_type = str(item.get("asset_type") or "")
    if asset_type in ("watercolor_static", "watercolor"):
        return ["watercolors"]
    if asset_type in ("audio",):
        return ["ambient"] if "ambient" in tags else []
    if asset_type in ("sfx", "transition"):
        return ["sfx"] if asset_type == "sfx" else ["transitions"]
    # Unknown disk tier — default to images so rows are never silently hidden.
    if tier:
        return ["images"]
    return []


def attach_panel_tabs(item: dict[str, Any]) -> dict[str, Any]:
    """Mutate and return *item* with ``panel_tabs`` set from disk-scan tier."""
    tabs = panel_tabs_for_cr_library_row(item)
    if tabs:
        item["panel_tabs"] = tabs
    else:
        item.pop("panel_tabs", None)
    return item


def attach_panel_tabs_all(items: list[dict[str, Any]]) -> None:
    for item in items:
        attach_panel_tabs(item)


def row_matches_panel_filter(item: dict[str, Any], panel: str) -> bool:
    tabs = item.get("panel_tabs")
    if isinstance(tabs, list) and tabs:
        return panel in tabs
    return panel in panel_tabs_for_cr_library_row(item)
