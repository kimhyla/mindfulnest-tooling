"""Trim persist must read milestone sidecar under scope lock — not torn Event SQLite."""
from __future__ import annotations

from pathlib import Path


BACKGROUND = Path(__file__).resolve().parent.parent / "server_handlers" / "background.py"


def _handler_block(name: str) -> str:
    text = BACKGROUND.read_text(encoding="utf-8")
    start = text.index(f"def {name}(")
    rest = text[start + 1 :]
    end_offset = len(rest)
    for marker in ("\ndef handle_", "\ndef _finalize", "\ndef _run_o3"):
        idx = rest.find(marker)
        if idx >= 0:
            end_offset = min(end_offset, idx)
    return text[start : start + 1 + end_offset]


def test_trim_persist_rebinds_scope_before_sidecar_read() -> None:
    block = _handler_block("handle_bg_kling_o3_trim")
    assert "production_bg_scope_lock()" in block
    assert "rebind_bg_paths_from_app(h.app)" in block
    assert "read_sidecar_for_poll_snapshot" in block
    assert "sidecar = bg.read_sidecar()" not in block.split("preview_only", 1)[1]
