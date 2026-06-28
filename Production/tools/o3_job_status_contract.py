"""Shared O3 job lifecycle + gallery contract — Python server + Beat Gen UI.

Truth model (BG_BEAT_JOB_TRUTH_GALLERY_SPEC_v1):
- *Lifecycle:* ``{job_id}_terminal.json`` + ``beat.o3_current_job_id`` (+ live subprocess).
- *Gallery:* sidecar ``kling_o3_options`` / ``kling_o3_video_path`` — not busy authority.
- *Intent:* ``{job_id}_intent.json`` is audit-only — not a UI/pipeline lock.
"""
from __future__ import annotations

from pathlib import Path

O3_VOICE_FIX_RUNNING_STATUSES = frozenset({
    "o3_running", "job_running", "job_starting", "visual_running",
    "lipsync_running", "tts_ready", "o3_element_running",
})
O3_BEAT_STATUS_PREFIXES = ("o3_voice_job_", "o3_element_")
O3_VOICE_FIX_RUNNING_PHASES = frozenset({"subprocess", "o3_element", "queued"})
INTENT_TERMINAL_STATUSES = frozenset({"done", "failed", "done_with_warning", "cancelled"})
O3_VOICE_FIX_TERMINAL_FAILURE_STATUSES = frozenset({
    "failed", "failed_o3", "failed_provider_fetch", "failed_provider_sub720",
})

O3_JOB_CACHE_FIELDS = (
    "kling_o3_voice_fix_ui_job_id",
    "kling_o3_voice_fix_job_log_path",
    "kling_o3_voice_fix_phase",
    "kling_o3_voice_fix_job_pid",
    "kling_o3_voice_fix_job_started_at",
    "o3_active_intent_id",
    "o3_active_intent_job_id",
    "o3_current_job_id",
)


def voice_fix_is_terminal_failure(voice_fix_status: str | None) -> bool:
    """True when lipsync/O3 voice pipeline failed and must not promote to done."""
    voice_fix = str(voice_fix_status or "").strip().lower()
    if voice_fix in O3_VOICE_FIX_TERMINAL_FAILURE_STATUSES:
        return True
    return voice_fix.startswith("failed")


def resolve_o3_current_job_id(beat: dict) -> str:
    """Active attempt pointer — ``o3_current_job_id`` only (M2 migration)."""
    return str(beat.get("o3_current_job_id") or "").strip()


def resolve_o3_job_id_for_lifecycle(beat: dict) -> str:
    """Job id for terminal/subprocess busy — canonical pointer then legacy UI/log fields."""
    job_id = resolve_o3_current_job_id(beat)
    if job_id:
        return job_id
    from o3_generation_intent import job_id_from_beat

    return job_id_from_beat(beat)


def clear_o3_job_cache_fields(beat: dict) -> None:
    """Remove lifecycle cache fields; never touches gallery options or approved path."""
    for key in O3_JOB_CACHE_FIELDS:
        beat.pop(key, None)


def clear_o3_pointer_if_terminal(beat: dict, event_dir: Path | None) -> bool:
    """Clear stale pointer when terminal proves the attempt finished."""
    from o3_generation_intent import (
        intent_event_dir_for_beat,
        load_intent_terminal,
        terminal_path_for_job,
    )

    beat_id = str(beat.get("beat_id") or "").strip()
    job_id = resolve_o3_job_id_for_lifecycle(beat)
    if not beat_id or not job_id:
        return False
    ev = intent_event_dir_for_beat(beat_id, event_dir)
    terminal = load_intent_terminal(terminal_path_for_job(job_id, ev))
    if not terminal:
        return False
    status = str(terminal.get("status") or "").strip()
    if status not in INTENT_TERMINAL_STATUSES:
        return False
    had_pointer = bool(
        beat.get("o3_current_job_id")
        or beat.get("kling_o3_voice_fix_ui_job_id")
    )
    clear_o3_job_cache_fields(beat)
    if str(beat.get("status") or "").startswith(("o3_voice_job_", "o3_element_")):
        if status == "done" or status == "done_with_warning":
            if str(beat.get("kling_o3_status") or "") == "approved":
                beat["status"] = "approved"
    if str(beat.get("kling_o3_voice_fix_status") or "") in O3_VOICE_FIX_RUNNING_STATUSES:
        if status in ("done", "done_with_warning"):
            beat["kling_o3_voice_fix_status"] = "approved"
        elif status == "failed":
            fail_msg = str((terminal.get("failure") or {}).get("message") or "")
            if fail_msg:
                beat["kling_o3_voice_fix_error"] = fail_msg
            from o3_generation_intent import heal_o3_beat_after_aborted_attempt

            if not heal_o3_beat_after_aborted_attempt(beat):
                video = str(beat.get("kling_o3_video_path") or "")
                if video and Path(video).is_file():
                    from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

                    align_beat_active_delivery_clip(
                        beat,
                        video,
                        mark_voice_fix_approved=True,
                    )
    return had_pointer


def _in_memory_o3_job_running(
    job_id: str,
    beat_id: str,
    in_memory_jobs: dict | None,
) -> bool:
    if not in_memory_jobs:
        return False
    row = in_memory_jobs.get(job_id)
    if not isinstance(row, dict):
        return False
    if str(row.get("beat_id") or "").strip() != beat_id:
        return False
    proc = row.get("process")
    if proc is not None and hasattr(proc, "poll"):
        return proc.poll() is None
    return bool(row.get("running"))


def beat_job_busy_in_event_dirs(
    beat: dict,
    event_dirs: list[Path] | tuple[Path, ...],
    *,
    in_memory_jobs: dict | None = None,
) -> bool:
    """True when any candidate Event dir reports the beat job running."""
    for event_dir in event_dirs:
        if beat_job_busy(beat, event_dir, in_memory_jobs=in_memory_jobs):
            return True
    return False


def beat_job_busy(
    beat: dict,
    event_dir: Path | None = None,
    *,
    in_memory_jobs: dict | None = None,
) -> bool:
    """Server-owned busy — terminal running + live subprocess, or spawn in-flight window."""
    from o3_generation_intent import (
        INTENT_RUNNING_STATUS,
        INTENT_TERMINAL_STATUSES,
        O3_SPAWN_IN_FLIGHT_S,
        intent_event_dir_for_beat,
        load_generation_intent,
        load_intent_terminal,
        o3_subprocess_is_live,
        intent_path_for_job,
        terminal_path_for_job,
    )

    beat_id = str(beat.get("beat_id") or "").strip()
    job_id = resolve_o3_job_id_for_lifecycle(beat)
    if not job_id:
        return False
    ev = intent_event_dir_for_beat(beat_id, event_dir) if beat_id else (event_dir or Path())
    terminal = load_intent_terminal(terminal_path_for_job(job_id, ev))
    term_status = str((terminal or {}).get("status") or "").strip()
    if term_status in INTENT_TERMINAL_STATUSES:
        from o3_gallery_closure import beat_gallery_closure_pending

        if term_status in ("done", "done_with_warning") and beat_gallery_closure_pending(
            beat,
            ev,
            terminal=terminal,
            job_id=job_id,
        ):
            return True
        return False
    if term_status == INTENT_RUNNING_STATUS:
        return o3_subprocess_is_live(job_id, beat_id, ev, in_memory_jobs=in_memory_jobs)
    if not terminal:
        intent_path = intent_path_for_job(job_id, ev)
        if intent_path.is_file():
            try:
                intent = load_generation_intent(intent_path)
                committed_at = str(intent.get("committed_at") or "").strip()
                if committed_at:
                    from datetime import datetime, timezone

                    committed_dt = datetime.fromisoformat(committed_at.replace("Z", "+00:00"))
                    if committed_dt.tzinfo is None:
                        committed_dt = committed_dt.replace(tzinfo=timezone.utc)
                    age_s = (datetime.now(timezone.utc) - committed_dt).total_seconds()
                    if age_s <= O3_SPAWN_IN_FLIGHT_S:
                        return True
            except (OSError, json.JSONDecodeError, ValueError, TypeError):
                pass
    return False


def beat_o3_operator_busy(
    beat: dict,
    event_dir: Path | None = None,
    *,
    in_memory_jobs: dict | None = None,
) -> bool:
    """Operator/server gate — terminal + pointer + subprocess (same as ``beat_job_busy``)."""
    beat_id = str(beat.get("beat_id") or "").strip()
    if event_dir is None and beat_id:
        try:
            import beat_generator as bg

            event_dir = bg.event_dir_for_beat_id(beat_id)
        except Exception:
            event_dir = None
    return beat_job_busy(beat, event_dir, in_memory_jobs=in_memory_jobs)


def beat_o3_voice_job_running(beat: dict) -> bool:
    """Legacy sidecar-cache running heuristic — not authoritative for UI busy."""
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
