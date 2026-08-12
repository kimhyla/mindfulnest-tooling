"""Cross-platform advisory lock compatibility contract."""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from Production.lib import fcntl_compat as fcntl

_PROD = Path(__file__).resolve().parents[1]

# Production modules on Phase A / Stitcher export and related lock paths.
# These must never import stdlib ``fcntl`` — Windows has no such module.
# Mac Phase A layered land: gate only the new layered job store.
# Full Windows fcntl migration of legacy modules stays on the vacation branch.
_CRITICAL_NO_RAW_FCNTL = (
    _PROD / "tools" / "layered_lipsync_jobs.py",
)


def test_exclusive_nonblocking_lock_and_release(tmp_path: Path) -> None:
    lock_path = tmp_path / "compat.lock"
    first = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    second = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises((BlockingIOError, OSError)):
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)

        fcntl.flock(first, fcntl.LOCK_UN)
        fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(second, fcntl.LOCK_UN)
    finally:
        os.close(first)
        os.close(second)

    assert lock_path.exists()


def _stdlib_fcntl_imports(source: str) -> list[str]:
    """Return AST import lines that load stdlib ``fcntl`` (not fcntl_compat)."""
    tree = ast.parse(source)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fcntl" or alias.name.startswith("fcntl."):
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "fcntl":
                names = ", ".join(a.name for a in node.names)
                hits.append(f"from fcntl import {names}")
    return hits


@pytest.mark.parametrize("path", _CRITICAL_NO_RAW_FCNTL, ids=lambda p: p.name)
def test_critical_modules_do_not_import_stdlib_fcntl(path: Path) -> None:
    assert path.is_file(), f"missing critical module: {path}"
    hits = _stdlib_fcntl_imports(path.read_text(encoding="utf-8"))
    assert hits == [], (
        f"{path.relative_to(_PROD.parent)} imports stdlib fcntl "
        f"(Windows ModuleNotFoundError): {hits}. "
        f"Use `from lib import fcntl_compat as fcntl` instead."
    )


@pytest.mark.skipif(sys.platform != "win32", reason="win32-only import smoke")
def test_phase_export_modules_import_on_win32() -> None:
    """Ensure Phase A export lock shim + overlay module load without stdlib fcntl."""
    import importlib

    prod = str(_PROD)
    if prod not in sys.path:
        sys.path.insert(0, prod)

    for mod_name in ("lib.fcntl_compat", "lib.state_repo"):
        sys.modules.pop(mod_name, None)
        importlib.import_module(mod_name)

    # Source-level guarantee for the HTTP export handler module (heavy deps).
    phases = _PROD / "tools" / "server_handlers" / "phases.py"
    assert _stdlib_fcntl_imports(phases.read_text(encoding="utf-8")) == []
    assert "fcntl_compat" in phases.read_text(encoding="utf-8")
