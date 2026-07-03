"""Stitch slot playback authority — four-files bake (FF-036) and dry client-mix (FF-042).

FF-036: TECH_SPEC_STITCH_FOUR_FILES_V1.md — dry passthrough concat → normalize +
loudnorm once → ambient/SFX mix → baked *_playback_* on video_path.

FF-042 (legacy): TECH_SPEC_STITCH_DRY_AUTHORITY_CLIENT_MIX_V1.md — dry concat IS
video_path; client Web Audio preview (superseded for event slots by FF-036).
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STITCH_FOUR_FILES_V1 = "STITCH_FOUR_FILES_V1"
STITCH_FOUR_FILES_PLAYBACK_RECIPE = STITCH_FOUR_FILES_V1
# FF-036 — four-files slots must never re-enter se_slot / mux_preview artifact tiers.
STITCH_FOUR_FILES_LEGACY_PURGE_V1 = "STITCH_FOUR_FILES_LEGACY_PURGE_V1"
# FF-037 — playback bake must end on timestamp heal (never copy-remux after).
STITCH_EXPORT_TRUTH_PLAYBACK_REMUX_V1 = "STITCH_EXPORT_TRUTH_PLAYBACK_REMUX_V1"
# FF-041 — lipsync: stream start_time parity + duration drift gate on playback bake.
STITCH_PLAYBACK_LIPSYNC_TIMESTAMP_AUTHORITY_V1 = "STITCH_PLAYBACK_LIPSYNC_TIMESTAMP_AUTHORITY_V1"
# FF-037 — waveform peaks must track speech-only dry export, not ambient-mixed playback.
STITCH_EXPORT_TRUTH_WAVEFORM_SPEECH_V1 = "STITCH_EXPORT_TRUTH_WAVEFORM_SPEECH_V1"
# FF-038 — force peaks re-extract after every export bake (stale hash misaligns composer).
STITCH_EXPORT_TRUTH_WAVEFORM_INVALIDATE_ON_EXPORT_V1 = (
    "STITCH_EXPORT_TRUTH_WAVEFORM_INVALIDATE_ON_EXPORT_V1"
)
# FF-042 — dry concat is video_path; client Web Audio for ambient/SFX preview.
STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 = "STITCH_DRY_AUTHORITY_CLIENT_MIX_V1"
STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE = STITCH_DRY_AUTHORITY_CLIENT_MIX_V1
STITCH_FOUR_FILES_MIGRATE_V1 = "STITCH_FOUR_FILES_MIGRATE_V1"
# FF-036 — Send to Stitcher must persist baked playback on slot JSON + disk (fail loud).
STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1 = "STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1"

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
    """True when server preview mux ladder is inactive (four-files or dry-authority)."""
    return playback_recipe_is_four_files(slot) or playback_recipe_is_dry_authority_client_mix(slot)


def playback_recipe_is_dry_authority_client_mix(slot: dict | None) -> bool:
    if not isinstance(slot, dict):
        return False
    return (slot.get("playback_recipe_version") or "").strip() == STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE


def slot_requires_client_preview_mix(slot: dict | None) -> bool:
    """True when Stitcher should layer ambient and/or SFX via client Web Audio."""
    if not isinstance(slot, dict):
        return False
    if not (
        playback_recipe_is_dry_authority_client_mix(slot)
        or playback_recipe_is_four_files(slot)
    ):
        return False
    return slot_has_playback_mix_layers(slot)


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


def resolve_four_files_waveform_video_path(slot: dict) -> str:
    """Speech-only path for WaveSurfer peaks — dry concat authority."""
    if playback_recipe_is_dry_authority_client_mix(slot):
        return resolve_slot_playback_path(slot)
    if not playback_recipe_is_four_files(slot):
        return resolve_slot_playback_path(slot)
    dry = (slot.get("dry_export_path") or "").strip()
    if dry:
        return dry
    return resolve_slot_playback_path(slot)


def _video_path_looks_like_playback_bake(path: str) -> bool:
    name = Path(path).name.lower()
    return "_playback_" in name


def migrate_four_files_slot_to_dry_authority(h, slot: dict, slot_key: str) -> bool:
    """Move four-files baked authority to dry video_path. Returns True if slot mutated."""
    if not isinstance(slot, dict):
        return False
    recipe = (slot.get("playback_recipe_version") or "").strip()
    video_rel = (slot.get("video_path") or "").strip()
    if recipe != STITCH_FOUR_FILES_PLAYBACK_RECIPE and not _video_path_looks_like_playback_bake(video_rel):
        if recipe == STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE:
            reconcile_dry_authority_slot_artifacts(slot)
        return False

    dry_rel = (slot.get("dry_export_path") or "").strip()
    migrated = False
    if dry_rel:
        try:
            dry_abs = Path(h._stitch_resolve_path(dry_rel))
            if dry_abs.is_file():
                if video_rel != dry_rel:
                    slot["video_path"] = dry_rel
                    slot.pop("waveform_peaks_hash", None)
                    migrated = True
        except (ValueError, TypeError, OSError):
            dry_rel = ""

    if not dry_rel and _video_path_looks_like_playback_bake(video_rel):
        event_dir = Path(h.app.event_dir) / "assembled"
        patterns = {
            "intro": "intro_kling_o3_*.mp4",
            "phase_a": "phase_a_stitched_*.mp4",
            "phase_b": "phase_b_stitched_*.mp4",
            "resolution": "resolution_kling_o3_*.mp4",
        }
        glob_pat = patterns.get(slot_key, f"{slot_key}_kling_o3_*.mp4")
        candidates = sorted(event_dir.glob(glob_pat), key=lambda p: p.stat().st_mtime, reverse=True)
        for cand in candidates:
            if "_playback_" in cand.name:
                continue
            try:
                rel = str(cand.resolve().relative_to(h._stitch_project_root()))
            except ValueError:
                rel = f"Production/{event_dir.parent.name}/assembled/{cand.name}"
            slot["video_path"] = rel
            slot.pop("waveform_peaks_hash", None)
            migrated = True
            break
        if not migrated:
            slot["playback_migration_required"] = True

    slot["playback_recipe_version"] = STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE
    slot.pop("dry_export_path", None)
    clear_legacy_playback_artifact_fields(slot)
    slot.pop("_waveform_peaks_url", None)
    if migrated:
        from server_handlers.stitch_editor import sync_stitch_slot_video_dur_ms  # noqa: PLC0415

        sync_stitch_slot_video_dur_ms(h, slot, force=True)
    return True


def reconcile_dry_authority_slot_artifacts(slot: dict) -> bool:
    """Purge legacy mux fields from dry-authority slots."""
    if not playback_recipe_is_dry_authority_client_mix(slot):
        return False
    had = slot_had_legacy_playback_artifact_fields(slot)
    clear_legacy_playback_artifact_fields(slot)
    slot.pop("dry_export_path", None)
    return had


def migrate_stale_split_authority_slot_to_dry_authority(
    h,
    slot: dict,
    slot_key: str,
) -> bool:
    """Move legacy split-authority / FF-042 slots onto four-files authority.

    Symptom: Beat Gen lipsync is perfect but Stitcher drifts — slot still has
    ambient_mix_hash / mux_preview_hash so the client plays rebaked split
    artifacts. Clears legacy tiers; Re Send to Stitcher rebakes playback MP4.
    """
    del slot_key  # event slots only; slot_key reserved for logging
    if not isinstance(slot, dict):
        return False
    if playback_recipe_is_four_files(slot):
        return reconcile_four_files_slot_authority(slot)
    video_rel = (slot.get("video_path") or "").strip()
    if not video_rel:
        return False
    migrated = False
    if playback_recipe_is_dry_authority_client_mix(slot):
        slot["dry_export_path"] = video_rel
        slot["playback_recipe_version"] = STITCH_FOUR_FILES_PLAYBACK_RECIPE
        clear_legacy_playback_artifact_fields(slot)
        slot.pop("waveform_peaks_hash", None)
        slot.pop("_waveform_peaks_url", None)
        migrated = True
    elif _video_path_looks_like_playback_bake(video_rel):
        return False
    elif slot_had_legacy_playback_artifact_fields(slot):
        slot["dry_export_path"] = video_rel
        slot["playback_recipe_version"] = STITCH_FOUR_FILES_PLAYBACK_RECIPE
        clear_legacy_playback_artifact_fields(slot)
        slot.pop("waveform_peaks_hash", None)
        slot.pop("_waveform_peaks_url", None)
        migrated = True
    if not migrated:
        return False
    from server_handlers.stitch_editor import sync_stitch_slot_video_dur_ms  # noqa: PLC0415

    sync_stitch_slot_video_dur_ms(h, slot, force=True)
    return True


def playback_recipe_is_four_files(slot: dict | None) -> bool:
    if not isinstance(slot, dict):
        return False
    return (slot.get("playback_recipe_version") or "").strip() == STITCH_FOUR_FILES_PLAYBACK_RECIPE


def assert_four_files_export_slot_applied(
    h,
    *,
    stitch_store,
    job_name: str,
    slot_key: str,
    dry_video_rel: str,
    playback_artifacts: dict,
) -> None:
    """Fail loud when Send to Stitcher did not write baked playback to the stitch slot."""
    from credentials_lib.ffmpeg_stitch import mp4_decodes_cleanly  # noqa: PLC0415

    code = STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1
    if not isinstance(playback_artifacts, dict) or not playback_artifacts.get("ok"):
        err = (playback_artifacts or {}).get("error") or "playback bake not ok"
        raise RuntimeError(f"{slot_key}: {err} [{code}]")
    if (playback_artifacts.get("code") or "").strip() != STITCH_FOUR_FILES_V1:
        raise RuntimeError(
            f"{slot_key}: expected {STITCH_FOUR_FILES_V1} bake, got "
            f"{playback_artifacts.get('code')!r} [{code}]",
        )

    playback_rel = (playback_artifacts.get("video_path") or "").strip()
    if not playback_rel or "_playback_" not in Path(playback_rel).name:
        raise RuntimeError(
            f"{slot_key}: playback path missing or not a *_playback_* mp4 [{code}]",
        )

    playback_abs = Path(h._stitch_resolve_path(playback_rel))
    if not playback_abs.is_file() or playback_abs.stat().st_size <= 0:
        raise RuntimeError(f"{slot_key}: playback file missing on disk: {playback_rel} [{code}]")
    if not mp4_decodes_cleanly(playback_abs):
        raise RuntimeError(f"{slot_key}: playback mp4 failed decode smoke [{code}]")

    dry_rel = (dry_video_rel or "").strip()
    if not dry_rel:
        raise RuntimeError(f"{slot_key}: dry export path missing [{code}]")
    dry_abs = Path(h._stitch_resolve_path(dry_rel))
    if not dry_abs.is_file() or dry_abs.stat().st_size <= 0:
        raise RuntimeError(f"{slot_key}: dry concat missing on disk: {dry_rel} [{code}]")

    state = stitch_store.read_state() or {}
    job = (state.get("jobs") or {}).get(job_name)
    if not isinstance(job, dict):
        raise RuntimeError(f"{slot_key}: stitch job missing after export: {job_name!r} [{code}]")
    slot = (job.get("slots") or {}).get(slot_key)
    if not isinstance(slot, dict):
        raise RuntimeError(f"{slot_key}: stitch slot missing after export [{code}]")

    if (slot.get("video_path") or "").strip() != playback_rel:
        raise RuntimeError(
            f"{slot_key}: slot.video_path did not update to playback "
            f"(got {(slot.get('video_path') or '')!r}) [{code}]",
        )
    if (slot.get("dry_export_path") or "").strip() != dry_rel:
        raise RuntimeError(
            f"{slot_key}: slot.dry_export_path mismatch "
            f"(got {(slot.get('dry_export_path') or '')!r}) [{code}]",
        )
    if not playback_recipe_is_four_files(slot):
        raise RuntimeError(
            f"{slot_key}: slot not on four-files recipe "
            f"(got {(slot.get('playback_recipe_version') or '')!r}) [{code}]",
        )


def verify_event_slot_four_files_export_applied(
    h,
    *,
    job_name: str,
    slot_key: str,
    dry_video_rel: str,
    playback_artifacts: dict,
    stitch_store=None,
) -> None:
    """Shared terminal gate for Beat Gen + Phase Send to Stitcher on event slots."""
    from server_handlers.stitch_editor import (  # noqa: PLC0415
        _event_stitch_state_store,
        is_milestone_stitch_job_name,
    )

    if is_milestone_stitch_job_name(job_name):
        return
    store = stitch_store or _event_stitch_state_store(h)
    assert_four_files_export_slot_applied(
        h,
        stitch_store=store,
        job_name=job_name,
        slot_key=slot_key,
        dry_video_rel=dry_video_rel,
        playback_artifacts=playback_artifacts or {},
    )


def _prepare_dry_concat_for_slot_bake(h, dry_video_path: Path, cache_dir: Path) -> Path:
    """LD-284 normalize + speech loudnorm on the passthrough dry concat (once, not per-beat)."""
    from server_handlers.speech_loudnorm import apply_speech_loudnorm_to_mp4  # noqa: PLC0415

    dry_str = str(dry_video_path)
    norm = h._stitch_normalize_slot(dry_str, cache_dir)
    norm = h._stitch_ensure_audio(norm, cache_dir)
    leveled, applied = apply_speech_loudnorm_to_mp4(norm, cache_dir=cache_dir, force=True)
    if applied:
        print(
            f"[stitch] slot bake speech loudnorm ok ({dry_video_path.name})",
            flush=True,
        )
    return leveled


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
        mp4_operator_playback_timestamps_safe,
    )
    from video_delivery import ensure_mp4_playback_timestamps  # noqa: PLC0415

    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dry_video_path.is_file():
        raise FileNotFoundError(f"dry export missing: {dry_video_path}")

    cache_dir = h._stitch_cache_dir()
    speech_src = _prepare_dry_concat_for_slot_bake(h, dry_video_path, cache_dir)

    if slot_has_playback_mix_layers(slot):
        mixed = h._stitch_mix_slot_audio(
            speech_src,
            slot,
            cache_dir,
            force_rebuild=True,
        )
        if mixed.resolve() != dest.resolve():
            shutil.copy2(mixed, dest)
    else:
        if speech_src.resolve() != dest.resolve():
            shutil.copy2(speech_src, dest)
        elif not dest.is_file():
            shutil.copy2(speech_src, dest)

    # Timestamp heal is the final pass. Copy-remux after heal reintroduces ~23ms
    # video start_time vs audio@0 and lengthens audio past video (lipsync drift).
    ensure_mp4_playback_timestamps(dest)
    if not mp4_operator_playback_timestamps_safe(dest):
        try:
            dest.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"{STITCH_PLAYBACK_LIPSYNC_TIMESTAMP_AUTHORITY_V1}: playback bake "
            f"stream start misaligned ({dest.name})",
        )
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
        # FF-038 — peaks hash must not survive path/dry changes across re-export.
        slot.pop("waveform_peaks_hash", None)
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
    assert_four_files_export_slot_applied(
        h,
        stitch_store=stitch_store,
        job_name=job_name,
        slot_key=slot_key,
        dry_video_rel=dry_video_rel,
        playback_artifacts=result,
    )
    result["slot_apply"] = STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1
    return playback_rel, probed_ms, result


def persist_dry_authority_slot_export(
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
    """FF-042 — dry concat IS video_path; no playback bake on export."""
    from server_handlers.stitch_editor import (  # noqa: PLC0415
        STITCH_SLOT_EXPORT_FULL_MEDIA_V1,
        apply_stitch_slot_default_ambient_preset,
        ensure_stitch_slot_canonical_default_sfx_cues,
        enrich_beat_boundaries,
        normalize_slot_audio_mix_levels,
        sync_stitch_slot_video_dur_ms,
        STITCH_SLOT_CANONICAL_DEFAULT_SFX,
        _clear_canonical_sfx_dismiss_flags,
        _hydrate_slot_ambient_paths,
    )

    dry_abs = Path(h._stitch_resolve_path(dry_video_rel))
    if not dry_abs.is_file():
        raise FileNotFoundError(f"dry export missing: {dry_abs}")

    prospective = dict(peek_slot or {})
    prospective.update(slot_patch)
    apply_stitch_slot_default_ambient_preset(slot_key, prospective)
    if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
        ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, prospective)
    normalize_slot_audio_mix_levels(prospective)
    _hydrate_slot_ambient_paths(h, [prospective])

    probed_ms = h._ffprobe_duration_ms(dry_abs)
    now_iso = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {"ok": True, "code": STITCH_DRY_AUTHORITY_CLIENT_MIX_V1}

    def upsert(state: dict) -> None:
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            raise ValueError(f"job missing during dry export upsert: {job_name!r}")
        slots = job.get("slots")
        if not isinstance(slots, dict):
            raise ValueError(f"job slots missing: {job_name!r}")
        slot = slots.setdefault(slot_key, {})
        old_video = (slot.get("video_path") or "").strip()
        slot.update(slot_patch)
        slot["video_path"] = dry_video_rel
        slot["video_dur_ms"] = probed_ms
        slot["playback_recipe_version"] = STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE
        slot.pop("dry_export_path", None)
        slot.pop("playback_migration_required", None)
        clear_legacy_playback_artifact_fields(slot)
        slot.pop("waveform_peaks_hash", None)
        apply_stitch_slot_default_ambient_preset(slot_key, slot)
        if old_video and old_video != dry_video_rel:
            _clear_canonical_sfx_dismiss_flags(slot, slot_key)
        if slot_key in STITCH_SLOT_CANONICAL_DEFAULT_SFX:
            ensure_stitch_slot_canonical_default_sfx_cues(h, slot_key, slot)
        normalize_slot_audio_mix_levels(slot)
        if beat_boundaries is not None:
            slot["beat_boundaries"] = enrich_beat_boundaries(beat_boundaries)
        sync_stitch_slot_video_dur_ms(h, slot, force=True)
        job["updated_at"] = now_iso

    stitch_store.mutate_state(upsert)
    result["video_path"] = dry_video_rel
    result["video_dur_ms"] = probed_ms
    result["export_full_media"] = STITCH_SLOT_EXPORT_FULL_MEDIA_V1
    return dry_video_rel, probed_ms, result


def build_slot_ambient_loop_audio_file(h, slot: dict, cache_dir: Path) -> Path:
    """Render slot-length ambient bed audio for client preview (FF-039 graph parity)."""
    import hashlib as _hl  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    from server_handlers.stitch_ambient_loop import (  # noqa: PLC0415
        ambient_loop_sig_token,
        build_ambient_bed_filter_lane_for_file,
    )

    ambient_path = (slot.get("ambient_bed_path") or "").strip()
    if not ambient_path:
        raise ValueError("ambient_bed_path required for ambient loop render")
    if not Path(ambient_path).is_file():
        raise FileNotFoundError(f"ambient bed not found: {ambient_path}")

    slot_dur_ms = int(slot.get("video_dur_ms") or 0)
    if slot_dur_ms <= 0:
        vp = (slot.get("video_path") or "").strip()
        if vp:
            slot_dur_ms = h._ffprobe_duration_ms(Path(h._stitch_resolve_path(vp)))
    slot_dur_s = max(slot_dur_ms / 1000.0, 0.001)
    ambient_volume = float(slot.get("ambient_volume", 0.15))
    bed_dur_ms = h._ffprobe_duration_ms(Path(ambient_path))
    bed_dur_s = bed_dur_ms / 1000.0 if bed_dur_ms else 0.0

    sig_parts = [
        ambient_path,
        str(ambient_volume),
        str(slot_dur_ms),
        ambient_loop_sig_token(),
    ]
    sig = _hl.md5("|".join(sig_parts).encode(), usedforsecurity=False).hexdigest()[:12]
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_dir / f"ambient_loop_{sig}.m4a"
    if out_path.is_file():
        return out_path

    lane = build_ambient_bed_filter_lane_for_file(
        0, ambient_path, bed_dur_s, slot_dur_s, ambient_volume, out_label="aout",
    )
    tmp = out_path.with_suffix(f".tmp.{os.getpid()}.m4a")
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(Path(ambient_path).resolve()),
                "-filter_complex", lane,
                "-map", "[aout]",
                "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
                str(tmp),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        os.replace(tmp, out_path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return out_path


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
