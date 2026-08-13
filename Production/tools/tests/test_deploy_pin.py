"""DEPLOY_PIN_V1 — frozen sha survives checkout theft; Python-only skips fleet."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from deploy_pin import (
    MARKER,
    bundle_source_changed,
    git_bundle_paths_changed,
    path_is_bundle_source,
    pin_file_for,
    read_html_build_sha,
    resolve_expect_sha,
    write_pin,
)

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "Production" / "scripts"
DEPLOY = SCRIPTS / "deploy_storyboard_v59.sh"
OPTION_B = SCRIPTS / "deploy_option_b.sh"
VERIFY = SCRIPTS / "verify_deploy_option_b_live.sh"
FLEET_PARITY = SCRIPTS / "verify_storyboard_fleet_bundle_parity.sh"
LAUNCHAGENT_DURABILITY = SCRIPTS / "verify_production_server_launchagent_durability.sh"
INSTALL = SCRIPTS / "install_production_server_launchagent.sh"
SERVER = REPO / "Production" / "tools" / "production_server.py"


def test_marker_present() -> None:
    assert MARKER == "DEPLOY_PIN_V1"


def test_resolve_expect_sha_frozen_when_checkout_moves() -> None:
    """Tonight's fake parity: live HEAD became 5f7f44ba while fleet served c9b3bd8b."""
    sha = resolve_expect_sha(
        env={"MN_EXPECT_BUILD_SHA": "c9b3bd8b"},
        pin_path=None,
        git_head="5f7f44ba",
    )
    assert sha == "c9b3bd8b"


def test_resolve_expect_sha_pin_file_beats_later_head(tmp_path: Path) -> None:
    pin = tmp_path / ".deploy_pin"
    write_pin(pin, "c9b3bd8b")
    sha = resolve_expect_sha(env={}, pin_path=pin, git_head="5f7f44ba")
    assert sha == "c9b3bd8b"


def test_resolve_expect_sha_env_beats_pin_file(tmp_path: Path) -> None:
    pin = tmp_path / ".deploy_pin"
    write_pin(pin, "oldpin01")
    sha = resolve_expect_sha(
        env={"MN_DEPLOY_PINNED_SHA": "c9b3bd8b"},
        pin_path=pin,
        git_head="5f7f44ba",
    )
    assert sha == "c9b3bd8b"


def test_resolve_expect_sha_falls_back_to_head_when_no_pin() -> None:
    sha = resolve_expect_sha(env={}, pin_path=None, git_head="e1231350")
    assert sha == "e1231350"


def test_bundle_source_changed_python_only_is_false() -> None:
    paths = [
        "Production/tools/server_handlers/background.py",
        "Production/scripts/deploy_storyboard_v59.sh",
        "Production/tools/tests/test_o3_trim_handler_event_dir_bind.py",
    ]
    assert bundle_source_changed(paths) is False


def test_bundle_source_changed_tsx_is_true() -> None:
    paths = [
        "Production/tools/server_handlers/background.py",
        "Production/tools/storyboard-v2/src/components/BgTab.tsx",
    ]
    assert bundle_source_changed(paths) is True


def test_path_is_bundle_source_ignores_e2e_and_counts_src() -> None:
    assert path_is_bundle_source(
        "Production/tools/storyboard-v2/src/state/buildShaDrift.ts"
    )
    assert not path_is_bundle_source(
        "Production/tools/storyboard-v2/e2e/phase_e_hydrate_live.spec.ts"
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "tooling"
    src = repo / "Production" / "tools" / "storyboard-v2" / "src"
    py = repo / "Production" / "tools"
    src.mkdir(parents=True)
    py.mkdir(parents=True, exist_ok=True)
    (src / "App.tsx").write_text("export const n = 1;\n", encoding="utf-8")
    (py / "handler.py").write_text("x = 1\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    return repo


def _commit(repo: Path, message: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True
    ).strip()


def test_git_bundle_paths_changed_python_only(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True
    ).strip()
    (repo / "Production" / "tools" / "handler.py").write_text("x = 2\n", encoding="utf-8")
    pin = _commit(repo, "python only")
    assert git_bundle_paths_changed(repo, base, pin) is False


def test_git_bundle_paths_changed_tsx(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True
    ).strip()
    app = repo / "Production" / "tools" / "storyboard-v2" / "src" / "App.tsx"
    app.write_text("export const n = 2;\n", encoding="utf-8")
    pin = _commit(repo, "ui")
    assert git_bundle_paths_changed(repo, base, pin) is True


def test_git_bundle_paths_changed_unknown_live_sha_is_safe_restart(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    pin = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True
    ).strip()
    assert git_bundle_paths_changed(repo, "deadbeef", pin) is True


def test_verify_option_b_does_not_reread_live_head() -> None:
    text = VERIFY.read_text(encoding="utf-8")
    assert "deploy_pin.py" in text
    assert "MN_EXPECT_BUILD_SHA" in text
    assert 'HEAD_SHA="$(cd "$SRC_TOOLING" && git rev-parse --short HEAD)"' not in text


def test_option_b_captures_pin_before_deploy() -> None:
    text = OPTION_B.read_text(encoding="utf-8")
    assert "deploy_pin.py" in text
    assert "capture" in text
    cap_at = text.find("deploy_pin.py")
    deploy_at = text.find("deploy_storyboard_v59.sh")
    assert 0 <= cap_at < deploy_at


def test_deploy_pins_sha_before_build_and_skips_fleet_when_unchanged() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "DEPLOY_PIN_V1" in text
    assert "STORYBOARD_FLEET_RESTART_SKIP_WHEN_BUNDLE_UNCHANGED_V1" in text
    assert "deploy_pin.py" in text
    pin_at = text.find("deploy_pin.py")
    build_at = text.find("npm run build")
    fleet_at = text.find("restart_storyboard_fleet.sh")
    assert 0 <= pin_at < build_at < fleet_at
    assert "MN_DEPLOY_SKIP_FLEET_RESTART" in text
    assert ".deploy_pin" in text


def test_fleet_parity_can_scope_live_ports_to_target() -> None:
    text = FLEET_PARITY.read_text(encoding="utf-8")
    assert "MN_FLEET_PARITY_LIVE_EVENTS" in text
    assert "deploy_pin.py" in text
    assert 'git -C "$ROOT" rev-parse --short HEAD' not in text


def test_server_tooling_sha_prefers_pinned_env() -> None:
    text = SERVER.read_text(encoding="utf-8")
    assert "MN_EXPECT_BUILD_SHA" in text


def test_launchagent_writes_pinned_sha() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert "MN_EXPECT_BUILD_SHA" in text


def test_launchagent_durability_allows_python_only_fleet_skip() -> None:
    text = LAUNCHAGENT_DURABILITY.read_text(encoding="utf-8")
    assert "STORYBOARD_FLEET_RESTART_SKIP_WHEN_BUNDLE_UNCHANGED_V1" in text


def test_pin_file_helper() -> None:
    assert pin_file_for(REPO).name == ".deploy_pin"


def test_read_html_build_sha(tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text(
        '<html><head><meta name="build-sha" content="c9b3bd8b"></head></html>',
        encoding="utf-8",
    )
    assert read_html_build_sha(html) == "c9b3bd8b"
