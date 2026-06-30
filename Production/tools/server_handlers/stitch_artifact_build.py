"""STITCH_SAVE_ASYNC_ARTIFACTS_V1 — ambient mix rebuild off the save_job HTTP thread.

Category fix: POST /api/stitch_editor/job must persist JSON immediately and queue
ffmpeg ambient bakes. Synchronous rebuild blocked g4-pre bootstrap (600s+) and
contended with load_job on the global stitch cache lock.
"""
from __future__ import annotations

import json
import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STITCH_SAVE_ASYNC_ARTIFACTS_V1 = "STITCH_SAVE_ASYNC_ARTIFACTS_V1"
TERMINAL_STATUSES = frozenset({"done", "failed"})


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


def find_active_build_for_stitch_job(
    event_dir: str | Path,
    stitch_job_name: str,
) -> dict[str, Any] | None:
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
        "built_slots": job.get("built_slots"),
        "error": job.get("error"),
        "code": STITCH_SAVE_ASYNC_ARTIFACTS_V1,
    }


def create_build(
    event_dir: str | Path,
    *,
    build_id: str,
    stitch_job_name: str,
    ambient_rebuild_keys: list[str],
) -> dict[str, Any]:
    now = _utc_now()
    job = {
        "build_id": build_id,
        "status": "queued",
        "phase": "queued",
        "message": "Ambient artifact rebuild queued",
        "stitch_job_name": stitch_job_name,
        "ambient_rebuild_keys": list(ambient_rebuild_keys),
        "started_at": now,
        "updated_at": now,
        "code": STITCH_SAVE_ASYNC_ARTIFACTS_V1,
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
        message="Ambient rebuild complete" if status == "done" else (error or "Ambient rebuild failed"),
        built_slots=built_slots,
        error=error,
    )


def _execute_stitch_ambient_rebuild(
    h,
    *,
    build_id: str,
    stitch_job_name: str,
    slot_keys: list[str],
    pin: dict,
) -> None:
    from server_handlers.stitch_editor import rebuild_stitch_ambient_mixes_for_job  # noqa: PLC0415

    event_dir = h.app.event_dir
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
            message=f"Rebuilding ambient mixes for {', '.join(slot_keys) or '—'}…",
        )
        built = rebuild_stitch_ambient_mixes_for_job(
            h,
            stitch_job_name,
            slot_keys=slot_keys,
        )
        finalize_build(event_dir, build_id, "done", built_slots=built)
    except Exception as exc:
        traceback.print_exc()
        finalize_build(event_dir, build_id, "failed", error=str(exc))


def submit_stitch_ambient_rebuild(
    h,
    *,
    stitch_job_name: str,
    slot_keys: list[str],
    pin: dict,
) -> dict[str, Any] | None:
    """Queue ambient ffmpeg off the save_job thread; return build record."""
    if not slot_keys:
        return None

    event_dir = h.app.event_dir
    existing = find_active_build_for_stitch_job(event_dir, stitch_job_name)
    if existing:
        return existing

    build_id = new_build_id()
    job = create_build(
        event_dir,
        build_id=build_id,
        stitch_job_name=stitch_job_name,
        ambient_rebuild_keys=slot_keys,
    )

    worker = threading.Thread(
        target=_execute_stitch_ambient_rebuild,
        args=(h,),
        kwargs={
            "build_id": build_id,
            "stitch_job_name": stitch_job_name,
            "slot_keys": list(slot_keys),
            "pin": dict(pin),
        },
        daemon=True,
        name=f"stitch-artifact-{build_id}",
    )
    worker.start()
    return job
