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
All paths that pin an active delivery clip must call ``finalize_kling_delivery_clip`` or ``align_beat_active_delivery_clip``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KLING_STITCH_READINESS_V1 = "KLING_STITCH_READINESS_V1"


def short_beat_label(beat_id: str) -> str:
    m = re.search(r"beat_(\d+)", str(beat_id or ""))
    return f"beat {m.group(1)}" if m else str(beat_id or "beat")


def beat_still_needs_stitch_approve(beat: dict) -> bool:
    from beat_generator import beat_is_still_insert  # noqa: PLC0415

    if not beat_is_still_insert(beat):
        return False
    if beat.get("kling_o3_still_stitch_approved"):
        return False
    if str(beat.get("kling_o3_status") or "") == "approved":
        return False
    return bool(str(beat.get("kling_o3_video_path") or "").strip())


def beat_stitch_export_block_info(beat: dict, event_dir: str | Path) -> dict[str, str] | None:
    if beat_kling_stitch_export_ready(beat, event_dir):
        return None
    from beat_generator import (  # noqa: PLC0415
        beat_is_still_insert,
        beat_magic_still_clip_path,
        is_user_selectable_o3_video,
    )

    event_dir = Path(event_dir)
    label = short_beat_label(str(beat.get("beat_id") or ""))
    if str(beat.get("magic_still_path") or "").strip():
        resolved = beat_magic_still_clip_path(beat, event_dir)
        if not resolved or not Path(resolved).is_file():
            return {
                "block_code": "MAGIC_STILL_MISSING",
                "block_label": "Magic still file missing",
                "fix_instruction": (
                    f"Re-run magic on still for {label} or clear the broken magic path, "
                    "then retry Send to Stitcher."
                ),
            }
    if beat_still_needs_stitch_approve(beat):
        return {
            "block_code": "STILL_NEEDS_STITCH_APPROVE",
            "block_label": "Approve still clip",
            "fix_instruction": (
                f"Open {label}, select your still clip in the option tile, "
                "then click Approve still for stitch under the video."
            ),
        }
    if _beat_o3_job_blocks_stitch_export(beat, event_dir):
        return {
            "block_code": "JOB_BUSY",
            "block_label": "Wait for Kling job to finish",
            "fix_instruction": (
                f"Wait for the active generation job on {label} to finish, then retry Send to Stitcher."
            ),
        }
    vp = str(beat.get("kling_o3_video_path") or "").strip()
    if vp and Path(vp).is_file() and not beat_is_still_insert(beat):
        if not is_user_selectable_o3_video(vp):
            return {
                "block_code": "CLIP_NOT_SELECTABLE",
                "block_label": "Select a delivery clip",
                "fix_instruction": (
                    f"Select a delivery clip (not a silent/base artifact) for {label}, "
                    "then retry Send to Stitcher."
                ),
            }
    return {
        "block_code": "NO_CLIP",
        "block_label": "Submit Kling or add magic on still",
        "fix_instruction": (
            f"Generate O3 voice or build a still video for {label} first, then retry Send to Stitcher."
        ),
    }


def beat_stitch_export_derived_fields(beat: dict, event_dir: str | Path) -> dict[str, Any]:
    ready = beat_kling_stitch_export_ready(beat, event_dir)
    block = beat_stitch_export_block_info(beat, event_dir) if not ready else None
    return {
        "stitch_export_ready": ready,
        "stitch_export_block_label": block["block_label"] if block else None,
        "stitch_export_fix_instruction": block["fix_instruction"] if block else None,
    }


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

    vp = str(Path(video_path).resolve())
    beat["kling_o3_video_path"] = vp
    beat_id = str(beat.get("beat_id") or "beat")
    from o3_gallery_option_identity import canonical_o3_option_key  # noqa: PLC0415

    beat["kling_o3_selected_option_key"] = canonical_o3_option_key(beat_id, vp)
    still = beat_is_still_insert(beat) if still_insert is None else still_insert
    if still:
        beat["kling_o3_status"] = "still_rendered"
        beat["status"] = "draft"
        beat.pop("kling_o3_still_stitch_approved", None)
        beat.pop("kling_o3_still_stitch_approved_at", None)
    else:
        beat["kling_o3_status"] = "approved"
        beat["status"] = "approved"


def align_beat_active_delivery_clip(
    beat: dict,
    video_path: str | Path | None = None,
    *,
    mark_voice_fix_approved: bool = False,
    clear_voice_fix_error: bool = False,
) -> bool:
    """Promote on-disk delivery to active pointer — single write path for heal/reconcile/pipelines."""
    vp = str(video_path or beat.get("kling_o3_video_path") or "").strip()
    if not vp or not Path(vp).is_file():
        return False
    finalize_kling_delivery_clip(beat, vp)
    if mark_voice_fix_approved:
        beat["kling_o3_voice_fix_status"] = "approved"
    if clear_voice_fix_error:
        for key in (
            "kling_o3_voice_fix_error",
            "kling_o3_voice_fix_error_code",
            "kling_o3_voice_fix_ui_job_id",
            "kling_o3_voice_fix_job_pid",
            "kling_o3_voice_fix_phase",
        ):
            beat.pop(key, None)
    return True


def active_delivery_sidecar_fields(
    video_path: str | Path,
    *,
    mark_voice_fix_approved: bool = False,
) -> dict[str, str]:
    """Sidecar field bundle for pipeline finalize — use instead of inline approved writes."""
    beat: dict = {}
    align_beat_active_delivery_clip(
        beat,
        video_path,
        mark_voice_fix_approved=mark_voice_fix_approved,
    )
    keys = ("kling_o3_video_path", "kling_o3_status", "status")
    if mark_voice_fix_approved:
        keys = (*keys, "kling_o3_voice_fix_status")
    return {k: str(beat[k]) for k in keys if k in beat}
