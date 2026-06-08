"""Shared Phase A stitch input resolution — pinned state beats glob."""
from __future__ import annotations

from pathlib import Path


def _state_get(state: dict, key: str) -> str | None:
    val = state.get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()
    nested = state.get("phase_a") or {}
    if isinstance(nested, dict):
        val = nested.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def resolve_phase_a_flyin(event_dir: Path, state: dict) -> Path | None:
    """Prefer pinned phase_a_flyin_file; else newest phase_a_flyin*.mp4."""
    pinned = _state_get(state, "phase_a_flyin_file")
    if pinned:
        p = event_dir / pinned
        if p.is_file():
            return p
    matches = sorted(
        event_dir.glob("phase_a_flyin*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def resolve_phase_a_flyout(event_dir: Path, state: dict) -> Path | None:
    """Prefer pinned phase_a_flyout_file; else newest shippable fly-out.

    Includes closeup_match_* names (not only phase_a_flyout_v*).
    Prefers non-kling post-processed variants when globbing.
    """
    pinned = _state_get(state, "phase_a_flyout_file")
    if pinned:
        p = event_dir / pinned
        if p.is_file():
            return p
    all_out = sorted(
        event_dir.glob("phase_a_flyout*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    non_kling = [p for p in all_out if "kling" not in p.name.lower()]
    pool = non_kling or all_out
    return pool[0] if pool else None


def resolve_phase_a_raw_lipsync(event_dir: Path) -> Path | None:
    """Newest phase_a_lipsync_*.mp4 without 'withbed' in the name."""
    matches = sorted(
        (p for p in event_dir.glob("phase_a_lipsync_*.mp4")
         if "withbed" not in p.name.lower()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None
