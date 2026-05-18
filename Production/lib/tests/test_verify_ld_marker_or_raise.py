"""Unit tests for Production/lib/directus.py — verify_ld_marker_or_raise gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO / "Production" / "lib"))

from directus import (  # noqa: E402
    FabricationGateError,
    _resolve_tooling_root,
    verify_ld_marker_or_raise,
)


@pytest.fixture
def tooling_root() -> Path:
    root = _resolve_tooling_root()
    assert root is not None, "expected mindfulnest-tooling git repo"
    return root


def test_present_marker_passes_and_strips_gate_fields(tooling_root: Path) -> None:
    payload = {
        "decision_key": "TEST_GATE_PRESENT",
        "marker_string": "verify_ld_marker_or_raise",
        "marker_regex": False,
        "decision_name": "gate unit test",
    }
    clean = verify_ld_marker_or_raise(payload)
    assert "marker_string" not in clean
    assert "marker_regex" not in clean
    assert clean["decision_key"] == "TEST_GATE_PRESENT"
    assert clean["decision_name"] == "gate unit test"


def test_absent_marker_raises_fabrication_gate_error(tooling_root: Path) -> None:
    marker = "__MN_LD_GATE_ABSENT_MARKER_UNIT_TEST_XYZ__"
    payload = {
        "decision_key": "TEST_GATE_ABSENT",
        "marker_string": marker,
    }
    with pytest.raises(FabricationGateError) as exc_info:
        verify_ld_marker_or_raise(payload)
    err = exc_info.value
    assert err.decision_key == "TEST_GATE_ABSENT"
    assert err.marker == marker
    assert err.kind == "literal"
    assert str(tooling_root) in err.tooling_root


def test_worktree_only_marker_still_raises(tooling_root: Path) -> None:
    marker = "__MN_LD_GATE_WORKTREE_ONLY_MARKER_UNIT_TEST__"
    probe = tooling_root / "Production" / "lib" / "tests" / ".gate_worktree_probe_only"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(f"# probe\n{marker}\n", encoding="utf-8")
    try:
        # Uncommitted file must not satisfy HEAD-bound gate.
        in_head = subprocess.run(
            ["git", "grep", "-c", "-F", marker, "HEAD"],
            cwd=str(tooling_root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert in_head.returncode != 0, "probe marker must be absent from HEAD for this test"
        payload = {"decision_key": "TEST_GATE_WORKTREE", "marker_string": marker}
        with pytest.raises(FabricationGateError) as exc_info:
            verify_ld_marker_or_raise(payload)
        assert exc_info.value.marker == marker
    finally:
        if probe.exists():
            probe.unlink()


def test_regex_marker_matches_committed_functions(tooling_root: Path) -> None:
    payload = {
        "decision_key": "TEST_GATE_REGEX",
        "marker_string": r"def \w+",
        "marker_regex": True,
    }
    clean = verify_ld_marker_or_raise(payload)
    assert "marker_string" not in clean


def test_bypass_env_skips_absent_marker(
    monkeypatch: pytest.MonkeyPatch, tooling_root: Path
) -> None:
    monkeypatch.setenv("MN_SKIP_LD_MARKER_GATE", "1")
    payload = {
        "decision_key": "TEST_GATE_BYPASS",
        "marker_string": "__MN_LD_GATE_BYPASS_SHOULD_NOT_EXIST__",
    }
    clean = verify_ld_marker_or_raise(payload)
    assert clean["decision_key"] == "TEST_GATE_BYPASS"
    assert "marker_string" not in clean


def test_empty_marker_string_is_no_op() -> None:
    payload = {
        "decision_key": "TEST_GATE_EMPTY",
        "marker_string": "",
        "decision_name": "unchanged",
    }
    out = verify_ld_marker_or_raise(payload)
    assert out["decision_key"] == "TEST_GATE_EMPTY"
    assert out["decision_name"] == "unchanged"
    assert "marker_string" not in out
