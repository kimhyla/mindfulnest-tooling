"""O3 recovery seal — master-or-orphan-before-failed terminal contract.

TECH_SPEC_O3_LIFECYCLE_SEAL_v1 F1 + F5: when Kling master or delivery exists on disk,
do not terminalize bare ``failed`` without attempting recovery first.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def seal_o3_recovery_before_terminal(
    beat_id: str,
    event_dir: str | Path,
    *,
    master_path: Path | str | None = None,
    delivery_path: Path | str | None = None,
    log_path: Path | str | None = None,
    failure_phase: str | None = None,
    failure_message: str | None = None,
    make_active: bool = True,
) -> dict[str, Any]:
    """Resolve on-disk artifacts before writing a closed terminal."""
    import beat_generator as bg

    event_dir = Path(event_dir)
    beat_id = str(beat_id or "").strip()
    result: dict[str, Any] = {
        "terminal_status": "failed",
        "recovered": False,
        "delivery_path": None,
        "master_path": None,
        "sidecar_persist_ok": False,
        "warning": None,
    }

    delivery_candidates: list[Path] = []
    for raw in (delivery_path,):
        if raw:
            p = Path(raw)
            if p.is_file():
                delivery_candidates.append(p.resolve())
    if log_path:
        from beat_generator import _delivery_path_from_o3_job_log

        logged = _delivery_path_from_o3_job_log(str(log_path))
        if logged and Path(logged).is_file():
            delivery_candidates.append(Path(logged).resolve())
    for path in bg.list_o3_element_delivery_paths_on_disk(beat_id, event_dir):
        delivery_candidates.append(path.resolve())

    seen: set[str] = set()
    delivery_file: Path | None = None
    for p in delivery_candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file() and p.stat().st_size > 100_000:
            delivery_file = p
            break

    if delivery_file is not None and delivery_file.is_file():
        try:
            recovered = bg.recover_orphan_o3_delivery(
                beat_id,
                event_dir,
                str(log_path) if log_path else None,
                delivery_path=str(delivery_file),
                make_active=make_active,
            )
            if recovered:
                result.update({
                    "terminal_status": "done",
                    "recovered": True,
                    "delivery_path": str(delivery_file),
                    "sidecar_persist_ok": True,
                })
                return result
        except Exception as exc:
            result["warning"] = {"code": "ORPHAN_RECOVERY_FAILED", "message": str(exc)[:500]}

    master_file: Path | None = None
    if master_path:
        mp = Path(master_path)
        if mp.is_file():
            master_file = mp.resolve()
    if master_file is None:
        for path in event_dir.glob(f"kling_o3_clips/{beat_id}*_element_o3_master.mp4"):
            if path.is_file():
                master_file = path.resolve()
                break

    if master_file is not None and master_file.is_file():
        result.update({
            "terminal_status": "done_with_warning",
            "master_path": str(master_file),
            "warning": {
                "code": "DELIVERY_ENCODE_PENDING",
                "message": (failure_message or "Delivery encode failed; master on disk")[:500],
                "phase": failure_phase,
            },
        })
        return result

    if failure_message:
        result["warning"] = {"code": "TRUE_FAILURE", "message": failure_message[:500]}
    return result
