"""BG_EXPORT_TO_STITCHER_ASYNC_V1 — durable on-disk Send-to-Stitcher export jobs."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib import fcntl_compat as fcntl

BG_EXPORT_TO_STITCHER_ASYNC_V1 = "BG_EXPORT_TO_STITCHER_ASYNC_V1"
TERMINAL_EXPORT_STATUSES = frozenset({"done", "failed", "interrupted"})


def export_jobs_dir(event_dir: str | Path) -> Path:
    p = Path(event_dir) / "bg_export_stitcher_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def export_lock_path(event_dir: str | Path) -> Path:
    p = export_jobs_dir(event_dir) / "export.lock"
    p.touch(exist_ok=True)
    return p


def _job_path(event_dir: str | Path, job_id: str) -> Path:
    return export_jobs_dir(event_dir) / f"{job_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return str(uuid.uuid4())[:12]


def _json_safe(obj: Any) -> Any:
    """Recursively coerce job payloads to JSON-serializable values."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def save_job(event_dir: str | Path, job: dict[str, Any]) -> None:
    job["updated_at"] = _utc_now()
    path = _job_path(event_dir, str(job["job_id"]))
    safe = _json_safe(job)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(safe, indent=2), encoding="utf-8")
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
    root = export_jobs_dir(event_dir)
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def export_lock_is_free(lock_path: Path) -> bool:
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


def export_job_store_roots(
    app_event_dir: str | Path,
    *,
    app_milestone_dir: str | Path | None = None,
) -> list[Path]:
    """Candidate on-disk roots for BG export jobs (event + milestone partitions)."""
    event_path = Path(app_event_dir)
    roots: list[Path] = []
    seen: set[str] = set()

    def add(root: Path) -> None:
        if not root.is_dir():
            return
        key = str(root.resolve())
        if key in seen:
            return
        seen.add(key)
        roots.append(root)

    if app_milestone_dir:
        add(Path(app_milestone_dir))
    add(event_path)
    milestones = event_path.parent / "Milestones"
    if milestones.is_dir():
        for mdir in sorted(milestones.iterdir()):
            if mdir.is_dir():
                add(mdir)
    return roots


def find_export_job(
    store_roots: list[Path],
    job_id: str,
) -> tuple[Path, dict[str, Any]] | None:
    for root in store_roots:
        job = load_job(root, job_id)
        if job:
            return root, job
    return None


def create_job(
    event_dir: str | Path,
    *,
    job_id: str,
    scope_key: str,
    scope_event_id: str,
    arc_number: int,
    bg_event_id: str,
    phase: str,
    slot_key: str,
    beat_ids: list[str],
    pin: dict[str, Any],
) -> dict[str, Any]:
    now = _utc_now()
    store_root = Path(event_dir)
    job = {
        "job_id": job_id,
        "job_store_dir": str(store_root.resolve()),
        "status": "queued",
        "phase": "queued",
        "message": "Export queued",
        "scope_key": scope_key,
        "scope_event_id": scope_event_id,
        "arc_number": arc_number,
        "bg_event_id": bg_event_id,
        "segment_phase": phase,
        "slot_key": slot_key,
        "beat_ids": list(beat_ids),
        "beat_total": len(beat_ids),
        "beat_index": 0,
        "pin": {
            "pinned_generation": pin.get("pinned_generation"),
            "pinned_event_dir": pin.get("pinned_event_dir"),
            "pinned_video_role": pin.get("pinned_video_role"),
        },
        "started_at": now,
        "updated_at": now,
        "code": BG_EXPORT_TO_STITCHER_ASYNC_V1,
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
    beat_index: int | None = None,
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
    if beat_index is not None:
        job["beat_index"] = beat_index
    job.update(extra)
    save_job(event_dir, job)
    return job


def finalize_job(
    event_dir: str | Path,
    job_id: str,
    status: str,
    *,
    error: str | None = None,
    error_code: str | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    job = load_job(event_dir, job_id)
    if not job:
        return None
    job["status"] = status
    job["phase"] = status
    if error:
        job["error"] = error
    if error_code:
        job["error_code"] = error_code
    if result:
        job["result"] = result
    if status == "done":
        job["message"] = "Sent to Stitcher"
    elif status == "interrupted":
        job["message"] = error or "Export interrupted"
    elif status == "failed":
        job["message"] = error or "Export failed"
    save_job(event_dir, job)
    return job


def find_active_job_for_scope_key(
    event_dir: str | Path,
    scope_key: str,
) -> dict[str, Any] | None:
    active = [
        j
        for j in list_jobs(event_dir)
        if j.get("scope_key") == scope_key
        and j.get("status") not in TERMINAL_EXPORT_STATUSES
    ]
    if not active:
        return None
    return max(active, key=lambda j: j.get("updated_at") or j.get("started_at") or "")


def reconcile_stale_running_jobs(
    event_dir: str | Path,
    lock_path: Path,
) -> list[str]:
    if not export_lock_is_free(lock_path):
        return []
    interrupted: list[str] = []
    for job in list_jobs(event_dir):
        if job.get("status") not in ("running", "queued"):
            continue
        finalize_job(
            event_dir,
            str(job["job_id"]),
            "interrupted",
            error="Export interrupted — server restart or worker lost",
            error_code="EXPORT_INTERRUPTED",
        )
        interrupted.append(str(job["job_id"]))
    return interrupted


def job_poll_payload(job: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "phase": job.get("phase"),
        "message": job.get("message"),
        "scope_key": job.get("scope_key"),
        "slot_key": job.get("slot_key"),
        "beat_index": job.get("beat_index", 0),
        "beat_total": job.get("beat_total", 0),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
        "error_code": job.get("error_code"),
        "code": BG_EXPORT_TO_STITCHER_ASYNC_V1,
    }
    if job.get("status") in TERMINAL_EXPORT_STATUSES:
        result = dict(job.get("result") or {})
        if job.get("error_code") and "error_code" not in result:
            result["error_code"] = job.get("error_code")
        payload["result"] = result
    return payload
