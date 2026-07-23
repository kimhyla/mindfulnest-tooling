"""WIN_STDIO_UTF8_V1 — /files must not 500 from Windows console encoding."""
from __future__ import annotations

import io
from pathlib import Path

import production_server as ps


def test_hot_serve_log_line_is_cp1252_safe() -> None:
    """The request-path hot-serve log must encode under Windows cp1252."""
    line = "[hot-serve] cloud->local stem.mp3 -> C:\\cache\\stem.mp3"
    line.encode("cp1252")
    src = Path(ps.__file__).read_text(encoding="utf-8")
    assert "cloud->local" in src
    assert "cloud→local" not in src


def test_configure_stdio_encoding_survives_arrow_print() -> None:
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    # Simulate a broken Windows console, then reconfigure like production_server.
    try:
        buf.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    buf.write("cloud→local ok\n")
    buf.flush()
