"""STITCH_SLOT_MEDIA_ARTIFACTS_V1 — validate, persist, and pin stitch slot media artifacts."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from server_handlers.stitch_media_sig import (
    STITCH_AMBIENT_BAKE_ON_SAVE_V1,
    STITCH_AMBIENT_MUX_LEGACY_CLEARED_V1,
    STITCH_LOAD_JOB_FAST_V1,
    STITCH_MUX_VIDEO_LINEAGE_V1,
    STITCH_SLOT_ARTIFACT_FIELDS,
    STITCH_SLOT_AMBIENT_MIX_FIELDS,
    STITCH_SLOT_MEDIA_ARTIFACTS_V1,
    STITCH_SLOT_MUX_FIELDS,
    clear_stitch_slot_ambient_mix_artifacts,
    clear_stitch_slot_media_artifacts,
    clear_stitch_slot_mux_artifacts,
    compute_stitch_ambient_mix_sig_from_slot,
    compute_stitch_mix_sig_from_slot,
    _video_mtime_ms,
)


def stitch_collect_referenced_cache_stems(stitch_state: dict) -> set[str]:
    """Return cache filename stems referenced by persisted slot artifact hashes."""
    stems: set[str] = set()
    jobs = stitch_state.get("jobs") if isinstance(stitch_state, dict) else None
    if not isinstance(jobs, dict):
        return stems
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        slots = job.get("slots")
        if not isinstance(slots, dict):
            continue
        for slot in slots.values():
            if not isinstance(slot, dict):
                continue
            mux = (slot.get("mux_preview_hash") or "").strip()
            peaks = (slot.get("waveform_peaks_hash") or "").strip()
            ambient = (slot.get("ambient_mix_hash") or "").strip()
            if mux:
                stems.add(mux)
            if peaks:
                stems.add(peaks)
            if ambient:
                stems.add(ambient)
    return stems


def sweep_stitch_editor_cache(
    project_root: Path,
    stitch_state: dict,
    *,
    max_age_s: float = 3600.0,
) -> dict[str, int]:
    """Sweep orphan temps and unreferenced cache artifacts (startup + post-migration)."""
    from credentials_lib.stitch_cache_build import (  # noqa: PLC0415
        sweep_stitch_cache_orphan_temps,
        sweep_stitch_cache_unreferenced,
    )

    cache_dir = Path(project_root) / "Production" / "stitch_editor_cache"
    orphan_temps = sweep_stitch_cache_orphan_temps(cache_dir, max_age_s=max_age_s)
    referenced = stitch_collect_referenced_cache_stems(stitch_state)
    unreferenced = sweep_stitch_cache_unreferenced(
        cache_dir, referenced, max_age_s=max_age_s,
    )
    return {"orphan_temps": orphan_temps, "unreferenced": unreferenced}


def _stitch_media_public_url(h, api_path: str) -> str:
    from server_handlers.stitch_editor import _stitch_media_public_url  # noqa: PLC0415

    return _stitch_media_public_url(h, api_path)


def attach_stitch_slot_derived_media_urls(h, slot: dict) -> None:
    """Attach ephemeral media URLs for client hydrate."""
    if not isinstance(slot, dict):
        return
    slot.pop("_mux_preview_url", None)
    slot.pop("_waveform_peaks_url", None)
    slot.pop("_ambient_mix_url", None)
    ambient_hash = (slot.get("ambient_mix_hash") or "").strip()
    if ambient_hash:
        slot["_ambient_mix_url"] = _stitch_media_public_url(
            h, f"/api/stitch_editor/slot_mix_file/{ambient_hash}",
        )
    mux_hash = (slot.get("mux_preview_hash") or "").strip()
    peaks_hash = (slot.get("waveform_peaks_hash") or "").strip()
    if mux_hash:
        slot["_mux_preview_url"] = _stitch_media_public_url(
            h, f"/api/stitch_editor/preview_file/{mux_hash}",
        )
    if peaks_hash:
        slot["_waveform_peaks_url"] = _stitch_media_public_url(
            h, f"/api/stitch_editor/peaks_file/stitch_peaks_{peaks_hash}.json",
        )


def _stitch_slot_has_sfx(slot: dict) -> bool:
    return bool(
        [c for c in (slot.get("sfx_cues") or []) if isinstance(c, dict)],
    )


def _stitch_slot_has_ambient(slot: dict) -> bool:
    return bool(
        (slot.get("ambient_bed_path") or slot.get("ambient_bed") or "").strip(),
    )


def _stitch_slot_requires_layered_audio(slot: dict) -> bool:
    """True when slot expects ambient bed and/or SFX baked into mux preview."""
    return _stitch_slot_has_ambient(slot) or _stitch_slot_has_sfx(slot)


def stitch_slot_needs_playback_artifact_bake(h, slot: dict) -> bool:
    """True when slot has video + SFX/ambient config but durable playback artifact is missing."""
    if not isinstance(slot, dict):
        return False
    video_path = (slot.get("video_path") or "").strip()
    if not video_path:
        return False
    if not callable(getattr(h, "_stitch_cache_dir", None)):
        return False
    try:
        cache_dir = h._stitch_cache_dir()
    except (AttributeError, OSError, TypeError, ValueError):
        return False

    if _stitch_slot_has_sfx(slot):
        mux_hash = (slot.get("mux_preview_hash") or "").strip()
        if not mux_hash:
            return True
        if not _artifact_cache_file_present(cache_dir, "preview", mux_hash):
            return True
        mux_video_path = (slot.get("mux_video_path") or "").strip()
        return mux_video_path != video_path

    if _stitch_slot_has_ambient(slot):
        amb_hash = (slot.get("ambient_mix_hash") or "").strip()
        if not amb_hash:
            return True
        if not _artifact_cache_file_present(cache_dir, "ambient_mix", amb_hash):
            return True
        pinned_path = (slot.get("ambient_mix_video_path") or "").strip()
        return pinned_path != video_path

    return False


def _file_content_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stitch_preview_lacks_layered_mix(h, slot: dict, mux_stem: str) -> bool:
    """True when preview MP4 is byte-identical to source slot video (mix never ran)."""
    if not _stitch_slot_requires_layered_audio(slot):
        return False
    cache_dir = h._stitch_cache_dir()
    preview = cache_dir / f"stitch_preview_{mux_stem}.mp4"
    if not preview.is_file():
        return False
    video_path = (slot.get("video_path") or "").strip()
    if not video_path:
        return False
    try:
        abs_vp = Path(h._stitch_resolve_path(video_path))
    except (ValueError, TypeError, OSError):
        return False
    if not abs_vp.is_file():
        return False
    try:
        return _file_content_md5(preview) == _file_content_md5(abs_vp)
    except OSError:
        return False


def _artifact_cache_file_present(cache_dir: Path, artifact_kind: str, stem: str) -> bool:
    """Fast existence check — no ffprobe/decode (STITCH_LOAD_JOB_FAST_V1)."""
    if not stem:
        return False
    if artifact_kind == "peaks":
        path = cache_dir / f"stitch_peaks_{stem}.json"
    elif artifact_kind == "preview":
        path = cache_dir / f"stitch_preview_{stem}.mp4"
    elif artifact_kind == "ambient_mix":
        path = cache_dir / f"se_slot_{stem}.mp4"
    else:
        return False
    try:
        return path.is_file() and path.stat().st_size > 1024
    except OSError:
        return False


def _artifact_file_valid(
    h,
    cache_dir: Path,
    artifact_kind: str,
    stem: str,
    expected_ms: int,
) -> bool:
    if not stem:
        return False
    if artifact_kind == "peaks":
        path = cache_dir / f"stitch_peaks_{stem}.json"
    elif artifact_kind == "preview":
        path = cache_dir / f"stitch_preview_{stem}.mp4"
    elif artifact_kind == "ambient_mix":
        path = cache_dir / f"se_slot_{stem}.mp4"
    else:
        return False
    if not path.is_file():
        return False
    if expected_ms <= 0:
        return path.stat().st_size > 1024
    from credentials_lib.ffmpeg_stitch import (  # noqa: PLC0415
        preview_cache_is_valid,
        stitch_audio_cache_is_valid,
    )

    expected_s = expected_ms / 1000.0
    if artifact_kind == "peaks":
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            dur = float(data.get("duration_s") or 0)
            return dur >= expected_s * 0.85
        except (OSError, TypeError, ValueError):
            return False
    if artifact_kind == "ambient_mix":
        from server_handlers.stitch_editor import stitch_cached_mp4_playable  # noqa: PLC0415

        return stitch_cached_mp4_playable(path, expected_s=expected_s)
    return preview_cache_is_valid(path, expected_s)


def _stitch_ambient_mix_lacks_layered_audio(h, slot: dict, ambient_stem: str) -> bool:
    """True when se_slot_* is byte-identical to source video (ambient mix never ran)."""
    if not _stitch_slot_has_ambient(slot):
        return False
    cache_dir = h._stitch_cache_dir()
    mixed = cache_dir / f"se_slot_{ambient_stem}.mp4"
    if not mixed.is_file():
        return False
    video_path = (slot.get("video_path") or "").strip()
    if not video_path:
        return False
    try:
        abs_vp = Path(h._stitch_resolve_path(video_path))
    except (ValueError, TypeError, OSError):
        return False
    if not abs_vp.is_file():
        return False
    try:
        return _file_content_md5(mixed) == _file_content_md5(abs_vp)
    except OSError:
        return False


def validate_stitch_slot_media_artifacts(
    h,
    slot: dict,
    *,
    fast: bool = False,
) -> list[str]:
    """Probe artifact files; clear stale fields. Returns human warnings."""
    warnings: list[str] = []
    if not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
        clear_stitch_slot_media_artifacts(slot)
        return warnings

    current_mix_sig = compute_stitch_mix_sig_from_slot(h, slot)
    current_ambient_sig = compute_stitch_ambient_mix_sig_from_slot(h, slot)
    stored_mix_sig = (slot.get("mix_sig") or "").strip()
    stored_ambient_sig = (slot.get("ambient_mix_sig") or "").strip()

    if stored_mix_sig and stored_mix_sig != current_mix_sig:
        clear_stitch_slot_mux_artifacts(slot)
        warnings.append("mix_sig stale — mux artifacts cleared")
    if stored_ambient_sig and stored_ambient_sig != current_ambient_sig:
        clear_stitch_slot_ambient_mix_artifacts(slot)
        warnings.append("ambient_mix_sig stale — ambient mix cleared")

    if not stored_mix_sig and any(slot.get(f) for f in STITCH_SLOT_MUX_FIELDS):
        clear_stitch_slot_mux_artifacts(slot)
        warnings.append("mix_sig missing — mux artifacts cleared")

    if not stored_ambient_sig and any(slot.get(f) for f in STITCH_SLOT_AMBIENT_MIX_FIELDS):
        clear_stitch_slot_ambient_mix_artifacts(slot)
        warnings.append("ambient_mix_sig missing — ambient mix cleared")

    # Migration: ambient-only slots should not keep legacy mux preview (once per slot).
    if _stitch_slot_has_ambient(slot) and not _stitch_slot_has_sfx(slot):
        if slot.get("mux_preview_hash") and not slot.get(STITCH_AMBIENT_MUX_LEGACY_CLEARED_V1):
            clear_stitch_slot_mux_artifacts(slot)
            slot[STITCH_AMBIENT_MUX_LEGACY_CLEARED_V1] = True
            warnings.append(
                f"legacy mux on ambient-only slot cleared ({STITCH_AMBIENT_BAKE_ON_SAVE_V1})",
            )

    cache_dir = h._stitch_cache_dir()
    expected_ms = int(slot.get("video_dur_ms") or 0)
    if expected_ms <= 0 and not fast:
        from server_handlers.stitch_editor import sync_stitch_slot_video_dur_ms  # noqa: PLC0415

        sync_stitch_slot_video_dur_ms(h, slot, force=True)
        expected_ms = int(slot.get("video_dur_ms") or 0)

    current_video_path = (slot.get("video_path") or "").strip()

    ambient_hash = (slot.get("ambient_mix_hash") or "").strip()
    if ambient_hash and _stitch_slot_has_ambient(slot):
        ambient_lineage_stale = False
        pinned_path = (slot.get("ambient_mix_video_path") or "").strip()
        pinned_mtime = int(slot.get("ambient_mix_video_mtime_ms") or 0)
        current_mtime_ms = 0
        if current_video_path and hasattr(h, "_stitch_resolve_path"):
            try:
                current_mtime_ms = _video_mtime_ms(
                    str(h._stitch_resolve_path(current_video_path)),
                )
            except (ValueError, TypeError, OSError):
                current_mtime_ms = 0
        if not pinned_path:
            if (
                fast
                and stored_ambient_sig == current_ambient_sig
                and stored_ambient_sig
                and _artifact_cache_file_present(cache_dir, "ambient_mix", ambient_hash)
                and current_video_path
            ):
                slot["ambient_mix_video_path"] = current_video_path
                if current_mtime_ms:
                    slot["ambient_mix_video_mtime_ms"] = current_mtime_ms
            else:
                ambient_lineage_stale = True
                warnings.append("ambient mix missing lineage pins — cleared")
        elif pinned_path != current_video_path:
            ambient_lineage_stale = True
            warnings.append("ambient mix built for different video_path — cleared")
        elif not fast and pinned_mtime and current_mtime_ms and pinned_mtime != current_mtime_ms:
            ambient_lineage_stale = True
            warnings.append("ambient mix built for older video revision — cleared")
        ambient_dur_ms = int(slot.get("ambient_mix_duration_ms") or 0)
        if not ambient_lineage_stale and ambient_dur_ms > 0 and expected_ms > 0:
            drift_ms = abs(ambient_dur_ms - expected_ms)
            drift_limit_ms = max(250, int(expected_ms * 0.01))
            if drift_ms > drift_limit_ms:
                ambient_lineage_stale = True
                warnings.append(f"ambient mix duration drift {drift_ms}ms — cleared")
        if ambient_lineage_stale:
            clear_stitch_slot_ambient_mix_artifacts(slot)
        elif fast and stored_ambient_sig == current_ambient_sig and stored_ambient_sig:
            if not _artifact_cache_file_present(cache_dir, "ambient_mix", ambient_hash):
                clear_stitch_slot_ambient_mix_artifacts(slot)
                warnings.append("ambient mix cache missing — cleared")
        elif not _artifact_file_valid(
            h, cache_dir, "ambient_mix", ambient_hash, expected_ms,
        ):
            clear_stitch_slot_ambient_mix_artifacts(slot)
            warnings.append("ambient mix cache missing or truncated — cleared")
        elif stored_ambient_sig != current_ambient_sig and _stitch_ambient_mix_lacks_layered_audio(
            h, slot, ambient_hash,
        ):
            clear_stitch_slot_ambient_mix_artifacts(slot)
            warnings.append("ambient mix is unmixed — cleared")

    mux_hash = (slot.get("mux_preview_hash") or "").strip()
    if mux_hash and _stitch_slot_has_sfx(slot):
        mux_lineage_stale = False
        mux_video_path = (slot.get("mux_video_path") or "").strip()
        mux_video_mtime_ms = int(slot.get("mux_video_mtime_ms") or 0)
        current_video_mtime_ms = 0
        if current_video_path and hasattr(h, "_stitch_resolve_path"):
            try:
                current_video_mtime_ms = _video_mtime_ms(
                    str(h._stitch_resolve_path(current_video_path)),
                )
            except (ValueError, TypeError, OSError):
                current_video_mtime_ms = 0

        if not mux_video_path:
            if (
                fast
                and stored_mix_sig == current_mix_sig
                and stored_mix_sig
                and _artifact_cache_file_present(cache_dir, "preview", mux_hash)
                and current_video_path
            ):
                slot["mux_video_path"] = current_video_path
                if current_video_mtime_ms:
                    slot["mux_video_mtime_ms"] = current_video_mtime_ms
            else:
                mux_lineage_stale = True
                warnings.append(
                    f"mux preview missing {STITCH_MUX_VIDEO_LINEAGE_V1} pins — cleared",
                )
        elif mux_video_path != current_video_path:
            mux_lineage_stale = True
            warnings.append(
                "mux preview built for different video_path — cleared",
            )
        elif not fast and mux_video_mtime_ms and current_video_mtime_ms and (
            mux_video_mtime_ms != current_video_mtime_ms
        ):
            mux_lineage_stale = True
            warnings.append(
                "mux preview built for older video revision — cleared",
            )

        mux_dur_ms = int(slot.get("mux_preview_duration_ms") or 0)
        if not mux_lineage_stale and mux_dur_ms > 0 and expected_ms > 0:
            drift_ms = abs(mux_dur_ms - expected_ms)
            drift_limit_ms = max(250, int(expected_ms * 0.01))
            if drift_ms > drift_limit_ms:
                mux_lineage_stale = True
                warnings.append(
                    f"mux preview duration drift {drift_ms}ms — cleared",
                )

        if mux_lineage_stale:
            slot.pop("mux_preview_hash", None)
            slot.pop("mux_preview_duration_ms", None)
            slot.pop("mux_video_path", None)
            slot.pop("mux_video_mtime_ms", None)
        elif fast and stored_mix_sig == current_mix_sig and stored_mix_sig:
            if not _artifact_cache_file_present(cache_dir, "preview", mux_hash):
                slot.pop("mux_preview_hash", None)
                slot.pop("mux_preview_duration_ms", None)
                slot.pop("mux_video_path", None)
                slot.pop("mux_video_mtime_ms", None)
                warnings.append("mux preview cache missing — cleared")
        elif not _artifact_file_valid(
            h, cache_dir, "preview", mux_hash, expected_ms,
        ):
            slot.pop("mux_preview_hash", None)
            slot.pop("mux_preview_duration_ms", None)
            slot.pop("mux_video_path", None)
            slot.pop("mux_video_mtime_ms", None)
            warnings.append("mux preview cache missing or truncated — cleared")
        elif stored_mix_sig != current_mix_sig and _stitch_preview_lacks_layered_mix(
            h, slot, mux_hash,
        ):
            slot.pop("mux_preview_hash", None)
            slot.pop("mux_preview_duration_ms", None)
            slot.pop("mux_video_path", None)
            slot.pop("mux_video_mtime_ms", None)
            warnings.append(
                "mux preview is unmixed (ambient/SFX configured but not baked) — cleared",
            )

    peaks_hash = (slot.get("waveform_peaks_hash") or "").strip()
    if peaks_hash:
        peaks_ok = (
            _artifact_cache_file_present(cache_dir, "peaks", peaks_hash)
            if fast
            else _artifact_file_valid(h, cache_dir, "peaks", peaks_hash, expected_ms)
        )
        if not peaks_ok:
            slot.pop("waveform_peaks_hash", None)
            slot.pop("waveform_peaks_duration_s", None)
            warnings.append("waveform peaks cache missing or truncated — cleared")

    # Always pin sigs to live geometry — stale stored sig must not re-clear mux every load.
    slot["mix_sig"] = current_mix_sig
    if _stitch_slot_has_ambient(slot):
        slot["ambient_mix_sig"] = current_ambient_sig
    elif slot.get("ambient_mix_sig"):
        slot.pop("ambient_mix_sig", None)

    attach_stitch_slot_derived_media_urls(h, slot)
    return warnings


def persist_stitch_slot_ambient_mix_artifacts(
    h,
    job_name: str,
    slot_key: str,
    *,
    ambient_mix_sig: str,
    ambient_mix_hash: str,
    ambient_mix_duration_ms: int,
    ambient_mix_video_path: str | None = None,
    ambient_mix_video_mtime_ms: int | None = None,
) -> None:
    """Persist ambient-only mix artifact (se_slot_*) on stitch job slot."""

    def update(state: dict) -> None:
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            return
        slots = job.get("slots")
        if not isinstance(slots, dict):
            return
        slot = slots.get(slot_key)
        if not isinstance(slot, dict):
            return
        pinned_path = (ambient_mix_video_path or (slot.get("video_path") or "").strip())
        pinned_mtime = ambient_mix_video_mtime_ms
        if pinned_mtime is None and pinned_path and hasattr(h, "_stitch_resolve_path"):
            try:
                pinned_mtime = _video_mtime_ms(
                    str(h._stitch_resolve_path(pinned_path)),
                )
            except (ValueError, TypeError, OSError):
                pinned_mtime = None
        if not pinned_path or pinned_mtime is None:
            clear_stitch_slot_ambient_mix_artifacts(slot)
            return
        slot["ambient_mix_sig"] = ambient_mix_sig
        slot["ambient_mix_hash"] = ambient_mix_hash
        slot["ambient_mix_duration_ms"] = int(ambient_mix_duration_ms)
        slot["ambient_mix_video_path"] = pinned_path
        slot["ambient_mix_video_mtime_ms"] = int(pinned_mtime)
        slot["mix_sig"] = compute_stitch_mix_sig_from_slot(h, slot)
        slot["media_artifacts_built_at"] = datetime.now(timezone.utc).isoformat()
        job["updated_at"] = slot["media_artifacts_built_at"]

    from server_handlers.stitch_editor import stitch_state_store_for_job  # noqa: PLC0415

    stitch_state_store_for_job(h, job_name).mutate_state(update)


def persist_stitch_slot_media_artifacts(
    h,
    job_name: str,
    slot_key: str,
    *,
    mix_sig: str,
    waveform_peaks_hash: str | None = None,
    waveform_peaks_duration_s: float | None = None,
    mux_preview_hash: str | None = None,
    mux_preview_duration_ms: int | None = None,
    mux_video_path: str | None = None,
    mux_video_mtime_ms: int | None = None,
) -> None:
    """Write artifact hashes onto the canonical stitch job slot."""

    def update(state: dict) -> None:
        job = (state.get("jobs") or {}).get(job_name)
        if not isinstance(job, dict):
            return
        slots = job.get("slots")
        if not isinstance(slots, dict):
            return
        slot = slots.get(slot_key)
        if not isinstance(slot, dict):
            return
        slot["mix_sig"] = mix_sig
        slot["media_artifacts_built_at"] = datetime.now(timezone.utc).isoformat()
        if waveform_peaks_hash:
            slot["waveform_peaks_hash"] = waveform_peaks_hash
            if waveform_peaks_duration_s is not None:
                slot["waveform_peaks_duration_s"] = waveform_peaks_duration_s
        if mux_preview_hash:
            pinned_path = (mux_video_path or (slot.get("video_path") or "").strip())
            pinned_mtime = mux_video_mtime_ms
            if pinned_mtime is None and pinned_path and hasattr(h, "_stitch_resolve_path"):
                try:
                    pinned_mtime = _video_mtime_ms(
                        str(h._stitch_resolve_path(pinned_path)),
                    )
                except (ValueError, TypeError, OSError):
                    pinned_mtime = None
            if not pinned_path:
                slot.pop("mux_preview_hash", None)
                slot.pop("mux_preview_duration_ms", None)
                slot.pop("mux_video_path", None)
                slot.pop("mux_video_mtime_ms", None)
            else:
                slot["mux_preview_hash"] = mux_preview_hash
                if mux_preview_duration_ms is not None:
                    slot["mux_preview_duration_ms"] = mux_preview_duration_ms
                slot["mux_video_path"] = pinned_path
                if pinned_mtime is not None:
                    slot["mux_video_mtime_ms"] = int(pinned_mtime)
                else:
                    slot.pop("mux_video_mtime_ms", None)
        job["updated_at"] = slot["media_artifacts_built_at"]

    from server_handlers.stitch_editor import stitch_state_store_for_job  # noqa: PLC0415

    stitch_state_store_for_job(h, job_name).mutate_state(update)


def find_stitch_job_slot_for_video(h, video_path: str) -> tuple[str, str] | None:
    """Return (job_name, slot_key) when video_path matches a canonical slot."""
    vp = (video_path or "").strip()
    if not vp:
        return None
    state = h.app.stitch_state.read_state() or {}
    jobs = state.get("jobs") or {}
    if not isinstance(jobs, dict):
        return None
    from server_handlers.stitch_editor import STITCH_SLOT_ORDER  # noqa: PLC0415

    for job_name, job in jobs.items():
        if not isinstance(job, dict) or not job_name.endswith("_stitch"):
            continue
        slots = job.get("slots")
        if not isinstance(slots, dict):
            continue
        for slot_key in STITCH_SLOT_ORDER:
            slot = slots.get(slot_key)
            if isinstance(slot, dict) and (slot.get("video_path") or "").strip() == vp:
                return job_name, slot_key
    return None


def invalidate_stitch_slot_artifacts_if_mix_drift(h, slot: dict) -> bool:
    """Clear mux and/or ambient artifacts when live geometry no longer matches stored sigs."""
    if not isinstance(slot, dict) or not (slot.get("video_path") or "").strip():
        return False
    cleared = False
    current_mix_sig = compute_stitch_mix_sig_from_slot(h, slot)
    current_ambient_sig = compute_stitch_ambient_mix_sig_from_slot(h, slot)
    stored_mix_sig = (slot.get("mix_sig") or "").strip()
    stored_ambient_sig = (slot.get("ambient_mix_sig") or "").strip()
    if stored_mix_sig and stored_mix_sig != current_mix_sig:
        clear_stitch_slot_mux_artifacts(slot)
        cleared = True
    if stored_ambient_sig and stored_ambient_sig != current_ambient_sig:
        clear_stitch_slot_ambient_mix_artifacts(slot)
        cleared = True
    if not stored_mix_sig and any(slot.get(f) for f in STITCH_SLOT_MUX_FIELDS):
        clear_stitch_slot_mux_artifacts(slot)
        cleared = True
    if not stored_ambient_sig and any(slot.get(f) for f in STITCH_SLOT_AMBIENT_MIX_FIELDS):
        clear_stitch_slot_ambient_mix_artifacts(slot)
        cleared = True
    return cleared


def clear_stitch_slot_artifacts_on_video_change(
    slot: dict,
    old_video_path: str,
    new_video_path: str,
) -> None:
    if (old_video_path or "").strip() != (new_video_path or "").strip():
        clear_stitch_slot_media_artifacts(slot)
