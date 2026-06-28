"""STITCH_BAKE_JOB_TRUTH_V1 — durable on-disk stitch module bake jobs."""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STITCH_BAKE_JOB_TRUTH_V1 = "STITCH_BAKE_JOB_TRUTH_V1"
TERMINAL_BAKE_STATUSES = frozenset({"done", "failed", "interrupted"})


def stitch_bake_jobs_dir(event_dir: str | Path) -> Path:
    p = Path(event_dir) / "stitch_bake_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _job_path(event_dir: str | Path, job_id: str) -> Path:
    return stitch_bake_jobs_dir(event_dir) / f"{job_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return str(uuid.uuid4())[:12]


def save_job(event_dir: str | Path, job: dict[str, Any]) -> None:
    job["updated_at"] = _utc_now()
    path = _job_path(event_dir, job["job_id"])
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_job(event_dir: str | Path, job_id: str) -> dict[str, Any] | None:
    path = _job_path(event_dir, job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_jobs(event_dir: str | Path) -> list[dict[str, Any]]:
    root = stitch_bake_jobs_dir(event_dir)
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def bake_lock_is_free(lock_path: Path) -> bool:
    """True when no process holds the global stitch bake flock lock."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except (BlockingIOError, OSError):
        return False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def create_job(
    event_dir: str | Path,
    *,
    job_id: str,
    stitch_job_name: str,
    scope_event_id: str,
) -> dict[str, Any]:
    now = _utc_now()
    job = {
        "job_id": job_id,
        "status": "queued",
        "phase": "queued",
        "message": "Bake queued",
        "stitch_job_name": stitch_job_name,
        "scope_event_id": scope_event_id,
        "started_at": now,
        "updated_at": now,
        "code": STITCH_BAKE_JOB_TRUTH_V1,
    }
    save_job(event_dir, job)
    return job


def update_job_progress(
    event_dir: str | Path,
    job_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    message: str | None = None,
    **extra: Any,
) -> dict[str, Any] | None:
    job = load_job(event_dir, job_id)
    if not job:
        return None
    if status is not None:
        job["status"] = status
    if phase is not None:
        job["phase"] = phase
    if message is not None:
        job["message"] = message
    job.update(extra)
    save_job(event_dir, job)
    return job


def finalize_job(
    event_dir: str | Path,
    job_id: str,
    status: str,
    *,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    job = load_job(event_dir, job_id)
    if not job:
        return None
    job["status"] = status
    job["phase"] = status
    if error:
        job["error"] = error
    if result:
        job["result"] = result
    if status == "done":
        job["message"] = "Bake complete"
    elif status == "interrupted":
        job["message"] = error or "Bake interrupted"
    elif status == "failed":
        job["message"] = error or "Bake failed"
    save_job(event_dir, job)
    return job


def find_active_job_for_stitch_job(
    event_dir: str | Path,
    stitch_job_name: str,
) -> dict[str, Any] | None:
    active = [
        j
        for j in list_jobs(event_dir)
        if j.get("stitch_job_name") == stitch_job_name
        and j.get("status") not in TERMINAL_BAKE_STATUSES
    ]
    if not active:
        return None
    return max(active, key=lambda j: j.get("updated_at") or j.get("started_at") or "")


def reconcile_stale_running_jobs(
    event_dir: str | Path,
    lock_path: Path,
) -> list[str]:
    """Mark running bake jobs interrupted when the flock lock is free (worker died)."""
    if not bake_lock_is_free(lock_path):
        return []
    interrupted: list[str] = []
    for job in list_jobs(event_dir):
        if job.get("status") not in ("running", "queued"):
            continue
        finalize_job(
            event_dir,
            job["job_id"],
            "interrupted",
            error="Bake interrupted — server restart or worker lost",
        )
        interrupted.append(job["job_id"])
    return interrupted


def job_poll_payload(job: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "phase": job.get("phase"),
        "message": job.get("message"),
        "stitch_job_name": job.get("stitch_job_name"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
        "code": STITCH_BAKE_JOB_TRUTH_V1,
    }
    if job.get("status") in TERMINAL_BAKE_STATUSES:
        payload["result"] = job.get("result") or {}
    return payload


def active_bake_job_summary(
    event_dir: str | Path,
    stitch_job_name: str,
    *,
    lock_path: Path | None = None,
) -> dict[str, Any] | None:
    if lock_path is not None:
        reconcile_stale_running_jobs(event_dir, lock_path)
    active = find_active_job_for_stitch_job(event_dir, stitch_job_name)
    if active:
        return job_poll_payload(active)
    jobs = [j for j in list_jobs(event_dir) if j.get("stitch_job_name") == stitch_job_name]
    if not jobs:
        return None
    latest = jobs[-1]
    if latest.get("status") not in TERMINAL_BAKE_STATUSES:
        return job_poll_payload(latest)
    return {
        **job_poll_payload(latest),
        "latest_terminal": True,
    }
