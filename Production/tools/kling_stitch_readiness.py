"""KLING_STITCH_READINESS_V1 — single Beat Gen stitch-export contract.

Architecture (not a UI patch):
  - **Still-insert beats:** build still ≠ stitch-ready; operator must explicitly approve.
  - **Element / O3 Kling beats:** active user-selectable delivery clip on disk = stitch-ready.
    Operator QC is redo/regen — not a second ``kling_o3_status`` gate that can drift from
    ``kling_o3_video_path``.

Root cause of the 2026-06 regression:
  - Two incompatible readiness models: ``completed``/``draft`` + video vs ``approved`` required
    for export; UI assumed tile-select approves but radio onChange no-ops when already selected.
  - Client and server both hard-coded ``kling_o3_status === 'approved'`` instead of this module.

All server export gates and client Send-to-Stitcher must call ``beat_kling_stitch_export_ready``.
All paths that pin an active delivery clip must call ``sync_kling_stitch_status_from_active_clip``.
"""
from __future__ import annotations

from pathlib import Path

KLING_STITCH_READINESS_V1 = "KLING_STITCH_READINESS_V1"


def beat_kling_stitch_export_ready(beat: dict, event_dir: str | Path) -> bool:
    """True when this beat may be included in segment Send to Stitcher."""
    from beat_generator import (  # noqa: PLC0415
        beat_is_still_insert,
        beat_magic_still_clip_path,
        is_user_selectable_o3_video,
    )

    event_dir = Path(event_dir)
    if beat_magic_still_clip_path(beat, event_dir):
        return True
    if beat_is_still_insert(beat):
        if beat.get("kling_o3_still_stitch_approved"):
            return True
        st = str(beat.get("kling_o3_status") or "")
        vp = str(beat.get("kling_o3_video_path") or "").strip()
        return st == "approved" and bool(vp) and Path(vp).is_file()
    vp = str(beat.get("kling_o3_video_path") or "").strip()
    if not vp or not Path(vp).is_file():
        return False
    if not is_user_selectable_o3_video(vp):
        return False
    if _beat_o3_job_blocks_stitch_export(beat, event_dir):
        return False
    return True


def _beat_o3_job_blocks_stitch_export(beat: dict, event_dir: Path) -> bool:
    try:
        from o3_job_status_contract import beat_o3_operator_busy  # noqa: PLC0415

        return beat_o3_operator_busy(beat, event_dir)
    except Exception:
        return bool(beat.get("job_busy") or beat.get("o3_current_job_id"))


def sync_kling_stitch_status_from_active_clip(beat: dict) -> bool:
    """Align ``kling_o3_status`` with active clip — prevents draft/completed + video drift."""
    from beat_generator import beat_is_still_insert  # noqa: PLC0415

    vp = str(beat.get("kling_o3_video_path") or "").strip()
    if not vp or not Path(vp).is_file():
        return False
    if beat_is_still_insert(beat):
        st = str(beat.get("kling_o3_status") or "")
        if st == "approved" and not beat.get("kling_o3_still_stitch_approved"):
            return False
        if st not in ("still_rendered", "approved"):
            beat["kling_o3_status"] = "still_rendered"
            if beat.get("status") == "approved":
                beat["status"] = "draft"
            return True
        return False
    st = str(beat.get("kling_o3_status") or "")
    if st == "approved" and str(beat.get("status") or "") == "approved":
        return False
    beat["kling_o3_status"] = "approved"
    beat["status"] = "approved"
    return True


def finalize_kling_delivery_clip(
    beat: dict,
    video_path: str,
    *,
    still_insert: bool | None = None,
) -> None:
    """Single write path when a delivery clip becomes the active beat pointer."""
    from beat_generator import beat_is_still_insert  # noqa: PLC0415

    beat["kling_o3_video_path"] = str(Path(video_path).resolve())
    still = beat_is_still_insert(beat) if still_insert is None else still_insert
    if still:
        beat["kling_o3_status"] = "still_rendered"
        beat["status"] = "draft"
        beat.pop("kling_o3_still_stitch_approved", None)
        beat.pop("kling_o3_still_stitch_approved_at", None)
    else:
        beat["kling_o3_status"] = "approved"
        beat["status"] = "approved"
