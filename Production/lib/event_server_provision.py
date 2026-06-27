"""EVENT_DEDICATED_SERVER_PROVISION_V1 — idempotent launchd provision for Event_N ports.

Delegates to existing bash scripts (SERVER_LAUNCHD_SINGLE_OWNER_V1):
  ensure_server_port.sh → install_production_server_launchagent.sh

Any running storyboard server may provision any Event_<digits> folder under
Production/ — local operator Mac only.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.paths import EVENT_DIR, TOOLING_ROOT, dropbox_root
from lib.server_port_guard import dedicated_port_for_event_id

CODE = "EVENT_DEDICATED_SERVER_PROVISION_V1"
DEFAULT_WAIT_SECONDS = 45


@dataclass(frozen=True)
class ProvisionResult:
    ok: bool
    event_id: str
    port: int | None = None
    bookmark_url: str | None = None
    ready: bool = False
    skipped: bool = False
    reason: str | None = None
    already_running: bool = False
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "event_id": self.event_id,
            "port": self.port,
            "bookmark_url": self.bookmark_url,
            "ready": self.ready,
            "skipped": self.skipped,
            "reason": self.reason,
            "already_running": self.already_running,
            "error": self.error,
            "code": CODE,
        }


def _provision_lock_path(port: int) -> Path:
    root = Path.home() / ".mindfulnest" / "runtime" / "servers"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"provision_port_{port}.lock"


def _event_http_ready(port: int, event_id: str, *, timeout: float = 3.0) -> bool:
    url = f"http://127.0.0.1:{port}/api/event/current"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode())
            return bool(data.get("ok")) and data.get("event_id") == event_id
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return False


def wait_for_event_server_http(
    port: int,
    event_id: str,
    *,
    timeout_seconds: float = DEFAULT_WAIT_SECONDS,
    poll_interval: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _event_http_ready(port, event_id):
            return True
        time.sleep(poll_interval)
    return False


def bookmark_url_for_event(event_id: str, port: int) -> str:
    return f"http://localhost:{port}/?event={event_id}"


def _scripts_dir() -> Path:
    return TOOLING_ROOT / "Production" / "scripts"


def _run_bash_script(script_name: str, *args: str) -> None:
    script = _scripts_dir() / script_name
    if not script.is_file():
        raise FileNotFoundError(f"missing script: {script}")
    env = os.environ.copy()
    env.setdefault("MN_TOOLING_ROOT", str(TOOLING_ROOT))
    env.setdefault("MN_DROPBOX_ROOT", str(dropbox_root()))
    subprocess.run(
        ["bash", str(script), *args],
        check=True,
        env=env,
        cwd=str(_scripts_dir()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def provision_dedicated_event_server(
    event_id: str,
    *,
    event_dir: Path | None = None,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
) -> ProvisionResult:
    """Install launchd agent + wait until dedicated port serves event_id."""
    eid = str(event_id or "").strip()
    port = dedicated_port_for_event_id(eid)
    if port is None:
        return ProvisionResult(
            ok=True,
            event_id=eid,
            skipped=True,
            reason="not_dedicated_event",
        )

    ev_dir = Path(event_dir) if event_dir else EVENT_DIR(eid)
    if not ev_dir.is_dir():
        return ProvisionResult(
            ok=False,
            event_id=eid,
            port=port,
            error=f"event_dir missing: {ev_dir}",
        )

    bookmark = bookmark_url_for_event(eid, port)
    if _event_http_ready(port, eid):
        return ProvisionResult(
            ok=True,
            event_id=eid,
            port=port,
            bookmark_url=bookmark,
            ready=True,
            already_running=True,
        )

    lock_path = _provision_lock_path(port)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if _event_http_ready(port, eid):
            return ProvisionResult(
                ok=True,
                event_id=eid,
                port=port,
                bookmark_url=bookmark,
                ready=True,
                already_running=True,
            )
        _run_bash_script(
            "ensure_server_port.sh",
            str(port),
            eid,
            str(ev_dir),
        )
        _run_bash_script("install_production_server_launchagent.sh", eid)
    except (subprocess.CalledProcessError, OSError, FileNotFoundError) as exc:
        out = ""
        if isinstance(exc, subprocess.CalledProcessError) and exc.stdout:
            out = str(exc.stdout)[-500:]
        msg = f"{exc}" + (f" — {out}" if out else "")
        print(f"[event-provision] FAIL {eid} :{port}: {msg}", flush=True)
        return ProvisionResult(
            ok=False,
            event_id=eid,
            port=port,
            bookmark_url=bookmark,
            ready=False,
            error=msg,
        )
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    ready = wait_for_event_server_http(port, eid, timeout_seconds=wait_seconds)
    return ProvisionResult(
        ok=ready,
        event_id=eid,
        port=port,
        bookmark_url=bookmark,
        ready=ready,
        error=None if ready else f"server not ready on :{port} after {wait_seconds}s",
    )


def provision_dedicated_event_server_background(event_id: str) -> None:
    """Fire-and-forget kickstart after event_create (daemon thread entry)."""
    try:
        provision_dedicated_event_server(event_id)
    except Exception as exc:  # noqa: BLE001 — background must not crash server
        print(f"[event-provision] background FAIL {event_id}: {exc}", flush=True)
