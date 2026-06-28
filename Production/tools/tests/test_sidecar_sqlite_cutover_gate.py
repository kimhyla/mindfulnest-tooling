"""P4/P6 cutover contracts — SQLite authority + legacy flock isolation."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_BG = _ROOT / "beat_generator.py"


def _fn_body(name: str) -> str:
    text = _BG.read_text(encoding="utf-8")
    return text.split(f"def {name}", 1)[1].split("\ndef ", 1)[0]


def test_sidecar_file_lock_has_no_fcntl_when_sqlite_branch_first():
    body = _fn_body("sidecar_file_lock")
    assert "sqlite_authority_enabled()" in body
    sqlite_idx = body.index("if sqlite_authority_enabled()")
    assert "fcntl.flock" not in body[: sqlite_idx + 400]


def test_legacy_json_lock_holds_fcntl():
    body = _fn_body("_legacy_json_sidecar_file_lock")
    assert "fcntl.flock" in body


def test_write_sidecar_routes_sqlite_to_store():
    body = _fn_body("write_sidecar")
    unlocked = _fn_body("_write_sidecar_unlocked")
    assert "_sidecar_use_sqlite()" in body or "_sidecar_use_sqlite()" in unlocked
    assert "replace_full" in unlocked


def test_cleanup_stale_lock_on_sqlite_init():
    text = _BG.read_text(encoding="utf-8")
    assert "_cleanup_stale_dropbox_sidecar_lock_file" in text
    cold = _fn_body("_run_bg_paths_cold_boot")
    assert "_cleanup_stale_dropbox_sidecar_lock_file()" in cold
