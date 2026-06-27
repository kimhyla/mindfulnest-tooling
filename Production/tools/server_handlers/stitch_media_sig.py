"""STITCH_SLOT_MEDIA_ARTIFACTS_V1 — shared mix_sig for server + client artifact invalidation."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

STITCH_SLOT_MEDIA_ARTIFACTS_V1 = "STITCH_SLOT_MEDIA_ARTIFACTS_V1"
STITCH_MUX_VIDEO_LINEAGE_V1 = "STITCH_MUX_VIDEO_LINEAGE_V1"
STITCH_WAVEFORM_MIX_MONO_V1 = "mono_v3"

from server_handlers.stitch_ambient_loop import ambient_loop_sig_token  # noqa: E402

STITCH_SFX_CUE_DEFAULT_VOLUME = 0.45
STITCH_SFX_CUE_DEFAULT_FADEIN_MS = 300
STITCH_SFX_CUE_DEFAULT_FADEOUT_MS = 1200
STITCH_AMBIENT_BED_VOLUME = 0.15

STITCH_AMBIENT_BAKE_ON_SAVE_V1 = "STITCH_AMBIENT_BAKE_ON_SAVE_V1"
# load_job trusts persisted sig + lineage pins; skips ffprobe/decode on hot open.
STITCH_LOAD_JOB_FAST_V1 = "STITCH_LOAD_JOB_FAST_V1"
STITCH_AMBIENT_MUX_LEGACY_CLEARED_V1 = "stitch_ambient_mux_legacy_cleared_v1"

STITCH_SLOT_ARTIFACT_FIELDS = (
    "mix_sig",
    "ambient_mix_sig",
    "ambient_mix_hash",
    "ambient_mix_duration_ms",
    "ambient_mix_video_path",
    "ambient_mix_video_mtime_ms",
    "waveform_peaks_hash",
    "waveform_peaks_duration_s",
    "mux_preview_hash",
    "mux_preview_duration_ms",
    "mux_video_path",
    "mux_video_mtime_ms",
    "media_artifacts_built_at",
    STITCH_AMBIENT_MUX_LEGACY_CLEARED_V1,
)

STITCH_SLOT_AMBIENT_MIX_FIELDS = (
    "ambient_mix_sig",
    "ambient_mix_hash",
    "ambient_mix_duration_ms",
    "ambient_mix_video_path",
    "ambient_mix_video_mtime_ms",
)

STITCH_SLOT_MUX_FIELDS = (
    "mux_preview_hash",
    "mux_preview_duration_ms",
    "mux_video_path",
    "mux_video_mtime_ms",
)


def _video_mtime_ms(abs_video_path: str) -> int:
    try:
        return int(os.path.getmtime(abs_video_path) * 1000)
    except OSError:
        return 0


def stitch_sfx_cue_sig_parts(cues: list | None) -> list[str]:
    parts: list[str] = []
    for i, cue in enumerate(cues or []):
        if not isinstance(cue, dict):
            continue
        parts.append(
            f"{cue.get('id', i)}:"
            f"{cue.get('offset_ms', 0)}:"
            f"{cue.get('duration_ms', '')}:"
            f"{float(cue.get('volume', STITCH_SFX_CUE_DEFAULT_VOLUME)):.4f}:"
            f"{int(cue.get('fadein_ms', STITCH_SFX_CUE_DEFAULT_FADEIN_MS))}:"
            f"{int(cue.get('fadeout_ms', STITCH_SFX_CUE_DEFAULT_FADEOUT_MS))}:"
            f"{cue.get('source_path', '')}"
        )
    parts.sort()
    return parts


def compute_stitch_mix_sig(
    *,
    video_path: str,
    video_mtime_ms: int,
    ambient_bed: str = "",
    ambient_bed_path: str = "",
    ambient_volume: float = STITCH_AMBIENT_BED_VOLUME,
    sfx_cues: list | None = None,
    base_sig: str = "",
) -> str:
    """Stable mix geometry + source identity for artifact invalidation."""
    ambient = (ambient_bed_path or ambient_bed or "").strip()
    vol = f"{float(ambient_volume):.4f}"
    parts = [
        STITCH_SLOT_MEDIA_ARTIFACTS_V1,
        STITCH_WAVEFORM_MIX_MONO_V1,
        ambient_loop_sig_token(),
        (video_path or "").strip(),
        str(int(video_mtime_ms or 0)),
        base_sig,
        ambient,
        vol,
        *stitch_sfx_cue_sig_parts(sfx_cues),
    ]
    digest = hashlib.sha256("|".join(parts).encode(), usedforsecurity=False).hexdigest()
    return digest[:16]


def compute_stitch_ambient_mix_sig_from_slot(
    h,
    slot: dict,
    *,
    video_abs_path: str | Path | None = None,
) -> str:
    """Ambient-layer sig only (no SFX cues) — STITCH_AMBIENT_BAKE_ON_SAVE_V1."""
    video_path = (slot.get("video_path") or "").strip()
    mtime_ms = 0
    if video_abs_path:
        mtime_ms = _video_mtime_ms(str(video_abs_path))
    elif video_path and hasattr(h, "_stitch_resolve_path"):
        try:
            abs_path = h._stitch_resolve_path(video_path)
            mtime_ms = _video_mtime_ms(abs_path)
        except (ValueError, TypeError, OSError):
            mtime_ms = 0
    ambient_bed = (slot.get("ambient_bed") or "").strip()
    ambient_path = (slot.get("ambient_bed_path") or "").strip()
    vol = float(slot.get("ambient_volume", STITCH_AMBIENT_BED_VOLUME))
    return compute_stitch_mix_sig(
        video_path=video_path,
        video_mtime_ms=mtime_ms,
        ambient_bed=ambient_bed,
        ambient_bed_path=ambient_path,
        ambient_volume=vol,
        sfx_cues=[],
    )


def compute_stitch_mix_sig_from_slot(
    h,
    slot: dict,
    *,
    video_abs_path: str | Path | None = None,
) -> str:
    """Compute mix_sig from a stitch job slot dict."""
    video_path = (slot.get("video_path") or "").strip()
    mtime_ms = 0
    if video_abs_path:
        mtime_ms = _video_mtime_ms(str(video_abs_path))
    elif video_path and hasattr(h, "_stitch_resolve_path"):
        try:
            abs_path = h._stitch_resolve_path(video_path)
            mtime_ms = _video_mtime_ms(abs_path)
        except (ValueError, TypeError, OSError):
            mtime_ms = 0
    ambient_bed = (slot.get("ambient_bed") or "").strip()
    ambient_path = (slot.get("ambient_bed_path") or "").strip()
    vol = float(slot.get("ambient_volume", STITCH_AMBIENT_BED_VOLUME))
    cues = [c for c in (slot.get("sfx_cues") or []) if isinstance(c, dict)]
    return compute_stitch_mix_sig(
        video_path=video_path,
        video_mtime_ms=mtime_ms,
        ambient_bed=ambient_bed,
        ambient_bed_path=ambient_path,
        ambient_volume=vol,
        sfx_cues=cues,
    )


def waveform_mix_hash_parts(
    base_sig: str,
    video_dur_ms: int,
    ambient_path: str,
    ambient_volume: float,
    sfx_cues: list,
) -> list[str]:
    """Cache key parts aligned with _mix_stitch_waveform_audio."""
    parts = [
        base_sig,
        STITCH_WAVEFORM_MIX_MONO_V1,
        ambient_loop_sig_token(),
        str(video_dur_ms),
        ambient_path,
        f"{ambient_volume:.4f}",
    ]
    parts.extend(stitch_sfx_cue_sig_parts(sfx_cues))
    return parts


def waveform_mix_hash_from_parts(parts: list[str]) -> str:
    import hashlib as _hl  # noqa: PLC0415

    return _hl.md5("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:12]


def clear_stitch_slot_mux_artifacts(slot: dict) -> None:
    if not isinstance(slot, dict):
        return
    for field in STITCH_SLOT_MUX_FIELDS:
        slot.pop(field, None)
    slot.pop("_mux_preview_url", None)


def clear_stitch_slot_ambient_mix_artifacts(slot: dict) -> None:
    if not isinstance(slot, dict):
        return
    for field in STITCH_SLOT_AMBIENT_MIX_FIELDS:
        slot.pop(field, None)
    slot.pop("_ambient_mix_url", None)


def clear_stitch_slot_media_artifacts(slot: dict) -> None:
    if not isinstance(slot, dict):
        return
    for field in STITCH_SLOT_ARTIFACT_FIELDS:
        slot.pop(field, None)
    slot.pop("_mux_preview_url", None)
    slot.pop("_waveform_peaks_url", None)
    slot.pop("_ambient_mix_url", None)
