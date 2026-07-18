"""Session GET terminal disk reconcile — gallery + busy without poll memory.

Default session GET composes terminal + disk truth in-memory (read-only).
Persisted reconcile runs only via explicit operator entry points (finalize,
``force_reconcile_o3=1``, startup/admin repair).
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

_TERMINAL_OUTCOME_KEYS = (
    "kling_o3_options",
    "kling_o3_video_path",
    "kling_o3_generation",
    "kling_o3_selected_option_key",
    "kling_o3_selected_at",
    "kling_o3_status",
    "kling_o3_voice_fix_status",
    "kling_o3_voice_fix_error",
    "status",
    "o3_current_job_id",
    "kling_o3_voice_fix_ui_job_id",
)


def _beat_delta(before: dict, after: dict) -> dict[str, object]:
    delta: dict[str, object] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            delta[key] = after.get(key)
    return delta


def _resolve_intent_log_path(job_id: str, beat_id: str, event_dir: Path) -> Path | None:
    if not job_id or not beat_id:
        return None
    alt = event_dir / "arlo_o3_jobs" / f"{job_id}_{beat_id}.log"
    if alt.is_file():
        return alt
    legacy = event_dir / "arlo_o3_jobs" / f"{job_id}.log"
    return legacy if legacy.is_file() else None


def _generation_mode_for_beat(beat: dict) -> str:
    import beat_generator as bg

    mode = str(beat.get("o3_generate_mode") or beat.get("generation_mode") or "").strip()
    if mode:
        return mode
    if bg.beat_is_still_insert(beat):
        return bg.PIPELINE_MODE_STILL
    return bg.PIPELINE_MODE_O3


def reconcile_beat_terminal_disk(
    beat: dict,
    sidecar: dict,
    event_dir: Path,
    *,
    orphan_recovery=None,
    orphan_preview: bool = False,
) -> bool:
    """Merge terminal + disk deliveries into ``beat`` (in-memory). Returns True if mutated."""
    import beat_generator as bg
    from o3_generation_intent import (
        INTENT_TERMINAL_STATUSES,
        heal_o3_beat_after_aborted_attempt,
        load_intent_terminal,
        terminal_path_for_job,
    )
    from o3_job_status_contract import (
        clear_o3_pointer_if_terminal,
        resolve_o3_job_id_for_lifecycle,
        terminal_binds_active_lifecycle,
    )

    beat_id = str(beat.get("beat_id") or "").strip()
    if not beat_id:
        return False
    changed = False
    job_id = resolve_o3_job_id_for_lifecycle(beat)
    terminal = None
    if job_id:
        terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
    status = str((terminal or {}).get("status") or "").strip()

    if status in INTENT_TERMINAL_STATUSES:
        if status in ("done", "done_with_warning"):
            if bg.reconcile_beat_gallery_from_disk(beat, event_dir):
                changed = True
            log_path = _resolve_intent_log_path(job_id, beat_id, event_dir)
            if orphan_preview:
                touched, _ = bg.preview_orphan_o3_delivery_on_beat(
                    beat,
                    event_dir,
                    beat_id=beat_id,
                    log_path=str(log_path) if log_path else None,
                    make_active=True,
                )
                if touched:
                    changed = True
            elif orphan_recovery:
                recovered = orphan_recovery(
                    beat_id,
                    event_dir,
                    str(log_path) if log_path else None,
                    make_active=True,
                )
                if recovered:
                    changed = True
            if bg.auto_select_o3_option_for_generation_mode(
                beat,
                sidecar,
                _generation_mode_for_beat(beat),
            ):
                changed = True
        elif status == "failed":
            if not terminal_binds_active_lifecycle(beat, job_id):
                pass
            else:
                fail_msg = str((terminal.get("failure") or {}).get("message") or "")
                if fail_msg and beat.get("kling_o3_voice_fix_error") != fail_msg:
                    beat["kling_o3_voice_fix_error"] = fail_msg
                    changed = True
                from o3_generation_intent import restore_last_good_o3_delivery_after_failed_attempt

                intent_gen = None
                intent = (terminal or {}).get("intent") or {}
                if isinstance(intent, dict):
                    slot = intent.get("generation_slot") or intent.get("generation")
                    if slot and str(slot).startswith("g"):
                        try:
                            intent_gen = int(str(slot)[1:])
                        except ValueError:
                            intent_gen = None
                if restore_last_good_o3_delivery_after_failed_attempt(
                    beat,
                    event_dir,
                    failed_generation=intent_gen,
                ):
                    changed = True
                elif heal_o3_beat_after_aborted_attempt(beat, event_dir):
                    changed = True
        elif status == "cancelled":
            if heal_o3_beat_after_aborted_attempt(beat, event_dir):
                changed = True
    elif bg.reconcile_beat_gallery_from_disk(beat, event_dir):
        changed = True

    if clear_o3_pointer_if_terminal(beat, event_dir):
        changed = True
    return changed


def terminal_outcome_row(
    beat_id: str,
    before: dict,
    after: dict,
    *,
    job_id: str,
    terminal_status: str,
) -> dict[str, Any] | None:
    """Client toast payload when terminal reconcile changed gallery or error state."""
    if terminal_status not in {"done", "done_with_warning", "failed", "cancelled"}:
        return None
    delta = _beat_delta(
        {k: before.get(k) for k in _TERMINAL_OUTCOME_KEYS},
        {k: after.get(k) for k in _TERMINAL_OUTCOME_KEYS},
    )
    if not delta and terminal_status not in ("done", "done_with_warning", "failed"):
        return None
    row: dict[str, Any] = {
        "beat_id": beat_id,
        "status": terminal_status,
        "job_id": job_id or None,
    }
    video = str(after.get("kling_o3_video_path") or "").strip()
    if video:
        row["video_path"] = video
    gen = after.get("kling_o3_generation")
    if gen is not None:
        row["generation"] = gen
    err = str(after.get("kling_o3_voice_fix_error") or "").strip()
    if err:
        row["error"] = err
    if delta:
        row["reconciled"] = True
        row["persisted"] = True
    return row


def plan_session_terminal_reconcile(
    beats: list[dict],
    sidecar: dict,
    *,
    orphan_recovery,
    server_event_dir: Path | None = None,
    library_event_dir: Path | None = None,
    scope_type: str = "event",
) -> tuple[list[tuple[str, dict[str, object]]], list[dict[str, Any]]]:
    """Disk work outside sidecar lock — returns pending deltas + client outcome rows."""
    import beat_generator as bg
    from o3_generation_intent import (
        load_intent_terminal,
        resolve_o3_job_event_dir_candidates,
        terminal_path_for_job,
    )
    from o3_job_status_contract import resolve_o3_job_id_for_lifecycle

    pending: list[tuple[str, dict[str, object]]] = []
    outcomes: list[dict[str, Any]] = []
    for beat in beats:
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            continue
        beat_event_dirs = resolve_o3_job_event_dir_candidates(
            beat_id,
            server_event_dir=server_event_dir,
            library_event_dir=library_event_dir,
            scope_type=scope_type,
        )
        beat_event = beat_event_dirs[0]
        before = copy.deepcopy(beat)
        beat_work = copy.deepcopy(beat)
        reconciled = False
        for ev in beat_event_dirs:
            if reconcile_beat_terminal_disk(
                beat_work,
                sidecar,
                ev,
                orphan_recovery=orphan_recovery,
            ):
                reconciled = True
                beat_event = ev
                break
        if not reconciled:
            continue
        delta = _beat_delta(beat, beat_work)
        job_id = resolve_o3_job_id_for_lifecycle(before) or resolve_o3_job_id_for_lifecycle(beat_work)
        terminal_status = ""
        if job_id:
            terminal = load_intent_terminal(terminal_path_for_job(job_id, beat_event))
            terminal_status = str((terminal or {}).get("status") or "").strip()
        outcome = terminal_outcome_row(
            beat_id,
            before,
            beat_work,
            job_id=job_id,
            terminal_status=terminal_status,
        )
        if delta:
            pending.append((beat_id, delta))
        if outcome and (delta or terminal_status in ("done", "done_with_warning", "failed")):
            outcomes.append(outcome)
    return pending, outcomes


def compose_session_terminal_view(
    beats: list[dict],
    sidecar: dict,
    *,
    server_event_dir: Path | None = None,
    library_event_dir: Path | None = None,
    scope_type: str = "event",
) -> list[dict[str, Any]]:
    """Read-only session GET — merge terminal/disk via O3_JOB_TRUTH_STACK_V1; no sidecar persist."""
    import copy

    from o3_job_truth import resolve_beat_o3_truth_for_session_compose

    outcomes: list[dict[str, Any]] = []
    for beat in beats:
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            continue
        before = copy.deepcopy(beat)
        truth = resolve_beat_o3_truth_for_session_compose(
            beat,
            sidecar,
            server_event_dir=server_event_dir,
            library_event_dir=library_event_dir,
            scope_type=scope_type,
        )
        if not truth:
            continue
        job_id = str(truth.get("job_id") or "")
        terminal_status = str(truth.get("terminal_status") or "")
        outcome = terminal_outcome_row(
            beat_id,
            before,
            beat,
            job_id=job_id,
            terminal_status=terminal_status,
        )
        if outcome and (
            before != beat
            or terminal_status in ("done", "done_with_warning", "failed")
        ):
            outcomes.append(outcome)
    return outcomes


def playback_event_dir_for_source(source_path: Path, server_event_dir: Path, library_event_dir: Path | None) -> Path:
    """Event_N dir that owns ``source_path`` — milestone clips often live under library Event_1."""
    src = source_path.resolve()
    prod = server_event_dir.parent
    for part in src.parts:
        if re.fullmatch(r"Event_\d+", part):
            candidate = prod / part
            if candidate.is_dir():
                return candidate
    if library_event_dir is not None:
        lib = Path(library_event_dir)
        if lib.is_dir():
            return lib
    return server_event_dir
