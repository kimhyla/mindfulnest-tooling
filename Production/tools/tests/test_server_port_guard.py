"""PRODUCTION_SERVER_PORT_GUARD_V1 — port-scoped single listener contracts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.server_port_guard import (
    CODE,
    audit_port_listeners,
    ensure_exclusive_port,
    port_startup_guard,
    production_server_pids_for_port,
    read_registry,
    register_server_port,
    unregister_server_port,
)

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "tools" / "production_server.py"
START = REPO / "scripts" / "start_event_server.sh"
DEPLOY = REPO / "scripts" / "deploy_storyboard_v59.sh"
ENSURE = REPO / "scripts" / "ensure_server_port.sh"


def test_production_server_imports_port_guard() -> None:
    text = SERVER.read_text(encoding="utf-8")
    assert "from lib.server_port_guard import" in text
    assert "port_startup_guard(" in text
    assert "register_server_port(" in text
    assert "unregister_server_port(" in text


def test_launch_scripts_delegate_to_ensure_server_port() -> None:
    assert ENSURE.is_file()
    for path in (START, DEPLOY):
        text = path.read_text(encoding="utf-8")
        assert "ensure_server_port.sh" in text
        assert 'lsof -ti:"${SERVER_PORT}" | xargs kill -9' not in text


def test_registry_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lib.server_port_guard.runtime_servers_dir",
        lambda: tmp_path,
    )
    register_server_port(
        5112,
        pid=4242,
        event_id="Event_2",
        event_dir=tmp_path / "Event_2",
    )
    reg = read_registry(5112)
    assert reg is not None
    assert reg["pid"] == 4242
    assert reg["event_id"] == "Event_2"
    assert reg["code"] == CODE
    unregister_server_port(5112, pid=4242)
    assert read_registry(5112) is None


def test_ensure_exclusive_port_preempts_listeners(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lib.server_port_guard.runtime_servers_dir",
        lambda: tmp_path,
    )
    killed: list[int] = []

    def _fake_terminate(port: int, *, exclude_pids=None, reason: str = "") -> list[int]:  # noqa: ANN001
        killed.extend([99, 100])
        return [99, 100]

    monkeypatch.setattr("lib.server_port_guard.terminate_port_servers", _fake_terminate)
    monkeypatch.setattr("lib.server_port_guard.port_bindable", lambda port, **kw: True)
    monkeypatch.setattr("lib.server_port_guard.cleanup_legacy_event_pid", lambda *a, **k: None)

    ensure_exclusive_port(
        5112,
        event_id="Event_2",
        event_dir=tmp_path / "Event_2",
    )
    assert killed == [99, 100]


def test_audit_flags_duplicate_listeners(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lib.server_port_guard.listeners_on_port", lambda port: [1, 2])
    monkeypatch.setattr("lib.server_port_guard.production_server_pids_for_port", lambda port: [1, 2, 3])
    monkeypatch.setattr("lib.server_port_guard.read_registry", lambda port: None)
    report = audit_port_listeners(5112)
    assert report["duplicate_listeners"] is True
    assert report["orphan_servers"] == [3]


def test_production_server_pids_for_port_filters_by_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lib.server_port_guard.listeners_on_port", lambda port: [10])

    def _cmd(pid: int) -> str:
        return {
            10: "python production_server.py --port 5112 --event-id Event_2",
            11: "python production_server.py --port 5111 --event-id Event_1",
        }.get(pid, "")

    monkeypatch.setattr("lib.server_port_guard.process_cmdline", _cmd)

    def _pgrep(*args, **kwargs):  # noqa: ANN001, ARG001
        return "10\n11\n"

    with patch("lib.server_port_guard.subprocess.check_output", side_effect=_pgrep):
        pids = production_server_pids_for_port(5112)
    assert pids == [10]
