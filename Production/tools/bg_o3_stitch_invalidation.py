"""BG_O3_STITCH_EXPORT_LINEAGE_V1 — invalidate stitch slots when O3 export authority changes.

When any beat's active export authority changes — selection, trim, cut, or baked clip —
the BG-exported stitch slot for that segment must not keep serving the pre-change MP4.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

BG_O3_STITCH_EXPORT_LINEAGE_V1 = "BG_O3_STITCH_EXPORT_LINEAGE_V1"

_EXPORT_AUTHORITY_FIELDS = (
    "kling_o3_video_path",
    "kling_o3_selected_option_key",
    "kling_o3_trim_start",
    "kling_o3_trim_back",
    "kling_o3_cut_start_s",
    "kling_o3_cut_end_s",
    "kling_o3_baked_path",
)


def _resolve_path_for_lineage(video_path: str) -> str:
    vp = str(video_path or "").strip()
    if not vp:
        return ""
    try:
        return str(Path(vp).resolve())
    except OSError:
        return vp


def _beat_export_lineage_part(beat: dict) -> str:
    """Single-beat export authority fingerprint used by stitch lineage sig."""
    import beat_generator as bg  # noqa: PLC0415

    bid = str(beat.get("beat_id") or "")
    path = _resolve_path_for_lineage(str(beat.get("kling_o3_video_path") or ""))
    key = str(beat.get("kling_o3_selected_option_key") or "").strip()
    baked = _resolve_path_for_lineage(str(beat.get("kling_o3_baked_path") or ""))
    trim_start = round(float(beat.get("kling_o3_trim_start") or 0.0), 3)
    trim_back_raw = beat.get("kling_o3_trim_back")
    trim_back = (
        round(float(trim_back_raw), 3)
        if trim_back_raw is not None and str(trim_back_raw).strip() != ""
        else "none"
    )
    cut_start = round(float(beat.get("kling_o3_cut_start_s") or 0.0), 3)
    cut_end_raw = beat.get("kling_o3_cut_end_s")
    cut_end = (
        round(float(cut_end_raw), 3)
        if cut_end_raw is not None and str(cut_end_raw).strip() != ""
        else "none"
    )
    try:
        export_token = bg.o3_baked_export_token(beat, video_path=beat.get("kling_o3_video_path"))
    except Exception:  # noqa: BLE001
        export_token = "unknown"
    return (
        f"{bid}|{key}|{path}|{baked}|t{trim_start}:{trim_back}|"
        f"c{cut_start}:{cut_end}|{export_token}"
    )


def compute_bg_segment_o3_export_lineage_sig(beats: list[dict]) -> str:
    """Stable hash of per-beat export authority for a BG segment."""
    parts: list[str] = []
    for beat in sorted(beats, key=lambda b: str(b.get("beat_id") or "")):
        if not isinstance(beat, dict):
            continue
        parts.append(_beat_export_lineage_part(beat))
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def o3_export_authority_changed(before: dict | None, after: dict | None) -> bool:
    """True when active export authority differs between beat snapshots."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    for field in _EXPORT_AUTHORITY_FIELDS:
        b_val = before.get(field)
        a_val = after.get(field)
        if field.endswith("_path"):
            b_val = _resolve_path_for_lineage(str(b_val or ""))
            a_val = _resolve_path_for_lineage(str(a_val or ""))
        else:
            b_val = str(b_val if b_val is not None else "").strip()
            a_val = str(a_val if a_val is not None else "").strip()
        if b_val != a_val:
            return True
    return _beat_export_lineage_part(before) != _beat_export_lineage_part(after)


def _stitch_job_name_for_event(event_dir: Path) -> str:
    return f"{event_dir.name}_stitch"


def _segment_beats_for_beat(sidecar: dict, beat_id: str) -> tuple[str | None, list[dict]]:
    import beat_generator as bg  # noqa: PLC0415

    phase = bg.segment_phase_for_beat(sidecar, beat_id)
    if not phase:
        return None, []
    for arc in (sidecar.get("arcs") or {}).values():
        for seg_key, seg in (arc.get("segments") or {}).items():
            if not isinstance(seg, dict):
                continue
            for beat in seg.get("beats") or []:
                if beat.get("beat_id") == beat_id:
                    return phase, list(seg.get("beats") or [])
    return phase, []


def invalidate_stitch_slot_for_bg_o3_selection_change(
    h,
    *,
    beat_id: str,
    sidecar: dict,
    before_beat: dict | None,
    after_beat: dict,
    reason: str = "bg_o3_selection_changed",
) -> list[str]:
    """Clear BG-export stitch slot video + mux when O3 selection/path changes."""
    if not o3_export_authority_changed(before_beat, after_beat):
        return []

    import beat_generator as bg  # noqa: PLC0415

    phase, segment_beats = _segment_beats_for_beat(sidecar, beat_id)
    if not phase or not segment_beats:
        return []

    slot_key = bg.stitch_slot_for_bg_phase(phase)
    if not slot_key:
        return []

    event_dir = Path(getattr(h.app, "event_dir", "") or "")
    if not event_dir.is_dir():
        return []

    job_name = _stitch_job_name_for_event(event_dir)
    stitch_store = getattr(h.app, "stitch_state", None)
    if stitch_store is None:
        return []

    logs: list[str] = []
    new_sig = compute_bg_segment_o3_export_lineage_sig(segment_beats)

    def _invalidate(state: dict) -> None:
        jobs = state.get("jobs") or {}
        job = jobs.get(job_name)
        if not isinstance(job, dict):
            return
        slots = job.get("slots")
        if not isinstance(slots, dict):
            return
        slot = slots.get(slot_key)
        if not isinstance(slot, dict):
            return
        old_video = str(slot.get("video_path") or "").strip()
        stored_sig = str(slot.get("bg_o3_export_lineage_sig") or "").strip()
        if not old_video and stored_sig == new_sig:
            return
        if stored_sig and stored_sig == new_sig and not old_video:
            return

        from server_handlers.stitch_media_artifacts import clear_stitch_slot_media_artifacts  # noqa: PLC0415

        if old_video:
            slot["superseded_bg_export_video_path"] = old_video
            slot.pop("video_path", None)
            slot.pop("video_dur_ms", None)
            slot.pop("beat_boundaries", None)
            slot.pop("playback_recipe_version", None)
            slot.pop("dry_export_path", None)
            logs.append(
                f"{slot_key}: cleared BG export video ({Path(old_video).name}) — {reason}",
            )
        clear_stitch_slot_media_artifacts(slot)
        slot["bg_o3_export_stale"] = True
        slot["bg_o3_export_stale_reason"] = reason
        slot["bg_o3_export_lineage_sig"] = new_sig
        job["updated_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc,
        ).isoformat()

    try:
        stitch_store.mutate_state(_invalidate)
    except Exception as exc:  # noqa: BLE001
        logs.append(f"{slot_key}: stitch invalidation failed: {exc}")
    return logs


def stamp_bg_o3_export_lineage_on_slot(
    slot: dict,
    *,
    segment_beats: list[dict],
) -> str:
    """Persist lineage sig after successful BG export upsert."""
    sig = compute_bg_segment_o3_export_lineage_sig(segment_beats)
    if isinstance(slot, dict):
        slot["bg_o3_export_lineage_sig"] = sig
        slot.pop("bg_o3_export_stale", None)
        slot.pop("bg_o3_export_stale_reason", None)
        slot.pop("superseded_bg_export_video_path", None)
        slot.pop("bg_o3_export_lineage_sig_expected", None)
    return sig


def _slot_is_bg_o3_export(slot: dict) -> bool:
    if not isinstance(slot, dict):
        return False
    source = str(slot.get("source") or "").strip().lower()
    return source.startswith("kling_o3_export")


def invalidate_stitch_slot_if_export_lineage_stale(
    h,
    *,
    slot_key: str,
    segment_beats: list[dict],
    reason: str = "bg_o3_export_lineage_mismatch",
    clear_video: bool = True,
) -> list[str]:
    """Mark or clear BG-export stitch slot when stored export no longer matches sidecar authority."""
    event_dir = Path(getattr(h.app, "event_dir", "") or "")
    if not event_dir.is_dir():
        return []

    job_name = _stitch_job_name_for_event(event_dir)
    stitch_store = getattr(h.app, "stitch_state", None)
    if stitch_store is None:
        return []

    current_sig = compute_bg_segment_o3_export_lineage_sig(segment_beats)
    logs: list[str] = []

    def _invalidate_if_stale(state: dict) -> None:
        jobs = state.get("jobs") or {}
        job = jobs.get(job_name)
        if not isinstance(job, dict):
            return
        slots = job.get("slots")
        if not isinstance(slots, dict):
            return
        slot = slots.get(slot_key)
        if not isinstance(slot, dict) or not _slot_is_bg_o3_export(slot):
            return
        old_video = str(slot.get("video_path") or "").strip()
        stored_sig = str(slot.get("bg_o3_export_lineage_sig") or "").strip()
        if stored_sig == current_sig and not slot.get("bg_o3_export_stale"):
            return
        if not old_video and stored_sig == current_sig:
            return

        from server_handlers.stitch_media_artifacts import clear_stitch_slot_media_artifacts  # noqa: PLC0415

        if old_video and clear_video:
            slot["superseded_bg_export_video_path"] = old_video
            slot.pop("video_path", None)
            slot.pop("video_dur_ms", None)
            slot.pop("beat_boundaries", None)
            slot.pop("playback_recipe_version", None)
            slot.pop("dry_export_path", None)
            logs.append(
                f"{slot_key}: cleared stale BG export ({Path(old_video).name}) — {reason}",
            )
        elif old_video:
            logs.append(
                f"{slot_key}: stale BG export flagged ({Path(old_video).name}) — {reason}",
            )
        if clear_video:
            clear_stitch_slot_media_artifacts(slot)
        slot["bg_o3_export_stale"] = True
        slot["bg_o3_export_stale_reason"] = reason
        slot["bg_o3_export_lineage_sig_expected"] = current_sig
        slot["bg_o3_export_lineage_sig"] = stored_sig or current_sig
        job["updated_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc,
        ).isoformat()

    try:
        stitch_store.mutate_state(_invalidate_if_stale)
    except Exception as exc:  # noqa: BLE001
        logs.append(f"{slot_key}: stitch stale reconcile failed: {exc}")
    return logs


def reconcile_bg_o3_export_stale_slots_for_event(h) -> list[str]:
    """Reconcile intro + resolution BG-export slots against current sidecar authority."""
    import beat_generator as bg  # noqa: PLC0415

    event_dir = Path(getattr(h.app, "event_dir", "") or "")
    if not event_dir.is_dir():
        return []
    event_id = bg.normalize_bg_event_id(event_dir.name.replace("Event_", "", 1))

    sidecar = bg.read_sidecar()
    logs: list[str] = []
    for phase, slot_key in (("pre", "intro"), ("post", "resolution")):
        seg = bg.get_seg_entry(sidecar, 1, event_id, phase)
        beats = list(seg.get("beats") or [])
        if not beats:
            continue
        for line in invalidate_stitch_slot_if_export_lineage_stale(
            h,
            slot_key=slot_key,
            segment_beats=beats,
            reason="bg_o3_export_lineage_reconcile",
        ):
            logs.append(line)
    return logs
