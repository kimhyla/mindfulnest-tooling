"""STITCH_ARTIFACT_ORCHESTRATOR_V1 — serialized ambient→mux artifact builds off HTTP thread.

Category fix (RC16): save_job and stitch_preview must not run parallel ffmpeg tiers on
STITCH_CACHE_BUILD_LOCK_V1. One orchestrator worker per stitch job runs:
  ambient tier (when drift/missing) → mux tier (when SFX/ambient geometry requires mux).

STITCH_SAVE_ASYNC_ARTIFACTS_V1 remains the save-fast marker; orchestrator replaces
ambient-only async submit.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STITCH_SAVE_ASYNC_ARTIFACTS_V1 = "STITCH_SAVE_ASYNC_ARTIFACTS_V1"
STITCH_ARTIFACT_ORCHESTRATOR_V1 = "STITCH_ARTIFACT_ORCHESTRATOR_V1"
TERMINAL_STATUSES = frozenset({"done", "failed"})
STALE_RUNNING_AFTER_S = float(os.environ.get("MN_STITCH_ARTIFACT_STALE_S", "900"))

# One active worker thread per stitch job name (process-local).
_worker_guard = threading.Lock()
_active_workers: dict[str, threading.Thread] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_builds_dir(event_dir: str | Path) -> Path:
    p = Path(event_dir) / "stitch_artifact_build_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _job_path(event_dir: str | Path, build_id: str) -> Path:
    return artifact_builds_dir(event_dir) / f"{build_id}.json"


def new_build_id() -> str:
    import uuid

    return str(uuid.uuid4())[:12]


def save_build(event_dir: str | Path, job: dict[str, Any]) -> None:
    job["updated_at"] = _utc_now()
    path = _job_path(event_dir, job["build_id"])
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_build(event_dir: str | Path, build_id: str) -> dict[str, Any] | None:
    path = _job_path(event_dir, build_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_builds(event_dir: str | Path) -> list[dict[str, Any]]:
    root = artifact_builds_dir(event_dir)
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _parse_updated_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def reconcile_stale_artifact_builds(
    event_dir: str | Path,
    *,
    stale_after_s: float = STALE_RUNNING_AFTER_S,
) -> list[str]:
    """Mark orphan ``running`` builds failed when worker died without finalize."""
    now = datetime.now(timezone.utc)
    reconciled: list[str] = []
    for row in list_builds(event_dir):
        if row.get("status") != "running":
            continue
        updated = _parse_updated_at(row.get("updated_at"))
        if updated is None:
            continue
        age_s = (now - updated.astimezone(timezone.utc)).total_seconds()
        if age_s < stale_after_s:
            continue
        build_id = str(row.get("build_id") or "")
        if not build_id:
            continue
        finalize_build(
            event_dir,
            build_id,
            "failed",
            error=f"stale_running_reconciled_after_{int(age_s)}s",
        )
        reconciled.append(build_id)
    return reconciled


def find_active_build_for_stitch_job(
    event_dir: str | Path,
    stitch_job_name: str,
) -> dict[str, Any] | None:
    reconcile_stale_artifact_builds(event_dir)
    for row in reversed(list_builds(event_dir)):
        if row.get("stitch_job_name") != stitch_job_name:
            continue
        if row.get("status") in TERMINAL_STATUSES:
            continue
        return row
    return None


def build_poll_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "build_id": job.get("build_id"),
        "status": job.get("status"),
        "phase": job.get("phase"),
        "message": job.get("message"),
        "stitch_job_name": job.get("stitch_job_name"),
        "ambient_rebuild_keys": job.get("ambient_rebuild_keys") or [],
        "mux_rebuild_keys": job.get("mux_rebuild_keys") or [],
        "built_slots": job.get("built_slots"),
        "error": job.get("error"),
        "code": STITCH_ARTIFACT_ORCHESTRATOR_V1,
        "async_artifact_code": STITCH_SAVE_ASYNC_ARTIFACTS_V1,
    }


def create_build(
    event_dir: str | Path,
    *,
    build_id: str,
    stitch_job_name: str,
    ambient_rebuild_keys: list[str],
    mux_rebuild_keys: list[str],
    trigger: str = "save_job",
) -> dict[str, Any]:
    now = _utc_now()
    job = {
        "build_id": build_id,
        "status": "queued",
        "phase": "queued",
        "message": "Artifact rebuild queued",
        "stitch_job_name": stitch_job_name,
        "ambient_rebuild_keys": list(ambient_rebuild_keys),
        "mux_rebuild_keys": list(mux_rebuild_keys),
        "trigger": trigger,
        "started_at": now,
        "updated_at": now,
        "code": STITCH_ARTIFACT_ORCHESTRATOR_V1,
        "async_artifact_code": STITCH_SAVE_ASYNC_ARTIFACTS_V1,
    }
    save_build(event_dir, job)
    return job


def update_build_progress(
    event_dir: str | Path,
    build_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    message: str | None = None,
    **extra: Any,
) -> dict[str, Any] | None:
    job = load_build(event_dir, build_id)
    if not job:
        return None
    if status is not None:
        job["status"] = status
    if phase is not None:
        job["phase"] = phase
    if message is not None:
        job["message"] = message
    job.update(extra)
    save_build(event_dir, job)
    return job


def finalize_build(
    event_dir: str | Path,
    build_id: str,
    status: str,
    *,
    built_slots: dict | None = None,
    error: str | None = None,
) -> None:
    update_build_progress(
        event_dir,
        build_id,
        status=status,
        phase=status,
        message=(
            "Artifact rebuild complete"
            if status == "done"
            else (error or "Artifact rebuild failed")
        ),
        built_slots=built_slots,
        error=error,
    )


def wait_for_artifact_build(
    event_dir: str | Path,
    build_id: str,
    *,
    timeout_s: float = 900.0,
    poll_s: float = 0.5,
) -> dict[str, Any]:
    """Block until build reaches terminal status (preview / warm paths)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        reconcile_stale_artifact_builds(event_dir)
        job = load_build(event_dir, build_id)
        if not job:
            raise RuntimeError(f"artifact build {build_id!r} missing")
        status = job.get("status")
        if status == "done":
            return job
        if status == "failed":
            raise RuntimeError(job.get("error") or "artifact build failed")
        time.sleep(poll_s)
    raise RuntimeError(
        f"artifact build {build_id!r} timed out after {timeout_s:.0f}s",
    )


def _build_mux_for_slot(h, *, stitch_job_name: str, slot_key: str) -> dict[str, Any]:
    from server_handlers.stitch_editor import (  # noqa: PLC0415
        build_stitch_slot_mux_preview_file,
        stitch_state_store_for_job,
    )
    from server_handlers.stitch_media_artifacts import (  # noqa: PLC0415
        attach_stitch_slot_derived_media_urls,
        persist_stitch_slot_media_artifacts,
    )
    from server_handlers.stitch_media_sig import (  # noqa: PLC0415
        compute_stitch_mix_sig_from_slot,
        _video_mtime_ms,
    )

    stitch_store = stitch_state_store_for_job(h, stitch_job_name)
    state = stitch_store.read_state() or {}
    slot = ((state.get("jobs") or {}).get(stitch_job_name) or {}).get("slots", {}).get(slot_key)
    if not isinstance(slot, dict):
        raise RuntimeError(f"slot {slot_key!r} missing for mux build")
    mix_sig = compute_stitch_mix_sig_from_slot(h, slot)
    hash_id, dur_ms = build_stitch_slot_mux_preview_file(h, slot)
    video_path = (slot.get("video_path") or "").strip()
    mux_video_mtime_ms: int | None = None
    if video_path:
        try:
            mux_video_mtime_ms = _video_mtime_ms(str(h._stitch_resolve_path(video_path)))
        except (ValueError, TypeError, OSError):
            mux_video_mtime_ms = None
    persist_stitch_slot_media_artifacts(
        h,
        stitch_job_name,
        slot_key,
        mix_sig=mix_sig,
        mux_preview_hash=hash_id,
        mux_preview_duration_ms=dur_ms,
        mux_video_path=video_path or None,
        mux_video_mtime_ms=mux_video_mtime_ms,
    )
    state = stitch_store.read_state() or {}
    refreshed = (
        ((state.get("jobs") or {}).get(stitch_job_name) or {})
        .get("slots", {})
        .get(slot_key)
    )
    if isinstance(refreshed, dict):
        attach_stitch_slot_derived_media_urls(h, refreshed)
    return {
        "ok": True,
        "kind": "mux_preview",
        "mux_preview_hash": hash_id,
        "mux_preview_duration_ms": dur_ms,
        "_mux_preview_url": (refreshed or {}).get("_mux_preview_url") if isinstance(refreshed, dict) else None,
    }


def _execute_artifact_plan(
    h,
    *,
    build_id: str,
    stitch_job_name: str,
    ambient_keys: list[str],
    mux_keys: list[str],
    pin: dict,
) -> None:
    from server_handlers.stitch_editor import (  # noqa: PLC0415
        rebuild_stitch_ambient_mixes_for_job,
        stitch_state_store_for_job,
    )

    event_dir = h.app.event_dir
    stitch_store = stitch_state_store_for_job(h, stitch_job_name)
    orig_stitch_state = None
    if stitch_store is not h.app.stitch_state:
        orig_stitch_state = h.app.stitch_state
        h.app.stitch_state = stitch_store
    built_slots: dict[str, Any] = {}
    try:
        if hasattr(h, "_check_event_pin") and not h._check_event_pin(pin, "stitch_artifact_build"):
            finalize_build(
                event_dir,
                build_id,
                "failed",
                error="event_changed_mid_job",
            )
            return

        update_build_progress(
            event_dir,
            build_id,
            status="running",
            phase="ambient_mix",
            message=(
                f"Rebuilding ambient mixes for {', '.join(ambient_keys) or '—'}…"
                if ambient_keys
                else "Ambient tier skipped (fresh)"
            ),
        )
        if ambient_keys:
            ambient_built = rebuild_stitch_ambient_mixes_for_job(
                h,
                stitch_job_name,
                slot_keys=list(ambient_keys),
            )
            built_slots.update(ambient_built)

        if mux_keys:
            update_build_progress(
                event_dir,
                build_id,
                phase="mux_preview",
                message=f"Building mux preview for {', '.join(mux_keys)}…",
            )
            for slot_key in mux_keys:
                built_slots[slot_key] = _build_mux_for_slot(
                    h,
                    stitch_job_name=stitch_job_name,
                    slot_key=slot_key,
                )

        finalize_build(event_dir, build_id, "done", built_slots=built_slots)
    except Exception as exc:
        traceback.print_exc()
        finalize_build(event_dir, build_id, "failed", error=str(exc))
    finally:
        if orig_stitch_state is not None:
            h.app.stitch_state = orig_stitch_state


def _start_worker(
    h,
    *,
    build_id: str,
    stitch_job_name: str,
    ambient_keys: list[str],
    mux_keys: list[str],
    pin: dict,
) -> None:
    def _run() -> None:
        try:
            _execute_artifact_plan(
                h,
                build_id=build_id,
                stitch_job_name=stitch_job_name,
                ambient_keys=ambient_keys,
                mux_keys=mux_keys,
                pin=pin,
            )
        finally:
            with _worker_guard:
                if _active_workers.get(stitch_job_name) is worker:
                    _active_workers.pop(stitch_job_name, None)

    worker = threading.Thread(
        target=_run,
        daemon=True,
        name=f"stitch-artifact-{build_id}",
    )
    with _worker_guard:
        _active_workers[stitch_job_name] = worker
    worker.start()


def submit_stitch_artifact_build_plan(
    h,
    *,
    stitch_job_name: str,
    ambient_keys: list[str],
    mux_keys: list[str],
    pin: dict,
    trigger: str = "save_job",
) -> dict[str, Any] | None:
    """Queue serialized ambient→mux ffmpeg; return build record."""
    ambient_keys = [k for k in ambient_keys if k]
    mux_keys = [k for k in mux_keys if k]
    if not ambient_keys and not mux_keys:
        return None

    event_dir = h.app.event_dir
    reconcile_stale_artifact_builds(event_dir)
    existing = find_active_build_for_stitch_job(event_dir, stitch_job_name)
    if existing:
        return existing

    build_id = new_build_id()
    job = create_build(
        event_dir,
        build_id=build_id,
        stitch_job_name=stitch_job_name,
        ambient_rebuild_keys=ambient_keys,
        mux_rebuild_keys=mux_keys,
        trigger=trigger,
    )
    _start_worker(
        h,
        build_id=build_id,
        stitch_job_name=stitch_job_name,
        ambient_keys=ambient_keys,
        mux_keys=mux_keys,
        pin=pin,
    )
    return job


def submit_stitch_ambient_rebuild(
    h,
    *,
    stitch_job_name: str,
    slot_keys: list[str],
    pin: dict,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper — ambient-only plan (prefer submit_stitch_artifact_build_plan)."""
    return submit_stitch_artifact_build_plan(
        h,
        stitch_job_name=stitch_job_name,
        ambient_keys=slot_keys,
        mux_keys=[],
        pin=pin,
        trigger="ambient_only",
    )


def plan_playback_ladder_warm(
    h,
    stitch_job_name: str,
    slot_key: str,
) -> tuple[list[str], list[str]]:
    """Return (ambient_keys, mux_keys) to materialize full playback ladder for warm."""
    from server_handlers.stitch_slot_edit_dispatch import slot_needs_ambient_rebuild  # noqa: PLC0415
    from server_handlers.stitch_editor import stitch_state_store_for_job  # noqa: PLC0415
    from server_handlers.stitch_media_artifacts import _stitch_slot_has_sfx  # noqa: PLC0415

    stitch_store = stitch_state_store_for_job(h, stitch_job_name)
    state = stitch_store.read_state() or {}
    slot = ((state.get("jobs") or {}).get(stitch_job_name) or {}).get("slots", {}).get(slot_key)
    if not isinstance(slot, dict):
        return [], []
    prev: dict = {}
    ambient_keys: list[str] = []
    if slot_needs_ambient_rebuild(h, prev, slot):
        ambient_keys = [slot_key]
    mux_keys: list[str] = []
    if _stitch_slot_has_sfx(slot) or (slot.get("ambient_bed") or "").strip():
        mux_keys = [slot_key]
    return ambient_keys, mux_keys
