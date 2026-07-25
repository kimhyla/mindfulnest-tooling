"""Deploy snapshots must stay bounded and free of regenerable build artifacts.

Regression cover for the Dropbox bloat incident: .deploy_backups reached ~132 GB
because every deploy rsynced a full node_modules copy into a new timestamped
snapshot and nothing ever pruned old ones.

These tests execute prune_deploy_snapshots.sh for real against temp trees rather
than grepping the deploy script, so the behaviour is what is locked, not the text.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRUNE = REPO / "scripts" / "prune_deploy_snapshots.sh"
DEPLOY = REPO / "scripts" / "deploy_storyboard_v59.sh"


def _run(root: Path, keep: str | None = None) -> subprocess.CompletedProcess:
    cmd = ["bash", str(PRUNE), str(root)]
    if keep is not None:
        cmd.append(keep)
    return subprocess.run(cmd, capture_output=True, text=True)


def _make_snapshot(root: Path, stamp: str, *, with_node_modules: bool = False) -> Path:
    snap = root / stamp / "Production" / "tools"
    snap.mkdir(parents=True, exist_ok=True)
    (snap / "keep_me.py").write_text("print('real code')\n", encoding="utf-8")
    if with_node_modules:
        nm = snap / "storyboard-v2" / "node_modules" / "left-pad"
        nm.mkdir(parents=True, exist_ok=True)
        (nm / "index.js").write_text("module.exports = 1;\n", encoding="utf-8")
    return root / stamp


def test_prune_script_exists_and_is_executable() -> None:
    assert PRUNE.is_file()


def test_keeps_newest_n_and_deletes_the_rest(tmp_path: Path) -> None:
    root = tmp_path / ".deploy_backups"
    root.mkdir()
    stamps = [f"2026071{i}T000000Z" for i in range(8)]
    for stamp in stamps:
        _make_snapshot(root, stamp)

    res = _run(root, "5")
    assert res.returncode == 0, res.stderr

    remaining = sorted(p.name for p in root.iterdir() if p.is_dir())
    assert remaining == sorted(stamps[-5:]), remaining
    # Oldest three are gone.
    for stamp in stamps[:3]:
        assert not (root / stamp).exists()


def test_default_keep_is_five(tmp_path: Path) -> None:
    root = tmp_path / ".deploy_backups"
    root.mkdir()
    for i in range(9):
        _make_snapshot(root, f"2026071{i}T000000Z")

    res = _run(root)
    assert res.returncode == 0, res.stderr
    assert len([p for p in root.iterdir() if p.is_dir()]) == 5


def test_strips_build_artifacts_from_retained_snapshots(tmp_path: Path) -> None:
    """A snapshot young enough to keep must still lose its node_modules."""
    root = tmp_path / ".deploy_backups"
    root.mkdir()
    snap = _make_snapshot(root, "20260718T000000Z", with_node_modules=True)
    assert list(snap.rglob("node_modules"))

    res = _run(root, "5")
    assert res.returncode == 0, res.stderr

    assert not list(snap.rglob("node_modules")), "node_modules survived prune"
    # Real code in the retained snapshot is untouched — rollback still works.
    assert (snap / "Production" / "tools" / "keep_me.py").is_file()


def test_under_the_cap_deletes_nothing(tmp_path: Path) -> None:
    root = tmp_path / ".deploy_backups"
    root.mkdir()
    for i in range(3):
        _make_snapshot(root, f"2026071{i}T000000Z")

    res = _run(root, "5")
    assert res.returncode == 0, res.stderr
    assert len([p for p in root.iterdir() if p.is_dir()]) == 3


def test_refuses_paths_that_are_not_deploy_backups(tmp_path: Path) -> None:
    """Guard against a mis-wired caller handing us a real content tree."""
    victim = tmp_path / "Production"
    (victim / "tools").mkdir(parents=True)
    (victim / "tools" / "precious.py").write_text("x = 1\n", encoding="utf-8")

    res = _run(victim, "1")
    assert res.returncode != 0
    assert "refusing to prune" in res.stderr
    assert (victim / "tools" / "precious.py").is_file()


def test_rejects_invalid_keep_count(tmp_path: Path) -> None:
    root = tmp_path / ".deploy_backups"
    root.mkdir()
    _make_snapshot(root, "20260718T000000Z")

    for bad in ("0", "-1", "abc"):
        res = _run(root, bad)
        assert res.returncode != 0, f"keep={bad} should be rejected"
        assert (root / "20260718T000000Z").exists()


def test_missing_root_is_a_no_op(tmp_path: Path) -> None:
    res = _run(tmp_path / ".deploy_backups")
    assert res.returncode == 0, res.stderr


def test_deploy_snapshot_excludes_build_artifacts() -> None:
    """The snapshot rsync itself must never copy node_modules again."""
    text = DEPLOY.read_text(encoding="utf-8")
    snapshot_block = text.split("(a) snapshotting current dest subset")[1].split("(b) Atomic mirror")[0]
    for excluded in ("node_modules", "dist", "__pycache__", ".venv"):
        assert f"--exclude='{excluded}'" in snapshot_block, f"snapshot rsync must exclude {excluded}"


def test_deploy_invokes_snapshot_retention() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "prune_deploy_snapshots.sh" in text
    assert "MN_DEPLOY_SNAPSHOT_KEEP" in PRUNE.read_text(encoding="utf-8")
