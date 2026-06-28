"""O3 gallery closure invariant — terminal done only after delivery is in kling_o3_options.

UI tiles read ``kling_o3_options``; lifecycle reads ``*_terminal.json`` + ``job_busy``.
A job is not operator-closed until the delivery path appears as a user-selectable gallery row.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def delivery_path_in_gallery(beat: dict, delivery_path: str) -> bool:
    """True when ``delivery_path`` is a user-selectable row in ``kling_o3_options``."""
    import beat_generator as bg

    dp = str(delivery_path or "").strip()
    if not dp:
        return False
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        vp = str(opt.get("video_path") or "").strip()
        if vp != dp:
            continue
        if bg.is_user_selectable_o3_video(vp, opt.get("source")):
            return True
    return False


def beat_gallery_closure_pending(
    beat: dict,
    event_dir: Path | None = None,
    *,
    terminal: dict | None = None,
    job_id: str | None = None,
) -> bool:
    """Terminal success but gallery tiles still empty for the delivered clip."""
    from o3_generation_intent import load_intent_terminal, terminal_path_for_job

    if terminal is None and job_id and event_dir:
        terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
    status = str((terminal or {}).get("status") or "").strip()
    if status not in ("done", "done_with_warning"):
        return False
    delivered = (terminal or {}).get("delivered") or {}
    video = str(delivered.get("video_path") or beat.get("kling_o3_video_path") or "").strip()
    if not video or not Path(video).is_file():
        return False
    return not delivery_path_in_gallery(beat, video)


def refresh_beat_gallery_fields_for_finalize(
    beat_id: str,
    event_dir: Path,
    delivery_path: str,
) -> dict[str, Any]:
    """Reload sidecar options + targeted disk reconcile before finalize persist."""
    import beat_generator as bg

    beat_copy: dict[str, Any] = {}
    with bg._sidecar_lock:
        sidecar = bg.read_sidecar()
        _, found = bg.find_beat(sidecar, beat_id)
        if found:
            beat_copy = dict(found)
    if not beat_copy:
        return {}
    bg.reconcile_o3_disk_deliveries_for_beat(beat_copy, event_dir)
    if not delivery_path_in_gallery(beat_copy, delivery_path):
        bg.recover_orphan_o3_delivery(
            beat_id,
            event_dir,
            log_path=None,
            delivery_path=delivery_path,
            make_active=True,
        )
        with bg._sidecar_lock:
            sidecar = bg.read_sidecar()
            _, found = bg.find_beat(sidecar, beat_id)
            if found:
                beat_copy = dict(found)
    return {"kling_o3_options": beat_copy.get("kling_o3_options")}


def assert_gallery_closed_before_terminal(
    beat_id: str,
    event_dir: Path,
    delivery_path: str,
) -> None:
    """Raise when pipeline would write terminal done without a gallery row."""
    import beat_generator as bg

    sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
    _, beat = bg.find_beat(sidecar, beat_id)
    if beat and delivery_path_in_gallery(beat, delivery_path):
        return
    raise RuntimeError(
        f"gallery not closed before terminal for {beat_id}: {delivery_path} missing from kling_o3_options"
    )
