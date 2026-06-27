"""STITCH_SLOT_EDIT_DISPATCH_V1 — tiered artifact rebuild plan for stitch_save_job."""
from __future__ import annotations

from pathlib import Path
from typing import Any

STITCH_SLOT_EDIT_DISPATCH_V1 = "STITCH_SLOT_EDIT_DISPATCH_V1"

EDIT_KIND_SFX_GEOMETRY = "sfx_geometry"
EDIT_KIND_AMBIENT_GEOMETRY = "ambient_geometry"
EDIT_KIND_MIXED_GEOMETRY = "mixed_geometry"
EDIT_KIND_VIDEO_LINEAGE = "video_lineage"
EDIT_KIND_METADATA = "metadata"

VALID_EDIT_KINDS = frozenset({
    EDIT_KIND_SFX_GEOMETRY,
    EDIT_KIND_AMBIENT_GEOMETRY,
    EDIT_KIND_MIXED_GEOMETRY,
    EDIT_KIND_VIDEO_LINEAGE,
    EDIT_KIND_METADATA,
})


def _slot_dict(slot: Any) -> dict:
    return slot if isinstance(slot, dict) else {}


def stitch_sfx_geometry_sig(slot: dict) -> str:
    """Sorted SFX cue geometry fingerprint (server mirror of client live geometry SFX part)."""
    from server_handlers.stitch_media_sig import stitch_sfx_cue_sig_parts  # noqa: PLC0415

    cues = [c for c in (slot.get("sfx_cues") or []) if isinstance(c, dict)]
    return "|".join(stitch_sfx_cue_sig_parts(cues))


def ambient_tier_drifted(h, prev: dict, nxt: dict) -> bool:
    """True when ambient bed / volume / video lineage for ambient mix changed."""
    from server_handlers.stitch_media_sig import compute_stitch_ambient_mix_sig_from_slot  # noqa: PLC0415

    if (prev.get("video_path") or "").strip() != (nxt.get("video_path") or "").strip():
        return True
    if (prev.get("ambient_bed") or "").strip() != (nxt.get("ambient_bed") or "").strip():
        return True
    if float(prev.get("ambient_volume", 0.15)) != float(nxt.get("ambient_volume", 0.15)):
        return True
    return compute_stitch_ambient_mix_sig_from_slot(h, prev) != compute_stitch_ambient_mix_sig_from_slot(
        h, nxt,
    )


def sfx_tier_drifted(prev: dict, nxt: dict) -> bool:
    return stitch_sfx_geometry_sig(prev) != stitch_sfx_geometry_sig(nxt)


def ambient_artifact_fresh(h, slot: dict) -> bool:
    """True when persisted ambient mix hash matches sig and cache file is playable."""
    from server_handlers.stitch_editor import stitch_cached_mp4_playable  # noqa: PLC0415
    from server_handlers.stitch_media_sig import compute_stitch_ambient_mix_sig_from_slot  # noqa: PLC0415

    stored_sig = (slot.get("ambient_mix_sig") or "").strip()
    stored_hash = (slot.get("ambient_mix_hash") or "").strip()
    if not stored_sig or not stored_hash:
        return False
    if stored_sig != compute_stitch_ambient_mix_sig_from_slot(h, slot):
        return False
    cache_path = h._stitch_cache_dir() / f"se_slot_{stored_hash}.mp4"
    if not cache_path.is_file():
        return False
    dur_ms = int(slot.get("ambient_mix_duration_ms") or 0)
    if dur_ms <= 0:
        dur_ms = h._ffprobe_duration_ms(cache_path)
    return stitch_cached_mp4_playable(
        cache_path,
        expected_s=dur_ms / 1000.0 if dur_ms > 0 else None,
    )


def slot_needs_ambient_rebuild(h, prev: dict, nxt: dict) -> bool:
    """Ambient tier rebuild required (drift or missing/stale artifact)."""
    if not (nxt.get("video_path") or "").strip():
        return False
    if not (nxt.get("ambient_bed") or "").strip():
        return False
    if not ambient_tier_drifted(h, prev, nxt) and ambient_artifact_fresh(h, nxt):
        return False
    return True


def infer_edit_kind_from_slots(
    h,
    prev_slots: dict[str, dict],
    next_slots: dict[str, dict],
    touched_keys: list[str],
) -> str:
    ambient = False
    sfx = False
    video = False
    for key in touched_keys:
        prev = _slot_dict(prev_slots.get(key))
        nxt = _slot_dict(next_slots.get(key))
        if (prev.get("video_path") or "").strip() != (nxt.get("video_path") or "").strip():
            video = True
        if ambient_tier_drifted(h, prev, nxt):
            ambient = True
        if sfx_tier_drifted(prev, nxt):
            sfx = True
    if video:
        return EDIT_KIND_VIDEO_LINEAGE
    if ambient and sfx:
        return EDIT_KIND_MIXED_GEOMETRY
    if ambient:
        return EDIT_KIND_AMBIENT_GEOMETRY
    if sfx:
        return EDIT_KIND_SFX_GEOMETRY
    return EDIT_KIND_METADATA


def plan_stitch_save_dispatch(
    h,
    *,
    prev_slots: dict[str, dict],
    next_slots: dict[str, dict],
    touched_keys: list[str],
    edit_kind_hint: str | None = None,
) -> dict[str, Any]:
    """
    Return tier dispatch for stitch_save_job after JSON persist.

    - ambient_rebuild_keys: slots that need sync ambient ffmpeg
    - ambient_skip_keys: slots with fresh ambient artifact (no ffmpeg)
    - mux_rebuild_hint_keys: slots where client should queue stitch_preview (SFX/ambient drift)
    """
    ambient_rebuild: list[str] = []
    ambient_skip: list[str] = []
    mux_hint: list[str] = []

    for key in touched_keys:
        prev = _slot_dict(prev_slots.get(key))
        nxt = _slot_dict(next_slots.get(key))
        if not (nxt.get("video_path") or "").strip():
            continue

        if sfx_tier_drifted(prev, nxt) or ambient_tier_drifted(h, prev, nxt):
            mux_hint.append(key)

        if not (nxt.get("ambient_bed") or "").strip():
            continue

        if slot_needs_ambient_rebuild(h, prev, nxt):
            ambient_rebuild.append(key)
        else:
            ambient_skip.append(key)

    resolved_kind = (
        edit_kind_hint.strip()
        if edit_kind_hint and edit_kind_hint.strip() in VALID_EDIT_KINDS
        else None
    )
    inferred_kind = infer_edit_kind_from_slots(h, prev_slots, next_slots, touched_keys)

    return {
        "code": STITCH_SLOT_EDIT_DISPATCH_V1,
        "edit_kind_hint": resolved_kind,
        "edit_kind_inferred": inferred_kind,
        "ambient_rebuild_keys": ambient_rebuild,
        "ambient_skip_keys": ambient_skip,
        "mux_rebuild_hint_keys": mux_hint,
    }
