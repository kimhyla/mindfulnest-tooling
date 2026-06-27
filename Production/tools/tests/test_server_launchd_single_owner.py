#!/usr/bin/env python3
"""SERVER_LAUNCHD_SINGLE_OWNER_V1 — restart mutex + launchd handoff contracts."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVER = REPO / "tools" / "production_server.py"
INSTALL = REPO / "scripts" / "install_production_server_launchagent.sh"
DEPLOY = REPO / "scripts" / "deploy_storyboard_v59.sh"
START = REPO / "scripts" / "start_event_server.sh"


def test_restart_mutex_and_launchd_handoff_in_server() -> None:
    text = SERVER.read_text(encoding="utf-8")
    assert "_restart_lock" in text
    assert "_perform_server_restart_locked" in text
    assert "duplicate restart ignored" in text
    assert "MN_LAUNCHD_MANAGED" in text
    assert "SERVER_LAUNCHD_SINGLE_OWNER_V1" in text
    assert "os._exit(0)" in text


def test_install_sets_launchd_managed_and_idempotent_reload() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert "SERVER_LAUNCHD_SINGLE_OWNER_V1" in text
    assert "MN_LAUNCHD_MANAGED" in text
    assert "plist unchanged" in text
    assert "cmp -s" in text
    assert "nohup env PRODUCTION_SERVER_SINGLE_MACHINE" not in text


def test_deploy_uses_launchd_only_not_nohup() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "SERVER_LAUNCHD_SINGLE_OWNER_V1" in text
    assert "install_production_server_launchagent.sh" in text
    assert "nohup env PRODUCTION_SERVER_SINGLE_MACHINE" not in text
    assert "launchd server ready" in text
    assert "(g.6) syncing production-server launch agent" not in text


def test_start_event_server_delegates_to_launchagent() -> None:
    text = START.read_text(encoding="utf-8")
    assert "install_production_server_launchagent.sh" in text
    assert "nohup env PRODUCTION_SERVER_SINGLE_MACHINE" not in text
    assert "SERVER_LAUNCHD_SINGLE_OWNER_V1" in text
