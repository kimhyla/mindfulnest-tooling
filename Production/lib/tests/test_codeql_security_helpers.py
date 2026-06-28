"""Tests for lib/path_serve_security.py and lib/http_response_safety.py."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from lib.http_response_safety import safe_content_type, safe_etag_from_basename, safe_http_header_value
from lib.path_serve_security import reject_path_traversal_segments, require_basename_under_dir


def test_reject_path_traversal():
    with pytest.raises(ValueError):
        reject_path_traversal_segments("../etc/passwd")
    reject_path_traversal_segments("Production/Event_1/foo.mp4")


def test_require_basename_under_dir():
    with tempfile.TemporaryDirectory() as tmp:
        parent = Path(tmp)
        f = parent / "clip.mp4"
        f.write_bytes(b"x")
        got = require_basename_under_dir("clip.mp4", parent)
        assert got == f.resolve()
        with pytest.raises(ValueError):
            require_basename_under_dir("../evil.mp4", parent)


def test_safe_http_header_strips_crlf():
    assert "\r" not in safe_http_header_value("foo\r\nInject: yes")
    assert safe_http_header_value("video/mp4") == "video/mp4"


def test_safe_content_type_allowlist():
    assert safe_content_type("video/mp4") == "video/mp4"
    assert safe_content_type("text/html") == "application/octet-stream"


def test_safe_etag_from_basename():
    assert safe_etag_from_basename("clip.mp4") == '"clip.mp4"'
    assert "\r" not in safe_etag_from_basename("bad\r\nname.mp4")
