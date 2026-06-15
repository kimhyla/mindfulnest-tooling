"""Shared O3 voice-job running detection — keep Python server + Beat Gen UI in sync."""
from __future__ import annotations

O3_VOICE_FIX_RUNNING_STATUSES = frozenset({
    "o3_running", "job_running", "job_starting", "visual_running",
    "lipsync_running", "tts_ready", "o3_element_running",
})
O3_BEAT_STATUS_PREFIXES = ("o3_voice_job_", "o3_element_")
O3_VOICE_FIX_RUNNING_PHASES = frozenset({"subprocess", "o3_element", "queued"})
INTENT_TERMINAL_STATUSES = frozenset({"done", "failed", "done_with_warning"})

def beat_o3_voice_job_running(beat: dict) -> bool:
    status = str(beat.get("status") or "")
    voice_fix = str(beat.get("kling_o3_voice_fix_status") or "")
    phase = str(beat.get("kling_o3_voice_fix_phase") or "").lower()
    if any(status.startswith(prefix) for prefix in O3_BEAT_STATUS_PREFIXES):
        return True
    if voice_fix in O3_VOICE_FIX_RUNNING_STATUSES:
        return True
    job_id = str(beat.get("kling_o3_voice_fix_ui_job_id") or "").strip()
    if job_id and phase in O3_VOICE_FIX_RUNNING_PHASES and not voice_fix.startswith("failed"):
        return True
    if job_id and not voice_fix.startswith("failed") and voice_fix != "approved":
        return True
    return False
