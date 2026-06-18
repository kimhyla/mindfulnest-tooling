"""Lipsync public-host readiness — R2 credentials + WaveSpeed-reachable staging."""
from __future__ import annotations

from unittest.mock import patch

import lipsync_public_host as host


def test_lipsync_ready_when_r2_env_complete():
    env = {
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_ACCOUNT_ID": "acct",
        "R2_BUCKET_NAME": "bucket",
    }
    assert host.r2_credentials_present(env=env) is True
    assert host.lipsync_public_host_ready(env=env) is True


def test_lipsync_not_ready_without_r2_or_public_base():
    assert host.lipsync_public_host_ready(env={}) is False
    caps = host.probe_lipsync_public_host_capabilities(creds={})
    assert caps["lipsync_public_host_ready"] is False
    assert caps["lipsync_public_host_message"]


def test_inject_lipsync_r2_env_from_creds_dict():
    target: dict[str, str] = {}
    host.inject_lipsync_r2_env(
        target,
        {
            "r2_access_key_id": "AKIA_TEST",
            "r2_secret_access_key": "secret",
            "r2_account_id": "acct",
            "r2_bucket_name": "mindfulnest-assets",
            "r2_cdn_base_url": "https://cdn.mindfulnest.app",
        },
    )
    assert target["R2_ACCESS_KEY_ID"] == "AKIA_TEST"
    assert target["MN_R2_CDN_BASE_URL"] == "https://cdn.mindfulnest.app"


def test_submit_handler_blocks_voice_first_without_public_host():
    bg_src = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "server_handlers"
        / "background.py"
    ).read_text(encoding="utf-8")
    assert "LIPSYNC_HOSTING_NOT_CONFIGURED" in bg_src
    assert "lipsync_public_host_ready" in bg_src
    assert "inject_lipsync_r2_env" in bg_src


def test_start_event_server_exports_lipsync_env():
    script = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "scripts"
        / "start_event_server.sh"
    ).read_text(encoding="utf-8")
    assert "lipsync_public_host.py" in script
    assert "--shell-export" in script


def test_credentials_parse_cloudflare_r2_rows():
    import sys
    from pathlib import Path

    tools = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(tools / "credentials_lib"))
    from credentials import _parse_keys_file  # type: ignore

    content = """
| **Cloudflare R2** | Access Key ID | `AKIA_R2_TEST` | |
| **Cloudflare R2** | Secret Access Key | `secret_r2_test` | |
| **Cloudflare R2** | Account ID | `00000000000000000000000000000000` | |
| **Cloudflare R2** | Bucket Name | `mindfulnest-assets` | |
"""
    creds = _parse_keys_file(content)
    assert creds["r2_access_key_id"] == "AKIA_R2_TEST"
    assert creds["r2_bucket_name"] == "mindfulnest-assets"


def test_probe_capabilities_includes_lipsync_host_flag():
    import beat_generator as bg

    with patch("lipsync_public_host.lipsync_public_host_ready", return_value=False):
        caps = bg.probe_capabilities()
    assert caps["lipsync_public_host_ready"] is False
