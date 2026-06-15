"""Durable on-disk store for Beat Gen Kling O3 batch jobs (survives refresh + server restart)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beat_generator import kling_o3_clips_dir


def kling_o3_jobs_dir(event_dir: str | Path) -> Path:
    p = kling_o3_clips_dir(event_dir) / "_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _job_path(event_dir: str | Path, job_id: str) -> Path:
    return kling_o3_jobs_dir(event_dir) / f"{job_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return str(uuid.uuid4())[:8]


def create_job(
    event_dir: str | Path,
    *,
    job_id: str,
    beat_entries: dict[str, dict[str, Any]],
    context: dict[str, Any],
    scope_event_id: str,
) -> dict[str, Any]:
    """Persist a new running job before worker threads start."""
    now = _utc_now()
    job = {
        "job_id": job_id,
        "status": "running",
        "scope_event_id": scope_event_id,
        "context": dict(context),
        "started_at": now,
        "updated_at": now,
        "total": len(beat_entries),
        "done_count": 0,
        "failed_count": 0,
        "beats": beat_entries,
        "results": {},
    }
    save_job(event_dir, job)
    return job


def save_job(event_dir: str | Path, job: dict[str, Any]) -> None:
    job["updated_at"] = _utc_now()
    path = _job_path(event_dir, job["job_id"])
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(job, indent=2))
    os.replace(tmp, path)


def load_job(event_dir: str | Path, job_id: str) -> dict[str, Any] | None:
    path = _job_path(event_dir, job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def list_jobs(event_dir: str | Path) -> list[dict[str, Any]]:
    root = kling_o3_jobs_dir(event_dir)
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            out.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def list_active_jobs(event_dir: str | Path) -> list[dict[str, Any]]:
    return [j for j in list_jobs(event_dir) if j.get("status") == "running"]


def update_job_beat(
    event_dir: str | Path,
    job_id: str,
    beat_id: str,
    **patch: Any,
) -> dict[str, Any] | None:
    job = load_job(event_dir, job_id)
    if not job:
        return None
    beat = (job.get("beats") or {}).get(beat_id)
    if not beat:
        return job
    beat.update(patch)
    save_job(event_dir, job)
    return job


def record_job_result(
    event_dir: str | Path,
    job_id: str,
    beat_id: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    job = load_job(event_dir, job_id)
    if not job:
        return None
    results = job.setdefault("results", {})
    is_new = beat_id not in results
    results[beat_id] = result
    beat = (job.get("beats") or {}).get(beat_id)
    if beat:
        beat["status"] = "completed" if result.get("ok") else "failed"
        if result.get("task_id"):
            beat["task_id"] = result.get("task_id")
        if result.get("error"):
            beat["error"] = result.get("error")
    if is_new:
        if result.get("ok"):
            job["done_count"] = int(job.get("done_count") or 0) + 1
        else:
            job["failed_count"] = int(job.get("failed_count") or 0) + 1
    save_job(event_dir, job)
    return job


def finalize_job(event_dir: str | Path, job_id: str, status: str = "done", *, error: str | None = None) -> None:
    job = load_job(event_dir, job_id)
    if not job:
        return
    job["status"] = status
    if error:
        job["error"] = error
    save_job(event_dir, job)


def job_to_memory(job: dict[str, Any]) -> dict[str, Any]:
    """Shape stored job for in-memory _KLING_O3_JOBS poll cache."""
    return {
        "status": job.get("status") or "running",
        "results": dict(job.get("results") or {}),
        "total": int(job.get("total") or 0),
        "done_count": int(job.get("done_count") or 0),
        "failed_count": int(job.get("failed_count") or 0),
        "error": job.get("error"),
    }


def job_poll_payload(job: dict[str, Any]) -> dict[str, Any]:
    mem = job_to_memory(job)
    return {
        "status": mem["status"],
        "results": mem["results"],
        "total": mem["total"],
        "done_count": mem["done_count"],
        "failed_count": mem["failed_count"],
        "error": mem.get("error"),
    }


def active_jobs_summary(event_dir: str | Path) -> list[dict[str, Any]]:
    """Lightweight list for client re-attach after refresh."""
    summaries: list[dict[str, Any]] = []
    for job in list_active_jobs(event_dir):
        beat_ids = [
            bid for bid, meta in (job.get("beats") or {}).items()
            if (meta.get("status") or "queued") in ("queued", "processing", "submitted")
        ]
        if not beat_ids and job.get("status") == "running":
            beat_ids = list((job.get("beats") or {}).keys())
        summaries.append({
            "job_id": job.get("job_id"),
            "beat_ids": beat_ids,
            "status": job.get("status"),
            "total": job.get("total"),
            "done_count": job.get("done_count"),
            "failed_count": job.get("failed_count"),
        })
    return summaries
