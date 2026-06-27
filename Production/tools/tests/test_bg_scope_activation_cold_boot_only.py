"""BG_SCOPE_ACTIVATION_COLD_BOOT_ONLY_V1 — warm init must not re-reconcile under lock."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import beat_generator as bg
from server_handlers import milestone_scope as ms

TOOLS = Path(__file__).resolve().parent.parent
BG = TOOLS / "beat_generator.py"
MILESTONE_SCOPE = TOOLS / "server_handlers" / "milestone_scope.py"


def _fn_body(name: str) -> str:
    text = BG.read_text(encoding="utf-8")
    return text.split(f"def {name}", 1)[1].split("\ndef ", 1)[0]


def test_init_bg_paths_warm_skips_cold_boot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    bg.reset_bg_paths_activation_for_tests()
    event_dir = tmp_path / "Event_9"
    event_dir.mkdir()
    calls = {"n": 0}

    def _fake_cold(_event_dir) -> None:
        calls["n"] += 1

    with patch.object(bg, "_run_bg_paths_cold_boot", side_effect=_fake_cold):
        bg.init_bg_paths(event_dir)
        bg.init_bg_paths(event_dir)
        bg.init_bg_paths(event_dir)

    assert calls["n"] == 1


def test_init_bg_paths_cold_boot_on_scope_change(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    bg.reset_bg_paths_activation_for_tests()
    ev2 = tmp_path / "Event_2"
    ev3 = tmp_path / "Event_3"
    ev2.mkdir()
    ev3.mkdir()
    calls = {"n": 0}

    def _fake_cold(_event_dir) -> None:
        calls["n"] += 1

    with patch.object(bg, "_run_bg_paths_cold_boot", side_effect=_fake_cold):
        bg.init_bg_paths(ev2)
        bg.init_bg_paths(ev2)
        bg.init_bg_paths(ev3)

    assert calls["n"] == 2


def test_init_bg_paths_cold_boot_forced_reruns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    bg.reset_bg_paths_activation_for_tests()
    event_dir = tmp_path / "Event_2"
    event_dir.mkdir()
    calls = {"n": 0}

    def _fake_cold(_event_dir) -> None:
        calls["n"] += 1

    with patch.object(bg, "_run_bg_paths_cold_boot", side_effect=_fake_cold):
        bg.init_bg_paths(event_dir)
        bg.init_bg_paths(event_dir, cold_boot=True)

    assert calls["n"] == 2


def test_warm_init_skips_mirror_reconcile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    bg.reset_bg_paths_activation_for_tests()
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    reconcile_calls = {"n": 0}

    def _fake_reconcile(_event_dir) -> dict:
        reconcile_calls["n"] += 1
        return {}

    with patch.object(bg, "reconcile_sqlite_segment_beats_from_json_mirror", side_effect=_fake_reconcile):
        with patch.object(bg, "bootstrap_sqlite_sidecar_from_json", return_value=0):
            with patch.object(bg, "bootstrap_sqlite_from_legacy_global_db", return_value=0):
                with patch.object(bg, "_cleanup_stale_dropbox_sidecar_lock_file"):
                    with patch.object(bg, "_sidecar_use_sqlite", return_value=False):
                        bg.init_bg_paths(event_dir)
                        bg.init_bg_paths(event_dir)

    assert reconcile_calls["n"] == 1


def test_init_unlocked_has_warm_scope_early_return() -> None:
    body = _fn_body("_init_bg_paths_unlocked")
    assert "_BG_ACTIVE_SCOPE_KEY" in body
    assert "_run_bg_paths_cold_boot" in body
    assert "scope_key = _compute_bg_scope_key" in body


def test_cold_boot_extracted_from_init_unlocked() -> None:
    text = BG.read_text(encoding="utf-8")
    assert "def _run_bg_paths_cold_boot" in text
    init = _fn_body("_init_bg_paths_unlocked")
    assert "reconcile_sqlite_segment_beats_from_json_mirror" not in init
    cold = _fn_body("_run_bg_paths_cold_boot")
    assert "reconcile_sqlite_segment_beats_from_json_mirror" in cold


def test_activate_bg_for_scope_uses_init_bg_paths_only() -> None:
    block = MILESTONE_SCOPE.read_text(encoding="utf-8").split(
        "def activate_bg_for_scope", 1
    )[1].split("\ndef assert_production_scope", 1)[0]
    assert "init_bg_paths" in block
    assert "reconcile_sqlite_segment_beats_from_json_mirror" not in block
