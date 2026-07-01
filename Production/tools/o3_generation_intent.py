"""O3 Generation Intent Snapshot — immutable submit contract at Generate click."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INTENT_SCHEMA_VERSION = 1
TERMINAL_SCHEMA_VERSION = 1

INTENT_TERMINAL_STATUSES = frozenset({"done", "failed", "done_with_warning", "cancelled"})
INTENT_RUNNING_STATUS = "running"
O3_HEARTBEAT_STALE_S = 90
O3_SPAWN_IN_FLIGHT_S = 15
O3_JOB_LOST_FAILURE_MESSAGE = (
    "O3 job ended without terminal record (subprocess lost or server restart)."
)
_O3_PIPELINE_PROCESS_MARKERS = (
    "kling_o3_element_beat_pipeline",
    "arlo_o3_voice_pipeline",
    "arlo_avatar_beat_pipeline",
    "o3_voice_pipeline",
)

OPERATOR_MUTABLE_FIELDS = frozenset({
    "kling_o3_prompt",
    "reference_image",
    "bg_ref_image",
    "speaker",
})


class IntentActiveError(RuntimeError):
    """Raised when canonical mutation is blocked during active intent."""


class IntentCommitError(Exception):
    def __init__(
        self,
        error_code: str,
        error_message: str,
        *,
        http_status: int = 400,
        detail: dict | None = None,
        retry_safe: bool = False,
    ) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.http_status = http_status
        self.detail = detail or {}
        self.retry_safe = retry_safe


def _jobs_dir(event_dir: Path) -> Path:
    return event_dir / "arlo_o3_jobs"


def _ref_abs_path(ref: Any) -> str:
    if not isinstance(ref, dict):
        return ""
    return str(ref.get("abs_path") or "").strip()


def resolve_o3_submit_ref(field: str, *, body: dict, beat: dict) -> dict | None:
    """Operator ref box wins on Generate; sidecar only when POST omits the field."""
    sidecar_ref = beat.get(field)
    if field in body:
        body_ref = body.get(field)
        if body_ref is None:
            return None
        if isinstance(body_ref, dict):
            body_path = _ref_abs_path(body_ref)
            sidecar_path = _ref_abs_path(sidecar_ref) if isinstance(sidecar_ref, dict) else ""
            if body_path and sidecar_path and body_path != sidecar_path:
                print(
                    f"[o3_intent] {field} ref box wins over sidecar "
                    f"({Path(body_path).name} not {Path(sidecar_path).name})",
                    flush=True,
                )
            if isinstance(sidecar_ref, dict) and _ref_abs_path(sidecar_ref) == body_path:
                merged = dict(sidecar_ref)
                merged.update({k: v for k, v in body_ref.items() if v not in (None, "")})
                return merged
            return dict(body_ref)
    if isinstance(sidecar_ref, dict):
        return dict(sidecar_ref)
    return None


def resolve_o3_submit_refs(body: dict, beat: dict) -> tuple[dict | None, dict | None]:
    """Resolve char + BG refs for O3 intent commit (ref box over sidecar)."""
    char_ref = resolve_o3_submit_ref("reference_image", body=body, beat=beat)
    bg_ref = resolve_o3_submit_ref("bg_ref_image", body=body, beat=beat)
    if char_ref is None and isinstance(beat.get("reference_image"), dict):
        char_ref = dict(beat["reference_image"])
    if bg_ref is None and isinstance(beat.get("bg_ref_image"), dict):
        bg_ref = dict(beat["bg_ref_image"])
    return char_ref, bg_ref


def intent_path_for_job(job_id: str, event_dir: Path) -> Path:
    return _jobs_dir(event_dir) / f"{job_id}_intent.json"


def terminal_path_for_job(job_id: str, event_dir: Path) -> Path:
    return _jobs_dir(event_dir) / f"{job_id}_terminal.json"


def pid_path_for_job(job_id: str, event_dir: Path) -> Path:
    return _jobs_dir(event_dir) / f"{job_id}.pid"


def heartbeat_path_for_job(job_id: str, event_dir: Path) -> Path:
    return _jobs_dir(event_dir) / f"{job_id}.heartbeat"


def write_o3_job_pid(job_id: str, event_dir: Path, pid: int) -> Path:
    jobs_dir = _jobs_dir(event_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = pid_path_for_job(job_id, event_dir)
    dest.write_text(str(int(pid)), encoding="utf-8")
    return dest


def touch_o3_job_heartbeat(job_id: str, event_dir: Path) -> Path:
    jobs_dir = _jobs_dir(event_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = heartbeat_path_for_job(job_id, event_dir)
    dest.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    return dest


def write_running_terminal_at_submit(
    job_id: str,
    event_dir: Path,
    *,
    intent_id: str | None = None,
    beat_id: str | None = None,
) -> Path:
    return write_intent_terminal(job_id, event_dir, {
        "intent_id": intent_id,
        "beat_id": beat_id,
        "status": INTENT_RUNNING_STATUS,
        "phase_last": "submit",
    })


def _sha256_file(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def load_generation_intent(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schema_version") or 0) != INTENT_SCHEMA_VERSION:
        raise ValueError(f"unsupported intent schema: {path}")
    return data


def load_intent_terminal(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_generation_intent(intent: dict, event_dir: Path) -> Path:
    job_id = str(intent.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("intent.job_id required")
    jobs_dir = _jobs_dir(event_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = intent_path_for_job(job_id, event_dir)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(intent, indent=2), encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def write_intent_terminal(job_id: str, event_dir: Path, payload: dict) -> Path:
    jobs_dir = _jobs_dir(event_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    dest = terminal_path_for_job(job_id, event_dir)
    body = {
        "schema_version": TERMINAL_SCHEMA_VERSION,
        "job_id": job_id,
        **payload,
    }
    if "terminal_at" not in body:
        body["terminal_at"] = datetime.now(timezone.utc).isoformat()
    tmp = dest.parent / f".{dest.name}.{os.getpid()}.tmp"
    try:
        tmp.write_text(json.dumps(body, indent=2), encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def terminal_status_for_job(job_id: str, event_dir: Path) -> str | None:
    terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
    if not terminal:
        return None
    return str(terminal.get("status") or "").strip() or None


def intent_event_dir_for_beat(beat_id: str, event_dir: Path | None = None) -> Path:
    """Return ``Event_N`` for intent I/O — ``beat_id`` event number beats server scope."""
    import beat_generator as bg
    from beatgen_scope import event_id_from_beat_id  # noqa: PLC0415

    scoped = Path(event_dir).expanduser().resolve() if event_dir is not None else None
    production_event = event_id_from_beat_id(beat_id)
    if scoped is not None and scoped.is_dir():
        if production_event and scoped.name == production_event:
            return scoped
        if not production_event:
            return scoped
    if production_event:
        return Path(bg._PROD_DIR) / production_event
    if scoped is not None and scoped.is_dir():
        return scoped
    return bg.event_dir_for_beat_id(beat_id)


def resolve_o3_job_event_dir(
    beat_id: str,
    *,
    server_event_dir: Path | None = None,
    library_event_dir: Path | None = None,
    scope_type: str = "event",
) -> Path:
    """Canonical Event folder for O3 job lifecycle (intent, terminal, pid).

    Milestone narrative ids (``event3b``) do not map to ``Production/Event_3b``;
    milestone scope uses ``library_event_dir``, else the pinned server event dir.
    """
    lib = Path(library_event_dir).expanduser().resolve() if library_event_dir else None
    server = Path(server_event_dir).expanduser().resolve() if server_event_dir else None
    if str(scope_type or "").strip().lower() == "milestone" and lib and lib.is_dir():
        return intent_event_dir_for_beat(beat_id, lib)
    if server and server.is_dir():
        return intent_event_dir_for_beat(beat_id, server)
    return intent_event_dir_for_beat(beat_id, None)


def resolve_o3_job_event_dir_candidates(
    beat_id: str,
    *,
    server_event_dir: Path | None = None,
    library_event_dir: Path | None = None,
    scope_type: str = "event",
) -> list[Path]:
    """Ordered Event dirs to consult for job terminals (primary + migration fallback)."""
    primary = resolve_o3_job_event_dir(
        beat_id,
        server_event_dir=server_event_dir,
        library_event_dir=library_event_dir,
        scope_type=scope_type,
    )
    seen: set[Path] = {primary.resolve()}
    out: list[Path] = [primary]
    for raw in (server_event_dir, library_event_dir):
        if raw is None:
            continue
        p = Path(raw).expanduser().resolve()
        if not p.is_dir() or p in seen:
            continue
        alt = intent_event_dir_for_beat(beat_id, p).resolve()
        if alt not in seen:
            seen.add(alt)
            out.append(intent_event_dir_for_beat(beat_id, p))
    return out


def discover_event_dirs(prod_root: Path) -> list[Path]:
    """All ``Event_*`` directories under Production (multi-event sidecar reconcile)."""
    root = Path(prod_root)
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.glob("Event_*") if p.is_dir()),
        key=lambda p: p.name,
    )


def _last_json_blob(log_text: str) -> dict | None:
    """Parse the last JSON object in a subprocess log (supports pretty-printed blocks)."""
    text = (log_text or "").rstrip()
    if not text:
        return None
    start = text.rfind("\n{")
    if start >= 0:
        start += 1
    else:
        start = text.find("{")
    if start < 0:
        return None
    try:
        parsed = json.loads(text[start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _pipeline_done_from_log(log_path: Path) -> dict | None:
    """Parse terminal success from element ``phase: done`` or voice-first ``ok: true`` JSON."""
    if not log_path.is_file():
        return None
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    last = _last_json_blob(log_text)
    if last and last.get("ok") is True:
        video = str(last.get("video") or last.get("playback_video") or "")
        if video:
            return last
    for line in reversed(log_text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if parsed.get("phase") == "done" and parsed.get("video"):
            return parsed
        if parsed.get("phase") == "finalize" and parsed.get("video"):
            return parsed
    return None


def _clear_beat_intent_lock_fields(beat: dict) -> None:
    beat.pop("o3_active_intent_id", None)
    beat.pop("o3_active_intent_job_id", None)


def heal_o3_beat_after_aborted_attempt(beat: dict, event_dir: str | Path | None = None) -> bool:
    """Restore approved-clip state after cancelled/failed redo that never replaced delivery."""
    from pathlib import Path

    import beat_generator as bg

    beat_id = str(beat.get("beat_id") or "").strip()
    if event_dir is None:
        event_dir = bg.event_dir_for_beat_id(beat_id) if beat_id else None
    from o3_job_status_contract import beat_o3_operator_busy

    if beat_o3_operator_busy(beat, event_dir):
        return False
    if restore_last_good_o3_delivery_after_failed_attempt(beat, event_dir):
        return True
    kling_status = str(beat.get("kling_o3_status") or "")
    video = str(beat.get("kling_o3_video_path") or "")
    if kling_status not in ("approved", "submitted", "completed") or not video or not Path(video).is_file():
        return False
    beat["status"] = "approved"
    beat["kling_o3_status"] = "approved"
    beat["kling_o3_voice_fix_status"] = "approved"
    beat.pop("kling_o3_voice_fix_error", None)
    beat.pop("kling_o3_voice_fix_error_code", None)
    beat.pop("kling_o3_task_id", None)
    beat.pop("kling_o3_submit_response", None)
    beat.pop("kling_o3_voice_fix_job_log_path", None)
    beat.pop("kling_o3_voice_fix_job_pid", None)
    beat.pop("kling_o3_voice_fix_job_started_at", None)
    beat.pop("kling_o3_voice_fix_attempt_id", None)
    beat.pop("kling_o3_voice_fix_phase", None)
    return True


def restore_last_good_o3_delivery_after_failed_attempt(
    beat: dict,
    event_dir: str | Path | None,
    *,
    failed_generation: int | None = None,
) -> bool:
    """O3_FAILED_REDO_HEAL_V1 — revert to last on-disk delivery when attempt N failed.

    After failed regen (g4+), if delivery for N is missing but g{N-1} (or any prior)
    exists on disk, promote the highest surviving generation to active approved state.
    """
    from pathlib import Path

    import beat_generator as bg

    beat_id = str(beat.get("beat_id") or "").strip()
    if not beat_id or event_dir is None:
        return False
    event_dir = Path(event_dir)
    from o3_job_status_contract import beat_o3_operator_busy

    if beat_o3_operator_busy(beat, event_dir, in_memory_jobs=None):
        return False

    bg.reconcile_o3_disk_deliveries_for_beat(beat, event_dir)

    if failed_generation is None:
        failed_generation = int(beat.get("kling_o3_generation") or 0) or None

    candidates: list[tuple[int, str]] = []
    for opt in beat.get("kling_o3_options") or []:
        if not isinstance(opt, dict):
            continue
        path = str(opt.get("video_path") or "").strip()
        if not path or not Path(path).is_file():
            continue
        gen = opt.get("generation")
        if gen is None:
            gen = bg._kling_o3_gen_from_video_path(path)
        gen_i = int(gen) if gen is not None else 0
        if failed_generation is not None and gen_i >= failed_generation:
            continue
        candidates.append((gen_i, path))

    if not candidates:
        for path in bg.list_o3_element_delivery_paths_on_disk(beat_id, event_dir):
            gen_i = bg._kling_o3_gen_from_video_path(str(path)) or 0
            if failed_generation is not None and gen_i >= failed_generation:
                continue
            candidates.append((gen_i, str(path.resolve())))

    if not candidates:
        return False

    gen_i, best_path = max(candidates, key=lambda row: row[0])
    from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

    if not align_beat_active_delivery_clip(
        beat,
        best_path,
        mark_voice_fix_approved=True,
        clear_voice_fix_error=True,
    ):
        return False

    beat["kling_o3_generation"] = gen_i
    beat["status"] = "approved"
    beat["kling_o3_status"] = "approved"
    for key in (
        "kling_o3_voice_fix_job_log_path",
        "kling_o3_voice_fix_job_pid",
        "kling_o3_voice_fix_job_started_at",
        "kling_o3_voice_fix_attempt_id",
        "kling_o3_voice_fix_phase",
        "kling_o3_task_id",
        "kling_o3_submit_response",
        "o3_current_job_id",
        "o3_active_intent_job_id",
    ):
        beat.pop(key, None)
    bg.refresh_o3_ui_slot_layout(beat)
    return True


def _heal_o3_beat_after_aborted_attempt(beat: dict, terminal: dict | None = None) -> bool:
    return heal_o3_beat_after_aborted_attempt(beat)


_JOB_ID_FROM_LOG_RE = re.compile(r"/([0-9a-f]{8})_[^/]+\.log", re.I)
_ACTIVE_PIPELINE_LOG_PHASES = frozenset({
    "o3_submit", "o3_poll", "o3_element", "o3_element_native_voice",
    "tts", "tts_submit", "tts_ready", "visual_running", "lipsync_submit",
    "lipsync_poll", "lipsync_running", "subprocess", "job_starting",
    "o3_running", "job_running", "queued", "finalize",
})
_TERMINAL_PIPELINE_LOG_PHASES = frozenset({"done", "failed", "error"})


def job_id_from_beat(beat: dict | None) -> str:
    """UI poll id or ``{job_id}_`` prefix from ``kling_o3_voice_fix_job_log_path``."""
    if not beat:
        return ""
    ui = str(beat.get("kling_o3_voice_fix_ui_job_id") or "").strip()
    if ui:
        return ui
    log_path = str(beat.get("kling_o3_voice_fix_job_log_path") or "")
    match = _JOB_ID_FROM_LOG_RE.search(log_path)
    return match.group(1) if match else ""


def _pid_is_running(pid_value) -> bool:
    try:
        pid = int(pid_value or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def subprocess_running_for_o3_job(job_id: str, beat_id: str) -> bool:
    """True when an O3 pipeline subprocess is still running for this job/beat."""
    job_id = str(job_id or "").strip()
    beat_id = str(beat_id or "").strip()
    if not job_id or not beat_id:
        return False
    try:
        import subprocess

        out = subprocess.check_output(
            ["pgrep", "-fl", "python"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return False
    needle_job = f"/{job_id}_"
    for line in out.splitlines():
        if beat_id not in line:
            continue
        if not any(marker in line for marker in _O3_PIPELINE_PROCESS_MARKERS):
            continue
        if needle_job in line or f" {job_id}_" in line or f"job_id={job_id}" in line:
            return True
    return False


def resolve_o3_job_log_path(job_id: str, beat_id: str, event_dir: Path, intent: dict | None = None) -> Path | None:
    """Best-effort log path for an O3 attempt (intent runtime, then jobs dir naming)."""
    job_id = str(job_id or "").strip()
    beat_id = str(beat_id or "").strip()
    if not job_id or not beat_id:
        return None
    if intent is None:
        intent_path = intent_path_for_job(job_id, event_dir)
        if intent_path.is_file():
            try:
                intent = load_generation_intent(intent_path)
            except (OSError, json.JSONDecodeError, ValueError):
                intent = None
    runtime = (intent or {}).get("runtime") or {}
    log_path = Path(str(runtime.get("log_path") or ""))
    jobs_dir = _jobs_dir(event_dir)
    if not log_path.is_file():
        alt = jobs_dir / f"{job_id}_{beat_id}.log"
        if alt.is_file():
            log_path = alt
    return log_path if log_path.is_file() else None


def o3_subprocess_is_live(
    job_id: str,
    beat_id: str,
    event_dir: Path,
    *,
    in_memory_jobs: dict | None = None,
) -> bool:
    """True when PID file, heartbeat, in-memory job, or pgrep proves subprocess is alive."""
    from o3_job_status_contract import _in_memory_o3_job_running

    job_id = str(job_id or "").strip()
    beat_id = str(beat_id or "").strip()
    if not job_id or not beat_id:
        return False
    if _in_memory_o3_job_running(job_id, beat_id, in_memory_jobs):
        return True
    pid_path = pid_path_for_job(job_id, event_dir)
    if pid_path.is_file():
        try:
            if _pid_is_running(int(pid_path.read_text(encoding="utf-8").strip())):
                return True
        except (TypeError, ValueError, OSError):
            pass
    hb_path = heartbeat_path_for_job(job_id, event_dir)
    if hb_path.is_file():
        import time

        age_s = max(0.0, time.time() - hb_path.stat().st_mtime)
        if age_s <= O3_HEARTBEAT_STALE_S:
            return True
    return subprocess_running_for_o3_job(job_id, beat_id)


def o3_job_attempt_is_live(
    job_id: str,
    beat_id: str,
    event_dir: Path,
    *,
    in_memory_jobs: dict | None = None,
    log_path: Path | None = None,
    intent: dict | None = None,
    log_grace_s: float | None = None,
    submit_grace_s: float | None = None,
) -> bool:
    """Backward-compatible alias — v2 liveness is PID/heartbeat only."""
    del log_path, intent, log_grace_s, submit_grace_s
    return o3_subprocess_is_live(
        job_id, beat_id, event_dir, in_memory_jobs=in_memory_jobs,
    )


def close_o3_attempt(
    job_id: str,
    beat_id: str,
    event_dir: Path,
    terminal_status: str,
    *,
    reason: str | None = None,
    phase_last: str = "o3_close",
    intent: dict | None = None,
    persist_beat: bool = True,
) -> dict:
    """Single closer — write closed terminal and persist sidecar heal."""
    from o3_job_status_contract import clear_o3_job_cache_fields, resolve_o3_current_job_id

    job_id = str(job_id or "").strip()
    beat_id = str(beat_id or "").strip()
    terminal_status = str(terminal_status or "").strip()
    if terminal_status not in INTENT_TERMINAL_STATUSES:
        raise ValueError(f"close_o3_attempt requires closed terminal status, got {terminal_status!r}")
    if intent is None:
        intent_path = intent_path_for_job(job_id, event_dir)
        if intent_path.is_file():
            try:
                intent = load_generation_intent(intent_path)
            except (OSError, json.JSONDecodeError, ValueError):
                intent = {}
    terminal_path = terminal_path_for_job(job_id, event_dir)
    existing = load_intent_terminal(terminal_path)
    if existing and str(existing.get("status") or "").strip() in INTENT_TERMINAL_STATUSES:
        return existing
    msg = reason or (
        O3_JOB_LOST_FAILURE_MESSAGE if terminal_status == "failed" else ""
    )
    terminal: dict = {
        "schema_version": TERMINAL_SCHEMA_VERSION,
        "job_id": job_id,
        "intent_id": (intent or {}).get("intent_id"),
        "beat_id": beat_id,
        "status": terminal_status,
        "phase_last": phase_last,
        "sidecar_persist_ok": bool(persist_beat),
        "terminal_at": datetime.now(timezone.utc).isoformat(),
    }
    if terminal_status == "failed":
        terminal["failure"] = {"message": msg or O3_JOB_LOST_FAILURE_MESSAGE}
    elif terminal_status == "cancelled":
        terminal["failure"] = {"message": msg or "O3 job cancelled"}
    write_intent_terminal(job_id, event_dir, terminal)
    for aux in (pid_path_for_job(job_id, event_dir), heartbeat_path_for_job(job_id, event_dir)):
        aux.unlink(missing_ok=True)

    def _heal_beat(beat: dict, _sidecar: dict) -> None:
        if str(beat.get("beat_id") or "").strip() != beat_id:
            return
        if resolve_o3_current_job_id(beat) not in ("", job_id):
            return
        clear_o3_job_cache_fields(beat)
        intent_gen = None
        intent_dict = intent if isinstance(intent, dict) else {}
        slot = intent_dict.get("generation_slot") or intent_dict.get("generation")
        if slot and str(slot).startswith("g"):
            try:
                intent_gen = int(str(slot)[1:])
            except ValueError:
                intent_gen = None
        if terminal_status == "failed":
            restore_last_good_o3_delivery_after_failed_attempt(
                beat,
                event_dir,
                failed_generation=intent_gen,
            )
            beat["kling_o3_voice_fix_error"] = msg or O3_JOB_LOST_FAILURE_MESSAGE
        heal_o3_beat_after_aborted_attempt(beat, event_dir)
        if str(beat.get("status") or "").startswith(("o3_voice_job_", "o3_element_")):
            if str(beat.get("kling_o3_status") or "") == "approved":
                beat["status"] = "approved"

    if persist_beat:
        import beat_generator as bg

        bg.update_beat_locked(beat_id, _heal_beat)
    return terminal


def finalize_o3_job_lost_attempt(
    job_id: str,
    beat_id: str,
    event_dir: Path,
    *,
    intent: dict | None = None,
    phase_last: str = "o3_liveness_lost",
    persist_beat: bool = False,
) -> dict:
    """Stamp failed terminal for a dead attempt — delegates to close_o3_attempt."""
    return close_o3_attempt(
        job_id,
        beat_id,
        event_dir,
        "failed",
        reason=O3_JOB_LOST_FAILURE_MESSAGE,
        phase_last=phase_last,
        intent=intent,
        persist_beat=persist_beat,
    )


def observe_and_close_stale_o3_attempt(
    job_id: str,
    beat_id: str,
    event_dir: Path,
    *,
    in_memory_jobs: dict | None = None,
    close_stale_running: bool = True,
) -> bool:
    """If terminal is running but subprocess is dead, close on disk (persist).

    When ``close_stale_running`` is False (session GET), this is read-only: no sidecar
    writes. ``beat_job_busy`` already treats terminal-done as not busy; pointer cleanup
    belongs in ``_apply_o3_session_terminal_reconcile`` / startup reconcile, not on
    every session-state GET (which would stampede milestone JSON flock / SQLite lock).
    """
    job_id = str(job_id or "").strip()
    beat_id = str(beat_id or "").strip()
    if not job_id or not beat_id:
        return False
    terminal = load_intent_terminal(terminal_path_for_job(job_id, event_dir))
    status = str((terminal or {}).get("status") or "").strip()
    if (
        close_stale_running
        and status == INTENT_RUNNING_STATUS
        and not o3_subprocess_is_live(
            job_id, beat_id, event_dir, in_memory_jobs=in_memory_jobs,
        )
    ):
        close_o3_attempt(
            job_id,
            beat_id,
            event_dir,
            "failed",
            reason=O3_JOB_LOST_FAILURE_MESSAGE,
            phase_last="observe_stale_running",
            persist_beat=True,
        )
        return True
    if close_stale_running and status in INTENT_TERMINAL_STATUSES:
        from o3_job_status_contract import resolve_o3_current_job_id

        import beat_generator as bg

        sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=5.0)
        _, beat = bg.find_beat(sidecar, beat_id)
        if beat and resolve_o3_current_job_id(beat) == job_id:

            def _clear_ptr(b: dict, _sc: dict) -> None:
                if str(b.get("beat_id") or "").strip() != beat_id:
                    return
                if resolve_o3_current_job_id(b) != job_id:
                    return
                from o3_job_status_contract import clear_o3_job_cache_fields

                clear_o3_job_cache_fields(b)
                if status == "failed":
                    fail = (terminal or {}).get("failure") or {}
                    b["kling_o3_voice_fix_error"] = str(
                        fail.get("message") or O3_JOB_LOST_FAILURE_MESSAGE,
                    )
                    intent_gen = None
                    intent_path = intent_path_for_job(job_id, event_dir)
                    if intent_path.is_file():
                        try:
                            intent_row = load_generation_intent(intent_path)
                            slot = intent_row.get("generation_slot") or intent_row.get("generation")
                            if slot and str(slot).startswith("g"):
                                intent_gen = int(str(slot)[1:])
                        except (OSError, json.JSONDecodeError, ValueError):
                            intent_gen = None
                    restore_last_good_o3_delivery_after_failed_attempt(
                        b,
                        event_dir,
                        failed_generation=intent_gen,
                    )
                    heal_o3_beat_after_aborted_attempt(b, event_dir)

            bg.update_beat_locked(beat_id, _clear_ptr)
            return True
    return False


def finalize_live_o3_jobs_before_shutdown(
    event_dir: Path,
    *,
    in_memory_jobs: dict | None = None,
    reason: str | None = None,
) -> int:
    """O3_SUBPROCESS_LIFECYCLE_V1 — terminal-stamp live O3 jobs before server shutdown."""
    event_dir = Path(event_dir)
    msg = reason or (
        "O3 job interrupted by server restart — prior clip preserved when on disk"
    )
    closed = 0
    jobs_dir = _jobs_dir(event_dir)
    if not jobs_dir.is_dir():
        return 0
    seen: set[str] = set()
    if in_memory_jobs:
        for job_id, row in in_memory_jobs.items():
            if not isinstance(row, dict):
                continue
            beat_id = str(row.get("beat_id") or "").strip()
            proc = row.get("process")
            if proc is not None and hasattr(proc, "poll") and proc.poll() is None:
                jid = str(job_id).strip()
                if jid and beat_id and jid not in seen:
                    close_o3_attempt(
                        jid,
                        beat_id,
                        event_dir,
                        "cancelled",
                        reason=msg,
                        phase_last="shutdown_interrupt",
                        persist_beat=True,
                    )
                    seen.add(jid)
                    closed += 1
    for term_path in jobs_dir.glob("*_terminal.json"):
        try:
            terminal = load_intent_terminal(term_path)
        except (OSError, json.JSONDecodeError):
            continue
        if str((terminal or {}).get("status") or "").strip() != INTENT_RUNNING_STATUS:
            continue
        job_id = term_path.name.replace("_terminal.json", "")
        if job_id in seen:
            continue
        beat_id = str((terminal or {}).get("beat_id") or "").strip()
        if not beat_id:
            intent_path = intent_path_for_job(job_id, event_dir)
            if intent_path.is_file():
                try:
                    beat_id = str(load_generation_intent(intent_path).get("beat_id") or "").strip()
                except (OSError, json.JSONDecodeError, ValueError):
                    beat_id = ""
        if not beat_id:
            continue
        if o3_subprocess_is_live(job_id, beat_id, event_dir, in_memory_jobs=in_memory_jobs):
            close_o3_attempt(
                job_id,
                beat_id,
                event_dir,
                "cancelled",
                reason=msg,
                phase_last="shutdown_interrupt",
                persist_beat=True,
            )
            closed += 1
            seen.add(job_id)
    return closed


def run_blocking_o3_startup_reconcile(prod_root: Path, scope_event_id: str | None = None) -> dict:
    """Close stale running terminals before HTTP serves traffic."""
    closed = 0
    errors: list[str] = []
    event_dirs: list[Path] = []
    if scope_event_id:
        num = scope_event_id.replace("Event_", "").strip()
        scoped = prod_root / f"Event_{num}"
        if scoped.is_dir():
            event_dirs.append(scoped)
    event_dirs.extend(discover_event_dirs(prod_root))
    seen: set[str] = set()
    for event_dir in event_dirs:
        key = str(event_dir.resolve())
        if key in seen:
            continue
        seen.add(key)
        jobs_dir = _jobs_dir(event_dir)
        if not jobs_dir.is_dir():
            continue
        for term_path in jobs_dir.glob("*_terminal.json"):
            try:
                terminal = load_intent_terminal(term_path)
            except (OSError, json.JSONDecodeError):
                continue
            if not terminal:
                continue
            if str(terminal.get("status") or "").strip() != INTENT_RUNNING_STATUS:
                continue
            job_id = term_path.name.replace("_terminal.json", "")
            intent_path = intent_path_for_job(job_id, event_dir)
            beat_id = str(terminal.get("beat_id") or "").strip()
            if not beat_id and intent_path.is_file():
                try:
                    beat_id = str(load_generation_intent(intent_path).get("beat_id") or "").strip()
                except (OSError, json.JSONDecodeError, ValueError):
                    beat_id = ""
            if not beat_id:
                continue
            if o3_subprocess_is_live(job_id, beat_id, event_dir):
                continue
            try:
                close_o3_attempt(
                    job_id,
                    beat_id,
                    event_dir,
                    "failed",
                    reason=O3_JOB_LOST_FAILURE_MESSAGE,
                    phase_last="startup_reconcile",
                    persist_beat=True,
                )
                closed += 1
            except Exception as exc:
                errors.append(f"{job_id}@{event_dir.name}: {exc}")
    return {"closed": closed, "errors": errors}


def log_indicates_active_o3_pipeline(log_text: str) -> bool:
    """True when subprocess log shows in-flight work (not terminal done/failed)."""
    if not log_text.strip():
        return False
    last = _last_json_blob(log_text)
    if last and last.get("ok") is True and (last.get("video") or last.get("playback_video")):
        return False
    for line in reversed(log_text.splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if row.get("phase") == "done" and row.get("video"):
            return False
        if row.get("phase") == "finalize" and row.get("video"):
            return False
        if row.get("ok") is True and (row.get("video") or row.get("playback_video")):
            return False
        phase = str(row.get("phase") or "").lower()
        if phase in _TERMINAL_PIPELINE_LOG_PHASES:
            return False
        if phase in _ACTIVE_PIPELINE_LOG_PHASES or phase:
            return True
    return False


def beat_has_active_intent(beat_id: str, event_dir: Path | None = None) -> bool:
    return active_intent_path_for_beat(
        beat_id,
        intent_event_dir_for_beat(beat_id, event_dir),
    ) is not None


def reconcile_stale_o3_intent_locks(sidecar: dict, event_dir: Path) -> int:
    """Close intent files that outlived a dead subprocess so ref/prompt drops unlock."""
    import beat_generator as bg
    from o3_job_status_contract import beat_o3_operator_busy, voice_fix_is_terminal_failure

    jobs_dir = _jobs_dir(event_dir)
    if not jobs_dir.is_dir():
        return 0
    closed = 0
    for intent_path in jobs_dir.glob("*_intent.json"):
        job_id = intent_path.name.replace("_intent.json", "")
        term_path = terminal_path_for_job(job_id, event_dir)
        if term_path.is_file():
            try:
                intent = load_generation_intent(intent_path)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            beat_id = str(intent.get("beat_id") or "").strip()
            if not beat_id:
                continue
            _, beat = bg.find_beat(sidecar, beat_id)
            terminal = load_intent_terminal(term_path)
            status = str((terminal or {}).get("status") or "").strip()
            if status == INTENT_RUNNING_STATUS:
                if not o3_subprocess_is_live(job_id, beat_id, event_dir):
                    close_o3_attempt(
                        job_id,
                        beat_id,
                        event_dir,
                        "failed",
                        reason=O3_JOB_LOST_FAILURE_MESSAGE,
                        phase_last="reconcile_running_terminal",
                        intent=intent,
                        persist_beat=False,
                    )
                    if beat:
                        from o3_job_status_contract import clear_o3_job_cache_fields

                        clear_o3_job_cache_fields(beat)
                        heal_o3_beat_after_aborted_attempt(beat)
                        beat["kling_o3_voice_fix_error"] = O3_JOB_LOST_FAILURE_MESSAGE
                    closed += 1
                continue
            if beat and not beat_o3_operator_busy(beat, event_dir):
                status = str(terminal.get("status") or "")
                if status in INTENT_TERMINAL_STATUSES:
                    lock_job = str(
                        beat.get("o3_active_intent_job_id")
                        or job_id_from_beat(beat)
                        or "",
                    )
                    if lock_job == job_id or beat.get("o3_active_intent_job_id") == job_id:
                        if status == "failed":
                            fail_msg = str((terminal.get("failure") or {}).get("message") or "")
                            if fail_msg:
                                beat["kling_o3_voice_fix_error"] = fail_msg
                                beat["kling_o3_last_attempt_failed_at"] = terminal.get("terminal_at")
                        elif status == "cancelled":
                            _heal_o3_beat_after_aborted_attempt(beat, terminal)
                        _clear_beat_intent_lock_fields(beat)
                        if beat.get("kling_o3_voice_fix_ui_job_id") == job_id:
                            beat.pop("kling_o3_voice_fix_ui_job_id", None)
                        closed += 1
            continue
        try:
            intent = load_generation_intent(intent_path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        beat_id = str(intent.get("beat_id") or "").strip()
        if not beat_id:
            continue
        _, beat = bg.find_beat(sidecar, beat_id)
        log_path = Path(str((intent.get("runtime") or {}).get("log_path") or ""))
        if not log_path.is_file():
            alt = jobs_dir / f"{job_id}_{beat_id}.log"
            if alt.is_file():
                log_path = alt
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
        if log_path.is_file():
            import time

            log_age_s = max(0.0, time.time() - log_path.stat().st_mtime)
        else:
            log_age_s = 0.0
        if (
            beat
            and job_id_from_beat(beat) == job_id
            and o3_subprocess_is_live(job_id, beat_id, event_dir)
        ):
            continue
        pid = (beat or {}).get("kling_o3_voice_fix_job_pid")
        if pid is not None and _pid_is_running(pid):
            continue
        voice_fix = str((beat or {}).get("kling_o3_voice_fix_status") or "")
        if voice_fix == "approved":
            done_row = _pipeline_done_from_log(log_path) if log_path.is_file() else None
            if not done_row and beat and not log_text.strip():
                # Beat still shows approved from a prior gen — only reuse the active
                # clip for genuinely stale orphan intents, never a fresh submit.
                video = str(beat.get("kling_o3_video_path") or "")
                if video and Path(video).is_file():
                    done_row = {"video": video}
            if done_row:
                video = str(done_row.get("video") or "")
                write_intent_terminal(job_id, event_dir, {
                    "intent_id": intent.get("intent_id"),
                    "status": "done",
                    "phase_last": "reconcile_voice_fix_approved",
                    "sidecar_persist_ok": True,
                    "delivered": {"video_path": video},
                })
                if beat:
                    _clear_beat_intent_lock_fields(beat)
                closed += 1
                continue
        if voice_fix_is_terminal_failure(voice_fix):
            beat_job_id = job_id_from_beat(beat)
            if beat_job_id and beat_job_id != job_id:
                continue
            write_intent_terminal(job_id, event_dir, {
                "intent_id": intent.get("intent_id"),
                "status": "failed",
                "phase_last": "reconcile_voice_fix_terminal",
                "sidecar_persist_ok": True,
                "failure": {
                    "message": str(
                        (beat or {}).get("kling_o3_voice_fix_error") or voice_fix
                    )[:500],
                },
            })
            if beat:
                _clear_beat_intent_lock_fields(beat)
            closed += 1
            continue
        done_row = _pipeline_done_from_log(log_path) if log_path.is_file() else None
        if done_row:
            video = str(done_row.get("video") or "")
            if video and Path(video).is_file():
                write_intent_terminal(job_id, event_dir, {
                    "intent_id": intent.get("intent_id"),
                    "status": "done_with_warning",
                    "phase_last": "reconcile_orphan_terminal",
                    "sidecar_persist_ok": False,
                    "delivered": {"video_path": video},
                    "warning": "Video on disk but sidecar persist failed during orphan reconcile",
                })
                if beat:
                    _clear_beat_intent_lock_fields(beat)
                closed += 1
                continue
        if '"phase": "done"' in log_text:
            continue
        close_o3_attempt(
            job_id,
            beat_id,
            event_dir,
            "failed",
            reason=O3_JOB_LOST_FAILURE_MESSAGE,
            phase_last="reconcile_stale_lock",
            intent=intent,
            persist_beat=True,
        )
        if beat:
            from o3_job_status_contract import clear_o3_job_cache_fields

            clear_o3_job_cache_fields(beat)
            _clear_beat_intent_lock_fields(beat)
            if not heal_o3_beat_after_aborted_attempt(beat):
                video = str(beat.get("kling_o3_video_path") or "")
                if video and Path(video).is_file():
                    from kling_stitch_readiness import align_beat_active_delivery_clip  # noqa: PLC0415

                    align_beat_active_delivery_clip(
                        beat,
                        video,
                        mark_voice_fix_approved=True,
                    )
            beat["kling_o3_voice_fix_error"] = O3_JOB_LOST_FAILURE_MESSAGE
        closed += 1
    return closed


def reconcile_stale_o3_intent_locks_all_events(sidecar: dict, prod_root: Path) -> int:
    """Reconcile orphaned intent locks under every ``Event_*`` (global sidecar)."""
    total = 0
    for event_dir in discover_event_dirs(prod_root):
        total += reconcile_stale_o3_intent_locks(sidecar, event_dir)
    return total


def active_intent_path_for_beat(beat_id: str, event_dir: Path) -> Path | None:
    jobs_dir = _jobs_dir(event_dir)
    if not jobs_dir.is_dir():
        return None
    bid = str(beat_id or "").strip()
    if not bid:
        return None
    candidates: list[tuple[str, Path]] = []
    for path in jobs_dir.glob("*_intent.json"):
        try:
            data = load_generation_intent(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if str(data.get("beat_id") or "").strip() != bid:
            continue
        job_id = str(data.get("job_id") or path.name.split("_intent")[0]).strip()
        term = terminal_path_for_job(job_id, event_dir)
        if term.is_file():
            try:
                tdata = load_intent_terminal(term)
                if str(tdata.get("status") or "") in INTENT_TERMINAL_STATUSES:
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        committed = str(data.get("committed_at") or "")
        candidates.append((committed, path))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][1]


def assert_canonical_mutation_allowed(beat_id: str, event_dir: Path | None = None) -> None:
    import beat_generator as bg
    from o3_job_status_contract import beat_job_busy

    sidecar = bg.read_sidecar_for_poll_snapshot(lock_timeout_s=2.0)
    _, beat = bg.find_beat(sidecar, beat_id)
    if beat and beat_job_busy(beat, event_dir):
        raise IntentActiveError(
            f"beat {beat_id} has active O3 job — operator fields are locked"
        )


def intent_poll_subset(intent: dict) -> dict:
    prompt = intent.get("prompt") or {}
    visual = intent.get("visual") or {}
    voice = intent.get("voice") or {}
    generation = intent.get("generation") or {}
    return {
        "intent_id": intent.get("intent_id"),
        "job_id": intent.get("job_id"),
        "beat_id": intent.get("beat_id"),
        "prompt": {
            "verbatim": prompt.get("verbatim"),
            "sha256": prompt.get("sha256"),
        },
        "visual": {
            "char_ref_abs_path": visual.get("char_ref_abs_path"),
            "bg_ref_abs_path": visual.get("bg_ref_abs_path"),
            "element_char_ref_gate": visual.get("element_char_ref_gate"),
        },
        "voice": {
            "element_id": voice.get("element_id"),
            "element_name": voice.get("element_name"),
            "kling_voice_id": voice.get("kling_voice_id"),
        },
        "generation": {
            "slot": generation.get("slot"),
            "slot_index": generation.get("slot_index"),
        },
    }


def submitted_audit_from_intent(intent: dict) -> dict:
    prompt = str((intent.get("prompt") or {}).get("verbatim") or "")
    visual = intent.get("visual") or {}
    voice = intent.get("voice") or {}
    gate = visual.get("element_char_ref_gate") or {}
    excerpt = prompt[:500]
    if "speaks" in prompt.lower():
        m = re.search(r"speaks[^:]*:\s*[\"']?(.{0,120})", prompt, re.I | re.S)
        if m:
            excerpt = m.group(0)[:500]
    return {
        "prompt_excerpt": excerpt,
        "char_ref": visual.get("char_ref_abs_path"),
        "element_id": voice.get("element_id"),
        "refer_images": gate.get("refer_images_resolved") or [],
        "generation_slot": (intent.get("generation") or {}).get("slot"),
    }


def build_generation_intent(
    *,
    beat: dict,
    sidecar: dict,
    body: dict,
    beat_id: str,
    event_dir: Path,
    job_id: str,
    attempt_id: str,
    log_path: Path,
    pipeline_script: Path,
    wavespeed_key: str | None,
) -> dict:
    """Build immutable intent from POST body. Raises IntentCommitError on block."""
    import beat_generator as bg
    from tools import kling_character_registry as reg
    from tools import kling_o3_prompt as o3p

    bid = str(beat_id).strip()
    from o3_job_status_contract import beat_job_busy

    if beat_job_busy(beat, event_dir):
        raise IntentCommitError(
            "BEAT_JOB_BUSY",
            "O3 generation is already running for this beat.",
            http_status=409,
            retry_safe=True,
        )

    user_prompt = str(body.get("kling_o3_prompt") or "").strip()
    if not user_prompt:
        raise IntentCommitError(
            "EMPTY_PROMPT",
            "Prompt box is empty — type the full O3 prompt before Generate.",
            http_status=400,
        )
    # Generate POST body is authoritative — Avatar/O3 builders must not read stale sidecar text.
    beat["kling_o3_prompt"] = user_prompt

    body_mode = str(
        body.get("generation_mode") or body.get("o3_generate_mode") or "",
    ).strip().lower()
    if body_mode in (
        bg.O3_GENERATE_MODE_VOICE_FIRST,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
        bg.O3_GENERATE_MODE_AVATAR,
    ):
        beat["o3_generate_mode"] = body_mode
    generation_mode = bg.resolve_beat_generation_mode(beat, sidecar)
    avatar_mode = generation_mode == bg.O3_GENERATE_MODE_AVATAR
    bg_ref_required = bg.o3_bg_ref_required_for_beat(beat, sidecar)
    element_o3_path = bg.element_char_ref_required_for_beat(beat, sidecar)
    ok_prompt, prompt_code, prompt_msg = bg.validate_o3_submit_prompt_for_mode(
        user_prompt,
        generation_mode,
    )
    if not ok_prompt:
        raise IntentCommitError(
            prompt_code,
            prompt_msg,
            http_status=400,
        )

    speaker = str(beat.get("speaker") or "").strip()
    if not speaker:
        raise IntentCommitError(
            "MISSING_SPEAKER",
            "Beat has no speaker.",
            http_status=400,
        )
    if not reg.is_speaker_voice_ready(speaker):
        raise IntentCommitError(
            "SPEAKER_NOT_VOICE_READY",
            f"{speaker!r} has no active Element + bound voice.",
            http_status=400,
        )

    event_id, phase = bg.segment_event_phase_for_beat(sidecar, bid)
    if not event_id or not phase:
        ctx = sidecar.get("active_context") or {}
        event_id = bg.normalize_bg_event_id(ctx.get("event_id") or "")
        phase = str(ctx.get("phase") or "pre")
    try:
        from operator_workbench_contract import materialize_o3_submit_refs

        char_ref, bg_ref = materialize_o3_submit_refs(
            body,
            beat,
            event_id=str(event_id or ""),
            phase=str(phase or "pre"),
        )
    except Exception as exc:
        print(f"[o3_intent] materialize refs fallback: {exc}", flush=True)
        char_ref, bg_ref = resolve_o3_submit_refs(body, beat)
    if not isinstance(char_ref, dict):
        raise IntentCommitError(
            "MISSING_O3_REF",
            (
                "Char ref must be set before generating Avatar Pro video."
                if avatar_mode
                else "Char ref and BG ref must be set before generating O3 video."
            ),
            http_status=400,
        )
    char_path = str(char_ref.get("abs_path") or "").strip()
    bg_path = ""
    if isinstance(bg_ref, dict):
        bg_path = str(bg_ref.get("abs_path") or "").strip()
    if not char_path or not Path(char_path).is_file():
        raise IntentCommitError(
            "MISSING_REF_FILE",
            f"Char ref file missing: {char_path}",
            http_status=400,
        )
    if bg_ref_required:
        if not isinstance(bg_ref, dict):
            raise IntentCommitError(
                "MISSING_O3_REF",
                "Char ref and BG ref must be set before generating O3 video.",
                http_status=400,
            )
        if not bg_path or not Path(bg_path).is_file():
            raise IntentCommitError(
                "MISSING_REF_FILE",
                f"BG ref file missing: {bg_path}",
                http_status=400,
            )

    ref_locked = bool(beat.get("reference_image_locked")) or bool(body.get("reference_image"))
    bg_locked = bool(beat.get("bg_ref_image_locked")) or bool(body.get("bg_ref_image"))
    work_beat = dict(beat)
    work_beat["reference_image"] = char_ref
    if bg_ref_required and isinstance(bg_ref, dict):
        work_beat["bg_ref_image"] = bg_ref
    if ref_locked:
        work_beat["reference_image_locked"] = True
    if bg_locked and bg_ref_required:
        work_beat["bg_ref_image_locked"] = True

    registration_action = "skipped_avatar_pro" if avatar_mode else "already_matched"
    gate_detail: str | None = None
    element_entry: dict[str, Any] = {}
    proven_bind: dict[str, Any] = {}
    if element_o3_path:
        aligned, gate_detail = reg.char_ref_matches_element_images(
            char_path, speaker, allow_pose_dir_fallback=False,
        )
    else:
        aligned = True
    if element_o3_path and not aligned:
        if ref_locked and wavespeed_key:
            reg_result = bg.try_register_dropped_char_ref_on_element(work_beat, wavespeed_key)
            if reg_result.get("ok") and reg_result.get("action") == "already_matched":
                aligned, gate_detail = reg.char_ref_matches_element_images(
                    char_path, speaker, allow_pose_dir_fallback=False,
                )
                if not aligned:
                    try:
                        reg_result = reg.reconcile_char_ref_with_element(
                            speaker, char_path, wavespeed_key,
                        )
                        reg_result["action"] = "reconciled_after_pose_only_match"
                    except Exception as exc:
                        reg_result = {"ok": False, "reason": str(exc)}
            if not reg_result.get("ok"):
                raise IntentCommitError(
                    "ELEMENT_VISUAL_MISMATCH",
                    str(work_beat.get("element_char_ref_error") or gate_detail or reg_result.get("reason") or ""),
                    http_status=400,
                    detail={
                        "char_ref": char_path,
                        "refer_images": _refer_images_rel(speaker),
                    },
                )
            registration_action = str(reg_result.get("action") or "registered")
            aligned, gate_detail = reg.char_ref_matches_element_images(
                char_path, speaker, allow_pose_dir_fallback=False,
            )
        if not aligned:
            raise IntentCommitError(
                "ELEMENT_REGISTRATION_FAILED" if registration_action != "already_matched" else "ELEMENT_VISUAL_MISMATCH",
                str(gate_detail or work_beat.get("element_char_ref_error") or ""),
                http_status=400,
                detail={
                    "char_ref": char_path,
                    "refer_images": _refer_images_rel(speaker),
                },
            )

    if element_o3_path:
        element_entry = bg.resolve_o3_element_list_entry(work_beat, speaker) or {}
        if not element_entry:
            raise IntentCommitError(
                "MISSING_ELEMENT_ENTRY",
                f"{speaker!r} has no active element_list entry.",
                http_status=400,
            )
        proven_err = bg.validate_proven_o3_element_submit(
            work_beat,
            speaker,
            str(element_entry.get("element_id") or ""),
        )
        if proven_err:
            raise IntentCommitError(
                "PROVEN_O3_BIND_MISMATCH",
                proven_err,
                http_status=409,
            )

        from tools.kling_voice_bind import (
            advance_o3_element_quality_for_proven_registry,
            detect_voice_bind_drift,
        )

        reg_eid = str(element_entry.get("element_id") or "")
        reg_vid = str(reg.get_bound_voice_id(speaker) or element_entry.get("voice_id") or "")
        advance_o3_element_quality_for_proven_registry(
            work_beat,
            speaker,
            registry_element_id=reg_eid,
            registry_voice_id=reg_vid,
        )

        drift_msg = detect_voice_bind_drift(
            work_beat,
            speaker,
            reg_vid,
        )
        if drift_msg and not body.get("accept_voice_drift"):
            raise IntentCommitError(
                "VOICE_BIND_DRIFT",
                drift_msg,
                http_status=409,
                retry_safe=True,
            )
        proven_bind = reg.resolve_proven_o3_bind(speaker) or {}
    else:
        element_entry = bg.resolve_o3_element_list_entry(work_beat, speaker) or {}

    prepared = bg.prepare_kling_o3_prompt_for_submit(work_beat, user_prompt)
    avatar_prepared = ""
    if avatar_mode:
        from beat_avatar_lipsync import build_avatar_beat_prompt

        avatar_prepared = build_avatar_beat_prompt(work_beat, speaker=speaker).strip()

    if prepared and re.search(r"\b(?:speaks|says)\b", prepared, re.I):
        extracted = bg.extract_spoken_dialogue_from_kling_prompt(prepared)
        if not extracted:
            raise IntentCommitError(
                "NO_QUOTED_DIALOGUE",
                "No spoken dialogue found in the prompt voice line.",
                http_status=400,
            )
        spoken_sent = extracted
    else:
        spoken_sent = bg.extract_spoken_dialogue_from_kling_prompt(user_prompt) or ""

    sidecar_gen = int(beat.get("kling_o3_generation") or 0)
    disk_gen_max = bg.highest_o3_generation_on_disk(bid, event_dir)
    next_gen = max(sidecar_gen, disk_gen_max) + 1
    clips_dir = event_dir / "kling_o3_clips"
    if avatar_mode:
        master = clips_dir / f"{bid}_g{next_gen}_avatar_pro.mp4"
    else:
        master = clips_dir / f"{bid}_g{next_gen}_element_o3_master.mp4"
    delivery = master.with_name(master.stem + "_delivery.mp4")

    replace_slot = body.get("replace_slot_index", beat.get("kling_o3_replace_slot_index", 0))
    try:
        replace_slot = max(0, min(2, int(replace_slot)))
    except (TypeError, ValueError):
        replace_slot = 0

    duration = bg.resolve_kling_o3_submit_duration(work_beat, prepared or user_prompt)

    ev_m = re.match(r"bg_arc\d+_event(\d+)_", bid)
    event_num = ev_m.group(1) if ev_m else "1"
    phase = bg.segment_phase_for_beat(sidecar, bid) or "pre"

    intent_id = uuid.uuid4().hex

    visual: dict[str, Any] = {
        "char_ref_abs_path": char_path,
        "char_ref_sha256": _sha256_file(char_path),
        "reference_image_locked": ref_locked,
    }
    if bg_path and Path(bg_path).is_file():
        visual["bg_ref_abs_path"] = bg_path
        visual["bg_ref_sha256"] = _sha256_file(bg_path)
        visual["bg_ref_image_locked"] = bg_locked
    if element_o3_path:
        visual["element_char_ref_gate"] = {
            "aligned": True,
            "method": "live_refer_images",
            "refer_images_resolved": _refer_images_rel(speaker),
            "registration_action": registration_action,
            "detail": gate_detail or None,
        }

    checks_passed = [
        "prompt_non_empty",
        "o3_prompt_mode_valid",
        "char_ref_file_exists",
        "slot_reserved",
    ]
    if bg_ref_required:
        checks_passed.append("bg_ref_file_exists")
    if element_o3_path:
        checks_passed.extend(["element_char_ref_aligned", "proven_o3_bind_valid"])

    voice_block: dict[str, Any] = {
        "speaker": speaker,
    }
    if avatar_mode:
        voice_block["transport"] = "elevenlabs_avatar_pro"
    if element_entry:
        voice_block["element_id"] = str(element_entry.get("element_id") or "")
        voice_block["element_name"] = str(element_entry.get("element_name") or "")
        voice_block["kling_voice_id"] = str(
            element_entry.get("voice_id") or reg.get_bound_voice_id(speaker) or "",
        )
    if proven_bind:
        voice_block["proven_o3_bind"] = {
            "lock_element_id": bool(proven_bind.get("lock_element_id")),
            "proven_from_beat_id": str(proven_bind.get("proven_from_beat_id") or ""),
        }

    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id,
        "job_id": job_id,
        "beat_id": bid,
        "event_id": f"Event_{event_num}",
        "phase": phase,
        "generation_mode": generation_mode,
        "committed_at": datetime.now(timezone.utc).isoformat(),
        "committed_by": "submit-arlo-o3-voice",
        "prompt": {
            "verbatim": user_prompt,
            "prepared_for_api": avatar_prepared or prepared or user_prompt,
            "spoken_sent": spoken_sent,
            "sha256": _sha256_text(user_prompt),
        },
        "visual": visual,
        "voice": voice_block,
        "generation": {
            "slot": f"g{next_gen}",
            "slot_index": next_gen,
            "master_clip_path": str(master),
            "delivery_clip_path": str(delivery),
            "sidecar_gen_before": sidecar_gen,
            "disk_gen_max_before": disk_gen_max,
            "replace_slot_index": replace_slot,
            "duration": duration,
        },
        "runtime": {
            "attempt_id": attempt_id,
            "log_path": str(log_path),
            "pipeline_script": str(pipeline_script),
        },
        "preflight": {
            "checks_passed": checks_passed,
            "canonical_skipped": [
                "ensure_operator_insert_char_ref_parity",
                "finalize_proven_element_beat",
                "apply_kling_o3_defaults_to_beat",
                "heal_o3_element_submit_prompt",
            ],
        },
    }
    return intent


def _refer_images_rel(speaker: str) -> list[str]:
    from tools import kling_character_registry as reg

    root = reg.prod_root()
    paths = reg.element_image_paths(speaker)
    out: list[str] = []
    for p in paths:
        try:
            out.append(str(p.relative_to(root)))
        except ValueError:
            out.append(str(p))
    return out


def sidecar_visual_ref_fields_from_intent(intent: dict) -> dict:
    """Operator ref snapshot for sidecar commit/finalize (voice-first + element native)."""
    visual = intent.get("visual") or {}
    out: dict[str, Any] = {}
    char_path = str(visual.get("char_ref_abs_path") or "").strip()
    bg_path = str(visual.get("bg_ref_abs_path") or "").strip()
    if char_path:
        out["reference_image"] = {"abs_path": char_path}
    if visual.get("reference_image_locked", True):
        out["reference_image_locked"] = True
    if bg_path:
        out["bg_ref_image"] = {"abs_path": bg_path}
    if visual.get("bg_ref_image_locked", True):
        out["bg_ref_image_locked"] = True
    return out


def load_intent_visual_ref_fields_from_env() -> dict:
    """Finalize helper — re-assert refs from MN_O3_INTENT_PATH when subprocess has intent."""
    path = (os.environ.get("MN_O3_INTENT_PATH") or "").strip()
    if not path:
        return {}
    try:
        intent = load_generation_intent(Path(path))
    except Exception:
        return {}
    return sidecar_visual_ref_fields_from_intent(intent)


def load_intent_visual_ref_fields_from_job_log(
    log_path: str | Path | None,
    event_dir: str | Path | None = None,
) -> dict:
    """Orphan recovery — re-assert operator refs from job_id intent on disk."""
    if not log_path:
        return {}
    name = Path(log_path).name
    m = re.match(r"^([0-9a-f]{8})_", name)
    if not m:
        return {}
    job_id = m.group(1)
    if event_dir is None:
        env_event = (os.environ.get("MN_LIPSYNC_STAGING_EVENT_DIR") or "").strip()
        if env_event:
            event_dir = Path(env_event)
        else:
            prod = Path(os.environ.get("MN_PROD_ROOT") or Path(__file__).resolve().parent.parent)
            event_dir = prod / "Event_1"
    intent_path = intent_path_for_job(job_id, Path(event_dir))
    if not intent_path.is_file():
        return {}
    try:
        intent = load_generation_intent(intent_path)
    except Exception:
        return {}
    return sidecar_visual_ref_fields_from_intent(intent)


def sidecar_fields_from_intent(intent: dict) -> dict:
    """Beat fields to mirror at commit time (same bytes as intent, not rebuilt)."""
    prompt = str((intent.get("prompt") or {}).get("verbatim") or "")
    generation = intent.get("generation") or {}
    return {
        "kling_o3_prompt": prompt,
        "o3_prompt_box_law": True,
        **sidecar_visual_ref_fields_from_intent(intent),
        "kling_o3_replace_slot_index": generation.get("replace_slot_index", 0),
        "kling_o3_duration": generation.get("duration"),
        "element_char_ref_ok": True,
        "o3_current_job_id": intent.get("job_id"),
    }
