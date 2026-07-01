"""STITCH_FOUR_FILES_V1 — one baked MP4 per stitch slot (speech + ambient + SFX).

Authority: TECH_SPEC_STITCH_FOUR_FILES_V1.md (FF-036)
Rule: slot.video_path is playback is Bake Final input — or fail closed.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STITCH_FOUR_FILES_V1 = "STITCH_FOUR_FILES_V1"
STITCH_FOUR_FILES_PLAYBACK_RECIPE = STITCH_FOUR_FILES_V1
# FF-036 — four-files slots must never re-enter se_slot / mux_preview artifact tiers.
STITCH_FOUR_FILES_LEGACY_PURGE_V1 = "STITCH_FOUR_FILES_LEGACY_PURGE_V1"

_LEGACY_ARTIFACT_FIELDS = (
    "ambient_mix_hash",
    "ambient_mix_sig",
    "ambient_mix_duration_ms",
    "ambient_mix_video_path",
    "ambient_mix_video_mtime_ms",
    "mux_preview_hash",
    "mux_preview_duration_ms",
    "mux_video_path",
    "mux_video_mtime_ms",
    "mix_sig",
    "_ambient_mix_url",
    "_mux_preview_url",
)


def clear_legacy_playback_artifact_fields(slot: dict) -> None:
    """Remove superseded cache-authority fields from slot JSON."""
    for key in _LEGACY_ARTIFACT_FIELDS:
        slot.pop(key, None)


def slot_skips_legacy_playback_artifact_tiers(slot: dict | None) -> bool:
    """True when slot authority is baked playback MP4 only (no se_slot / mux ladder)."""
    return playback_recipe_is_four_files(slot)


def slot_had_legacy_playback_artifact_fields(slot: dict) -> bool:
    """True when any split-authority field is still present on slot JSON."""
    return any((slot.get(key) or "").strip() for key in _LEGACY_ARTIFACT_FIELDS if not key.startswith("_"))


def reconcile_four_files_slot_authority(slot: dict) -> bool:
    """Purge legacy artifact fields from four-files slots. Returns True if anything removed."""
    if not playback_recipe_is_four_files(slot):
        return False
    had_legacy = slot_had_legacy_playback_artifact_fields(slot)
    clear_legacy_playback_artifact_fields(slot)
    slot.pop("_waveform_peaks_url", None)
    return had_legacy


def slot_has_playback_mix_layers(slot: dict) -> bool:
    """True when ambient bed or SFX cues require ffmpeg mix (not plain copy)."""
    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
        _stitch_slot_has_ambient,
        _stitch_slot_has_sfx,
    )

    return _stitch_slot_has_ambient(slot) or _stitch_slot_has_sfx(slot)


def resolve_slot_playback_path(slot: dict) -> str:
    """Read gate — sole playback path for event slots under STITCH_FOUR_FILES_V1."""
    path = (slot.get("video_path") or "").strip()
    if not path:
        raise ValueError(f"{STITCH_FOUR_FILES_V1}: slot missing video_path")
    return path


def playback_recipe_is_four_files(slot: dict | None) -> bool:
    if not isinstance(slot, dict):
        return False
    return (slot.get("playback_recipe_version") or "").strip() == STITCH_FOUR_FILES_PLAYBACK_RECIPE


def bake_slot_playback_mp4(
    h,
    slot: dict,
    *,
    dry_video_path: Path,
    dest: Path,
) -> float:
    """Bake speech + ambient + SFX into dest. Input MUST be dry concat (never mixed video_path)."""
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        STITCH_EXPORT_AV_MAX_DRIFT_S,
        av_duration_drift_s,
    )
    from video_delivery import ensure_mp4_playback_timestamps  # noqa: PLC0415

    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dry_video_path.is_file():
        raise FileNotFoundError(f"dry export missing: {dry_video_path}")

    if slot_has_playback_mix_layers(slot):
        cache_dir = h._stitch_cache_dir()
        mixed = h._stitch_mix_slot_audio(
            dry_video_path,
            slot,
            cache_dir,
            force_rebuild=True,
        )
        if mixed.resolve() != dest.resolve():
            shutil.copy2(mixed, dest)
    else:
        shutil.copy2(dry_video_path, dest)

    ensure_mp4_playback_timestamps(dest)
    drift = av_duration_drift_s(dest)
    if drift > STITCH_EXPORT_AV_MAX_DRIFT_S:
        try:
            dest.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"{STITCH_FOUR_FILES_V1}: playback bake A/V drift {drift:.3f}s "
            f"> {STITCH_EXPORT_AV_MAX_DRIFT_S}s ({dest.name})",
        )
    return h._ffprobe_duration_ms(dest) / 1000.0


def _assembled_playback_dest(h, slot_key: str) -> tuple[Path, str]:
    """Return (absolute dest, project-relative path) for a new playback MP4."""
    event_dir = Path(h.app.event_dir)
    assembled = event_dir / "assembled"
    assembled.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{slot_key}_playback_{ts}.mp4"
    abs_dest = assembled / name
    root = h._stitch_project_root()
    try:
        rel = str(abs_dest.resolve().relative_to(root))
    except ValueError:
        rel = f"Production/{event_dir.name}/assembled/{name}"
    return abs_dest, rel


def bake_and_persist_slot_playback_mp4(
    h,
    job_name: str,
    slot_key: str,
    *,
    dry_video_rel: str,
    slot_patch: dict,
    beat_boundaries: list | None,
    stitch_store,
    peek_slot: dict | None = None,
) -> tuple[str, int, dict[str, Any]]:
    """Single-mutate bake: dry concat → playback MP4 written to slot.video_path."""
    from server_handlers.stitch_editor import (  # noqa: PLC0415
        STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
        apply_stitch_slot_default_ambient_preset,
        ensure_stitch_slot_canonical_default_sfx_cues,
        enrich_beat_boundaries,
        normalize_slot_audio_mix_levels,
        sync_stitch_slot_video_dur_ms,
        STITCH_SLOT_CANONICAL_DEFAULT_SFX,
        _clear_canonical_sfx_dismiss_flags,
    )

    dry_abs = Path(h._stitch_resolve_path(dry_video_rel))
    dest_abs, playback_rel = _assembled_playback_dest(h, slot_key)

    # Build prospective slot for mix graph (defaults before bake).
    prospective = dict(peek_slot or {})
    prospective.update(slot_patch)
    apply_stitch_slot_default_ambient_preset(slot_key, prospective)
    if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
        ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, prospective)
    normalize_slot_audio_mix_levels(prospective)
    from server_handlers.stitch_editor import _hydrate_slot_ambient_paths  # noqa: PLC0415

    _hydrate_slot_ambient_paths(h, [prospective])

    duration_s = bake_slot_playback_mp4(
        h,
        prospective,
        dry_video_path=dry_abs,
        dest=dest_abs,
    )
    probed_ms = int(round(duration_s * 1000))

    now_iso = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {"ok": True, "code": STITCH_FOUR_FILES_V1}

    def upsert(state: dict) -> None:
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            raise ValueError(f"job missing during playback bake: {job_name!r}")
        slots = job.get("slots")
        if not isinstance(slots, dict):
            raise ValueError(f"job slots missing: {job_name!r}")
        slot = slots.setdefault(slot_key, {})
        old_video = (slot.get("video_path") or "").strip()
        slot.update(slot_patch)
        slot["dry_export_path"] = dry_video_rel
        slot["video_path"] = playback_rel
        slot["video_dur_ms"] = probed_ms
        slot["playback_recipe_version"] = STITCH_FOUR_FILES_PLAYBACK_RECIPE
        clear_legacy_playback_artifact_fields(slot)
        apply_stitch_slot_default_ambient_preset(slot_key, slot)
        if old_video and old_video != playback_rel:
            _clear_canonical_sfx_dismiss_flags(slot, slot_key)
        if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
            ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, slot)
        normalize_slot_audio_mix_levels(slot)
        if beat_boundaries is not None:
            slot["beat_boundaries"] = enrich_beat_boundaries(beat_boundaries)
        sync_stitch_slot_video_dur_ms(h, slot, force=True)
        job["updated_at"] = now_iso

    stitch_store.mutate_state(upsert)
    result["video_path"] = playback_rel
    result["video_dur_ms"] = probed_ms
    result["export_full_media"] = STITCH_SLOT_EXPORT_FULL_MEDIA_V1
    return playback_rel, probed_ms, result


def rebake_slot_playback_from_dry(h, job_name: str, slot_key: str, *, stitch_store=None) -> dict:
    """Save-path rebake: requires dry_export_path on slot."""
    stitch_store = stitch_store or h.app.stitch_state
    state = stitch_store.read_state() or {}
    job = (state.get("jobs") or {}).get(job_name)
    if not isinstance(job, dict):
        return {"ok": False, "error": "job_missing", "code": STITCH_FOUR_FILES_V1}
    slot = (job.get("slots") or {}).get(slot_key)
    if not isinstance(slot, dict):
        return {"ok": False, "error": "slot_missing", "code": STITCH_FOUR_FILES_V1}
    dry_rel = (slot.get("dry_export_path") or "").strip()
    if not dry_rel:
        return {
            "ok": False,
            "error": "dry_export_path_missing",
            "code": STITCH_FOUR_FILES_V1,
            "hint": "Re Send to Stitcher for this slot to establish dry_export_path",
        }
    boundaries = slot.get("beat_boundaries")
    try:
        playback_rel, probed_ms, report = bake_and_persist_slot_playback_mp4(
            h,
            job_name,
            slot_key,
            dry_video_rel=dry_rel,
            slot_patch={},
            beat_boundaries=boundaries,
            stitch_store=stitch_store,
            peek_slot=slot,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return {"ok": False, "error": str(exc), "code": STITCH_FOUR_FILES_V1}
    report["video_path"] = playback_rel
    report["video_dur_ms"] = probed_ms
    return report
