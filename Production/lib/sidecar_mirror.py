"""Debounced Dropbox mirror export for Beat Gen SQLite authority."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_export_lock = threading.Lock()
_timer: threading.Timer | None = None
_pending_path: str | None = None
_last_export_at: float | None = None
_last_export_error: str | None = None


def mirror_debounce_s() -> float:
    raw = os.environ.get("MN_SIDECAR_MIRROR_DEBOUNCE_S", "10")
    try:
        return max(0.5, float(raw))
    except ValueError:
        return 10.0


def last_mirror_export_monotonic() -> float | None:
    return _last_export_at


def last_mirror_export_error() -> str | None:
    return _last_export_error


def schedule_mirror_export(
    mirror_path: str | Path,
    *,
    assemble: Callable[[], dict],
    write_atomic: Callable[[dict], None],
) -> None:
    """Coalesce mirror writes — SQLite commit already durable."""
    global _timer, _pending_path
    path = str(Path(mirror_path).resolve())
    with _export_lock:
        _pending_path = path
        _state = {"assemble": assemble, "write_atomic": write_atomic}

        def _fire() -> None:
            flush_mirror_export(**_state)

        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(mirror_debounce_s(), _fire)
        _timer.daemon = True
        _timer.start()


def flush_mirror_export(
    *,
    assemble: Callable[[], dict] | None = None,
    write_atomic: Callable[[dict], None] | None = None,
    mirror_path: str | Path | None = None,
) -> bool:
    """Immediate mirror write (shutdown / deploy smoke)."""
    global _last_export_at, _last_export_error, _timer, _pending_path
    from lib.beatgen_store import BeatgenStore, sqlite_authority_enabled

    if not sqlite_authority_enabled():
        return False
    path = str(Path(mirror_path or _pending_path or "").resolve()) if (mirror_path or _pending_path) else ""
    with _export_lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        try:
            data = (assemble or BeatgenStore.get().assemble_sidecar_dict)()
            writer = write_atomic
            if writer is None:
                import beat_generator as bg  # type: ignore

                def writer(d: dict) -> None:
                    bg._write_sidecar_json_mirror(d, path)

            if not path:
                return False
            writer(data)
            _last_export_at = time.monotonic()
            _last_export_error = None
            return True
        except Exception as exc:
            _last_export_error = str(exc)
            print(f"[sidecar_mirror] export failed: {exc}", flush=True)
            return False


def mirror_status() -> dict:
    return {
        "debounce_s": mirror_debounce_s(),
        "last_export_monotonic": _last_export_at,
        "last_error": _last_export_error,
        "pending_path": _pending_path,
    }
