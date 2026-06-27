"""Port-scoped exclusivity for production_server.py (PRODUCTION_SERVER_PORT_GUARD_V1).

One localhost port → at most one storyboard server listener. Port is the authority
key (not event_dir): duplicate listeners came from event-scoped pid files plus
several launch paths that did not agree on preemption.

Registry + flock live under ~/.mindfulnest/runtime/servers/ (local, not Dropbox).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DEDICATED_PORT_MIN = 5111
DEDICATED_PORT_MAX = 5199
CODE = "PRODUCTION_SERVER_PORT_GUARD_V1"


def port_to_event_id(port: int) -> str | None:
    """Map dedicated storyboard port → Event_N (matches event_server_port.sh)."""
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        return None
    if port_i < DEDICATED_PORT_MIN or port_i > DEDICATED_PORT_MAX:
        return None
    n = port_i - 5110
    if n < 1:
        return None
    return f"Event_{n}"


def dedicated_port_for_event_id(event_id: str) -> int | None:
    """Inverse of port_to_event_id — Event_N → 5110+N."""
    eid = str(event_id or "").strip()
    if not eid.startswith("Event_"):
        return None
    suffix = eid[len("Event_") :]
    if not suffix.isdigit():
        return None
    n = int(suffix)
    if n < 1:
        return None
    port = 5110 + n
    if port < DEDICATED_PORT_MIN or port > DEDICATED_PORT_MAX:
        return None
    return port


def runtime_servers_dir() -> Path:
    root = Path.home() / ".mindfulnest" / "runtime" / "servers"
    root.mkdir(parents=True, exist_ok=True)
    return root


def lock_path(port: int) -> Path:
    return runtime_servers_dir() / f"port_{port}.lock"


def registry_path(port: int) -> Path:
    return runtime_servers_dir() / f"port_{port}.json"


def legacy_event_pid_path(event_dir: Path, port: int) -> Path:
    return Path(event_dir) / f"production_server_{port}.pid"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_production_server_cmdline(cmd: str) -> bool:
    lowered = (cmd or "").lower()
    return "production_server.py" in lowered


def read_registry(port: int) -> dict | None:
    path = registry_path(port)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def write_registry(port: int, record: dict) -> None:
    path = registry_path(port)
    payload = dict(record)
    payload.setdefault("code", CODE)
    payload.setdefault("updated_at", _utc_now_iso())
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def clear_registry(port: int, *, pid: int | None = None) -> None:
    path = registry_path(port)
    if not path.is_file():
        return
    if pid is not None:
        reg = read_registry(port)
        if reg and int(reg.get("pid") or 0) != int(pid):
            return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def process_cmdline(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "args="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, OSError, ValueError):
        return ""


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def listeners_on_port(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return sorted(set(pids))


def production_server_pids_for_port(port: int) -> list[int]:
    """Listeners on port plus orphan production_server processes bound to same --port."""
    found: set[int] = set(listeners_on_port(port))
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "production_server.py"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        out = ""
    port_needle = f"--port {port}"
    port_eq = f"--port={port}"
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        cmd = process_cmdline(pid)
        if not _is_production_server_cmdline(cmd):
            continue
        if port_needle in cmd or port_eq in cmd or f" -p {port} " in f" {cmd} ":
            found.add(pid)
    return sorted(found)


def terminate_pid(pid: int, *, graceful: bool = True) -> None:
    if pid <= 0 or not process_alive(pid):
        return
    sig = signal.SIGTERM if graceful else signal.SIGKILL
    try:
        os.kill(pid, sig)
    except OSError:
        return


def terminate_port_servers(
    port: int,
    *,
    exclude_pids: set[int] | None = None,
    reason: str = "ensure_exclusive_port",
) -> list[int]:
    exclude = exclude_pids or set()
    killed: list[int] = []
    targets = [pid for pid in production_server_pids_for_port(port) if pid not in exclude]
    if not targets:
        return killed
    print(
        f"[port-guard] {reason}: port {port} clearing {len(targets)} "
        f"production_server pid(s): {targets}",
        flush=True,
    )
    for pid in targets:
        terminate_pid(pid, graceful=True)
        killed.append(pid)
    if killed:
        time.sleep(1.5)
        for pid in list(killed):
            if process_alive(pid):
                print(f"[port-guard] port {port} pid {pid} still alive — SIGKILL", flush=True)
                terminate_pid(pid, graceful=False)
        time.sleep(0.5)
    return killed


def cleanup_legacy_event_pid(event_dir: Path, port: int) -> None:
    legacy = legacy_event_pid_path(event_dir, port)
    if not legacy.is_file():
        return
    try:
        pid = int(legacy.read_text(encoding="utf-8").strip())
    except ValueError:
        try:
            legacy.unlink(missing_ok=True)
        except OSError:
            pass
        return
    if process_alive(pid):
        cmd = process_cmdline(pid)
        if _is_production_server_cmdline(cmd):
            terminate_pid(pid, graceful=True)
            time.sleep(1.0)
    try:
        legacy.unlink(missing_ok=True)
    except OSError:
        pass


def port_bindable(port: int, retries: int = 10, delay: float = 1.0) -> bool:
    for attempt in range(retries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return True
            except OSError:
                if attempt < retries - 1:
                    print(
                        f"[port-guard] port {port} still in use "
                        f"(attempt {attempt + 1}/{retries})",
                        flush=True,
                    )
                    time.sleep(delay)
    return False


@contextmanager
def port_startup_lock(port: int) -> Iterator[None]:
    path = lock_path(port)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _preempt_port_locked(
    port: int,
    *,
    event_dir: Path,
    exclude_pids: set[int],
) -> None:
    cleanup_legacy_event_pid(event_dir, port)
    reg = read_registry(port)
    if reg:
        reg_pid = int(reg.get("pid") or 0)
        if reg_pid and reg_pid not in exclude_pids and process_alive(reg_pid):
            cmd = process_cmdline(reg_pid)
            if _is_production_server_cmdline(cmd):
                terminate_port_servers(
                    port, exclude_pids=exclude_pids, reason="registry_stale",
                )
    terminate_port_servers(port, exclude_pids=exclude_pids, reason="port_preempt")
    if not port_bindable(port):
        raise RuntimeError(f"port {port} still in use after preemption")


@contextmanager
def port_startup_guard(
    port: int,
    *,
    event_id: str,
    event_dir: Path,
    exclude_pid: int | None = None,
) -> Iterator[None]:
    """Hold port flock through bind — prevents a second launcher from preempting mid-startup."""
    exclude = {exclude_pid} if exclude_pid else set()
    with port_startup_lock(port):
        _preempt_port_locked(port, event_dir=event_dir, exclude_pids=exclude)
        yield


def ensure_exclusive_port(
    port: int,
    *,
    event_id: str,
    event_dir: Path,
    exclude_pid: int | None = None,
) -> None:
    """Shell/CLI preemption — clears port before spawning production_server."""
    with port_startup_guard(
        port,
        event_id=event_id,
        event_dir=event_dir,
        exclude_pid=exclude_pid,
    ):
        return


def register_server_port(
    port: int,
    *,
    pid: int,
    event_id: str,
    event_dir: Path,
) -> None:
    record = {
        "port": port,
        "pid": pid,
        "event_id": event_id,
        "event_dir": str(Path(event_dir).resolve()),
        "started_at": _utc_now_iso(),
    }
    write_registry(port, record)
    legacy = legacy_event_pid_path(event_dir, port)
    try:
        legacy.write_text(str(pid), encoding="utf-8")
    except OSError:
        print(f"[port-guard] WARNING: could not write legacy pid file {legacy}", flush=True)


def unregister_server_port(port: int, *, pid: int) -> None:
    clear_registry(port, pid=pid)
    reg = read_registry(port)
    if reg is None:
        return


def audit_port_listeners(port: int) -> dict:
    listeners = listeners_on_port(port)
    servers = production_server_pids_for_port(port)
    reg = read_registry(port)
    return {
        "port": port,
        "listeners": listeners,
        "production_server_pids": servers,
        "duplicate_listeners": len(listeners) > 1,
        "orphan_servers": sorted(set(servers) - set(listeners)),
        "registry": reg,
    }


def _cli_ensure(args: argparse.Namespace) -> int:
    ensure_exclusive_port(
        int(args.port),
        event_id=str(args.event_id),
        event_dir=Path(args.event_dir),
        exclude_pid=int(args.exclude_pid) if args.exclude_pid else None,
    )
    print(f"[port-guard] OK port {args.port} exclusive for {args.event_id}", flush=True)
    return 0


def _cli_audit(args: argparse.Namespace) -> int:
    data = audit_port_listeners(int(args.port))
    print(json.dumps(data, indent=2, sort_keys=True))
    if data["duplicate_listeners"] or data["orphan_servers"]:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="production_server port exclusivity guard")
    sub = parser.add_subparsers(dest="command", required=True)

    ensure_p = sub.add_parser("ensure", help="Preempt prior listeners and verify port is free")
    ensure_p.add_argument("--port", type=int, required=True)
    ensure_p.add_argument("--event-id", required=True)
    ensure_p.add_argument("--event-dir", required=True)
    ensure_p.add_argument("--exclude-pid", type=int, default=0)
    ensure_p.set_defaults(func=_cli_ensure)

    audit_p = sub.add_parser("audit", help="Report listeners/registry for a port")
    audit_p.add_argument("--port", type=int, required=True)
    audit_p.set_defaults(func=_cli_audit)

    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    prod_root = Path(__file__).resolve().parent.parent
    if str(prod_root) not in sys.path:
        sys.path.insert(0, str(prod_root))
    raise SystemExit(main())
