"""O3_JOB_TRUTH_STACK_V1 — single read authority for beat O3 state.

Priority: terminal JSON > delivery on disk > sidecar fields > UI latch.
Session GET, poll merge, and gallery render must call ``resolve_beat_o3_truth`` only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

O3_JOB_TRUTH_STACK_V1 = "O3_JOB_TRUTH_STACK_V1"


def resolve_beat_o3_truth(
    beat_id: str,
    event_dir: str | Path,
    beat: dict,
    *,
    sidecar: dict | None = None,
    in_memory_jobs: dict | None = None,
    orphan_recovery=None,
    orphan_preview: bool = False,
) -> dict[str, Any]:
    """Return authoritative O3 view for one beat after reconcile + busy resolution."""
    import beat_generator as bg
    from o3_job_status_contract import beat_o3_operator_busy, resolve_o3_job_id_for_lifecycle
    from o3_session_terminal_reconcile import reconcile_beat_terminal_disk

    event_dir = Path(event_dir)
    sidecar = sidecar if isinstance(sidecar, dict) else {}
    working = dict(beat)

    from o3_generation_intent import load_intent_terminal, terminal_path_for_job

    job_id = resolve_o3_job_id_for_lifecycle(working)
    terminal_status = ""
    terminal_message = ""
    terminal = None
    if job_id:
        terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
        if terminal:
            terminal_status = str(terminal.get("status") or "")
            failure = terminal.get("failure") or {}
            if isinstance(failure, dict):
                terminal_message = str(failure.get("message") or "")

    reconcile_beat_terminal_disk(
        working,
        sidecar,
        event_dir,
        orphan_recovery=orphan_recovery,
        orphan_preview=orphan_preview,
    )

    video_path = str(working.get("kling_o3_video_path") or "")
    video_exists = bool(video_path and Path(video_path).is_file())
    kling_status = str(working.get("kling_o3_status") or "")
    voice_fix_status = str(working.get("kling_o3_voice_fix_status") or "")
    operator_busy = beat_o3_operator_busy(
        working,
        event_dir,
        in_memory_jobs=in_memory_jobs,
    )

    return {
        "beat_id": beat_id,
        "authority": O3_JOB_TRUTH_STACK_V1,
        "job_id": job_id,
        "terminal_status": terminal_status,
        "terminal_message": terminal_message,
        "kling_o3_status": kling_status,
        "kling_o3_voice_fix_status": voice_fix_status,
        "kling_o3_video_path": video_path if video_exists else "",
        "video_path_exists": video_exists,
        "operator_busy": operator_busy,
        "status": str(working.get("status") or ""),
        "kling_o3_generation": working.get("kling_o3_generation"),
        "kling_o3_options": list(working.get("kling_o3_options") or []),
        "reconciled_beat": working,
    }


def apply_session_o3_truth_fields(beat: dict, truth: dict[str, Any]) -> bool:
    """In-memory session GET merge — reconciled authority fields onto live beat."""
    return apply_beat_o3_truth_to_beat(beat, truth)


def resolve_beat_o3_truth_for_session_compose(
    beat: dict,
    sidecar: dict,
    *,
    server_event_dir: Path | None,
    library_event_dir: Path | None,
    scope_type: str,
    in_memory_jobs: dict | None = None,
) -> dict[str, Any] | None:
    """Session GET read path — try event-dir candidates; orphan preview only (no persist)."""
    from o3_generation_intent import resolve_o3_job_event_dir_candidates

    beat_id = str(beat.get("beat_id") or "").strip()
    if not beat_id:
        return None
    beat_event_dirs = resolve_o3_job_event_dir_candidates(
        beat_id,
        server_event_dir=server_event_dir,
        library_event_dir=library_event_dir,
        scope_type=scope_type,
    )
    truth: dict[str, Any] | None = None
    for ev in beat_event_dirs:
        before = dict(beat)
        truth = resolve_beat_o3_truth(
            beat_id,
            ev,
            beat,
            sidecar=sidecar,
            in_memory_jobs=in_memory_jobs,
            orphan_preview=True,
        )
        apply_session_o3_truth_fields(beat, truth)
        if beat != before:
            break
    return truth


def apply_beat_o3_truth_to_beat(beat: dict, truth: dict[str, Any]) -> bool:
    """Copy reconciled fields from truth snapshot back onto live beat dict."""
    reconciled = truth.get("reconciled_beat")
    if not isinstance(reconciled, dict):
        return False
    changed = False
    for key in (
        "status",
        "kling_o3_status",
        "kling_o3_voice_fix_status",
        "kling_o3_video_path",
        "kling_o3_generation",
        "kling_o3_options",
        "kling_o3_voice_fix_error",
        "kling_o3_voice_fix_error_code",
    ):
        if key in reconciled and beat.get(key) != reconciled.get(key):
            if reconciled.get(key) is None and key in beat:
                beat.pop(key, None)
            else:
                beat[key] = reconciled[key]
            changed = True
    return changed
