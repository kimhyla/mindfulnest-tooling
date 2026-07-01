"""BG_O3_STITCH_EXPORT_LINEAGE_V1 — invalidate stitch slots when O3 export authority changes.

When any beat's ``kling_o3_video_path`` or ``kling_o3_selected_option_key`` changes,
the BG-exported stitch slot for that segment must not keep serving the pre-change MP4.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

BG_O3_STITCH_EXPORT_LINEAGE_V1 = "BG_O3_STITCH_EXPORT_LINEAGE_V1"


def _resolve_path_for_lineage(video_path: str) -> str:
    vp = str(video_path or "").strip()
    if not vp:
        return ""
    try:
        return str(Path(vp).resolve())
    except OSError:
        return vp


def compute_bg_segment_o3_export_lineage_sig(beats: list[dict]) -> str:
    """Stable hash of per-beat export pointers for a BG segment."""
    parts: list[str] = []
    for beat in sorted(beats, key=lambda b: str(b.get("beat_id") or "")):
        if not isinstance(beat, dict):
            continue
        bid = str(beat.get("beat_id") or "")
        path = _resolve_path_for_lineage(str(beat.get("kling_o3_video_path") or ""))
        key = str(beat.get("kling_o3_selected_option_key") or "").strip()
        parts.append(f"{bid}|{key}|{path}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def o3_export_authority_changed(before: dict | None, after: dict | None) -> bool:
    """True when active export pointer fields differ between beat snapshots."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    for field in ("kling_o3_video_path", "kling_o3_selected_option_key"):
        b_val = str(before.get(field) or "").strip()
        a_val = str(after.get(field) or "").strip()
        if field == "kling_o3_video_path":
            b_val = _resolve_path_for_lineage(b_val)
            a_val = _resolve_path_for_lineage(a_val)
        if b_val != a_val:
            return True
    return False


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
    return sig
