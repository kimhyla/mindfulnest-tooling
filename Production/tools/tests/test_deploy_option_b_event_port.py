"""STORYBOARD_OPTION_B_V1 — deploy uses dedicated event port, not hardcoded 5111."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "scripts" / "deploy_storyboard_v59.sh"
OPTION_B = REPO / "scripts" / "deploy_option_b.sh"
VERIFY = REPO / "scripts" / "verify_deploy_option_b_live.sh"
START = REPO / "scripts" / "start_event_server.sh"
POST = REPO / "scripts" / "post_tooling_change_smoke.sh"
SPEC = REPO / "docs" / "STORYBOARD_OPTION_B_SPEC_v1.md"


def test_option_b_spec_exists() -> None:
    assert SPEC.is_file()
    text = SPEC.read_text(encoding="utf-8")
    assert "deploy_option_b.sh" in text
    assert "Option B" in text


def test_deploy_option_b_entry_points_exist() -> None:
    assert OPTION_B.is_file()
    assert VERIFY.is_file()
    opt = OPTION_B.read_text(encoding="utf-8")
    assert "deploy_storyboard_v59.sh" in opt
    assert "verify_deploy_option_b_live.sh" in opt
    assert "STORYBOARD_OPTION_B_V1" in opt


def test_post_tooling_delegates_to_option_b() -> None:
    text = POST.read_text(encoding="utf-8")
    assert "deploy_option_b.sh" in text
    assert "rsync -a --delete" not in text


def test_deploy_uses_dedicated_port_not_global_pkill() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "event_server_port.sh" in text
    assert "event_id_to_port" in text
    assert "ensure_server_port.sh" in text
    assert "install_production_server_launchagent.sh" in text
    assert "pkill -f \"production_server.py\"" not in text


def test_dirty_gate_ignores_local_runtime_artifacts() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "Production/.production_snapshots/" in text
    assert "doppler.env" in text


def test_start_event_server_uses_dropbox_runtime() -> None:
    text = START.read_text(encoding="utf-8")
    assert "DROPBOX" in text and "install_production_server_launchagent.sh" in text
    assert "ensure_server_port.sh" in text
    assert "SERVER_LAUNCHD_SINGLE_OWNER_V1" in text


def test_deploy_sha256_verify_uses_git_head_not_working_tree() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert 'git -C "$SRC_TOOLING" show "HEAD:${f}"' in text
    assert "Dropbox sync lag" in text


def test_event_canonical_module_skips_unpinned_events() -> None:
    text = (REPO / "scripts" / "verify_event_canonical_module.sh").read_text(encoding="utf-8")
    assert "SKIP" in text
    assert "optional until stitch bake final" in text


def test_smoke_per_event_library_uses_dedicated_port() -> None:
    text = (REPO / "scripts" / "smoke_per_event_library.sh").read_text(encoding="utf-8")
    assert "event_server_port.sh" in text
    assert "MN_SERVER_PORT" in text


def test_deploy_waits_for_launchd_after_sync() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "launchd server ready" in text
    assert "install_production_server_launchagent.sh" in text


def test_verify_option_b_checks_build_sha_and_parity() -> None:
    text = VERIFY.read_text(encoding="utf-8")
    assert "verify_tooling_dropbox_parity.py" in text
    assert "build-sha" in text
    assert "app-build-sha" in text
    assert "event/load" in text
    # Minified bundle uses {"data-testid":"app-build-sha"} — not HTML attr quotes.
    assert 'data-testid["' in text or "data-testid" in text and "re.compile" in text


def test_verify_option_b_app_build_sha_matches_minified_bundle() -> None:
    import re

    dist = REPO / "tools" / "storyboard-v2" / "dist" / "index.html"
    if not dist.is_file():
        return
    html = dist.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(r'data-testid["\']?\s*[=:]\s*["\']app-build-sha["\']')
    assert pat.search(html), "dist bundle must wire app-build-sha marker for Option B verify"
