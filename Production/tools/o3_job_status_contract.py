"""Shared O3 voice-job running detection — keep Python server + Beat Gen UI in sync."""
from __future__ import annotations

O3_VOICE_FIX_RUNNING_STATUSES = frozenset({
    "o3_running", "job_running", "job_starting", "visual_running",
    "lipsync_running", "tts_ready", "o3_element_running",
})
O3_BEAT_STATUS_PREFIXES = ("o3_voice_job_", "o3_element_")
O3_VOICE_FIX_RUNNING_PHASES = frozenset({"subprocess", "o3_element", "queued"})
INTENT_TERMINAL_STATUSES = frozenset({"done", "failed", "done_with_warning"})
O3_VOICE_FIX_TERMINAL_FAILURE_STATUSES = frozenset({
    "failed", "failed_o3", "failed_provider_fetch", "failed_provider_sub720",
})
# Failed voice-fix attempts that rejected new output but left prior approved O3 clip active.
O3_VOICE_FIX_SOFT_REJECT_KEPT_CLIP_STATUSES = frozenset({
    "failed_provider_sub720",
})
_SOFT_REJECT_KEPT_CLIP_ERROR_MARKERS = (
    "kling lipsync returned sub-720p output",
    "previous approved clip was kept active",
)


def voice_fix_is_terminal_failure(voice_fix_status: str | None) -> bool:
    """True when lipsync/O3 voice pipeline failed and must not promote to done."""
    voice_fix = str(voice_fix_status or "").strip().lower()
    if voice_fix in O3_VOICE_FIX_TERMINAL_FAILURE_STATUSES:
        return True
    return voice_fix.startswith("failed")


def voice_fix_soft_reject_kept_approved_clip(
    beat: dict,
    *,
    video_path_exists: bool | None = None,
) -> bool:
    """True when a failed attempt did not replace an already-approved O3 clip."""
    if str(beat.get("kling_o3_status") or "") != "approved":
        return False
    video_path = str(beat.get("kling_o3_video_path") or "").strip()
    if not video_path:
        return False
    if video_path_exists is False:
        return False
    if video_path_exists is None:
        from pathlib import Path

        if not Path(video_path).is_file():
            return False
    voice_fix = str(beat.get("kling_o3_voice_fix_status") or "").strip().lower()
    if voice_fix in O3_VOICE_FIX_SOFT_REJECT_KEPT_CLIP_STATUSES:
        return True
    err = str(beat.get("kling_o3_voice_fix_error") or "").strip().lower()
    if not voice_fix.startswith("failed") or not err:
        return False
    return any(marker in err for marker in _SOFT_REJECT_KEPT_CLIP_ERROR_MARKERS)


def beat_o3_voice_job_running(beat: dict) -> bool:
    status = str(beat.get("status") or "")
    voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
    phase = str(beat.get("kling_o3_voice_fix_phase") or "").lower()
    if any(status.startswith(prefix) for prefix in O3_BEAT_STATUS_PREFIXES):
        return True
    if voice_fix in O3_VOICE_FIX_RUNNING_STATUSES:
        return True
    job_id = str(beat.get("kling_o3_voice_fix_ui_job_id") or "").strip()
    if job_id and phase in O3_VOICE_FIX_RUNNING_PHASES and not voice_fix_is_terminal_failure(voice_fix):
        return True
    if job_id and not voice_fix_is_terminal_failure(voice_fix) and voice_fix != "approved":
        return True
    return False
