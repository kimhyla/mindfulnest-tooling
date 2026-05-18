"""Unit tests for openai_image_edit_generate_end_frame (LD-730) — mocked HTTP only."""

from __future__ import annotations

import base64
import json
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TOOLING_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_TOOLING_REPO / "Production" / "tools"))

from kling_startend_pipeline import openai_image_edit_generate_end_frame  # noqa: E402

FAKE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)
INPUT_BYTES = b"\x89PNG\r\n\x1a\nfake-input-bytes"
END_PROMPT = "owl turns head slightly"
API_KEY = "sk-test-key"


def _mock_connection(
    *,
    status: int = 200,
    body: bytes | None = None,
    request_error: BaseException | None = None,
) -> MagicMock:
    conn = MagicMock()
    if request_error is not None:
        conn.request.side_effect = request_error
        return conn

    resp = MagicMock()
    resp.status = status
    if body is None:
        body = json.dumps({"data": [{"b64_json": base64.b64encode(FAKE_PNG).decode("ascii")}]}).encode(
            "utf-8"
        )
    resp.read.return_value = body
    conn.getresponse.return_value = resp
    return conn


@patch("http.client.HTTPSConnection")
def test_success_returns_png_bytes(mock_conn_cls: MagicMock) -> None:
    mock_conn_cls.return_value = _mock_connection()
    out = openai_image_edit_generate_end_frame(
        INPUT_BYTES, END_PROMPT, API_KEY, aspect_ratio="4:3", timeout_s=30
    )
    assert out == FAKE_PNG
    mock_conn_cls.assert_called_once()
    conn = mock_conn_cls.return_value
    conn.request.assert_called_once()
    assert conn.request.call_args[0][0] == "POST"
    assert conn.request.call_args[0][1] == "/v1/images/edits"


@patch("http.client.HTTPSConnection")
def test_http_4xx_raises_system_exit(mock_conn_cls: MagicMock) -> None:
    mock_conn_cls.return_value = _mock_connection(
        status=400,
        body=b'{"error":{"message":"bad request"}}',
    )
    with pytest.raises(SystemExit, match=r"HTTP 400"):
        openai_image_edit_generate_end_frame(INPUT_BYTES, END_PROMPT, API_KEY)


@patch("http.client.HTTPSConnection")
def test_http_5xx_raises_system_exit(mock_conn_cls: MagicMock) -> None:
    mock_conn_cls.return_value = _mock_connection(status=503, body=b"upstream error")
    with pytest.raises(SystemExit, match=r"HTTP 503"):
        openai_image_edit_generate_end_frame(INPUT_BYTES, END_PROMPT, API_KEY)


@patch("http.client.HTTPSConnection")
def test_timeout_raises_system_exit(mock_conn_cls: MagicMock) -> None:
    mock_conn_cls.return_value = _mock_connection(request_error=socket.timeout("timed out"))
    with pytest.raises(SystemExit, match=r"connection failed"):
        openai_image_edit_generate_end_frame(INPUT_BYTES, END_PROMPT, API_KEY)


@pytest.mark.parametrize(
    "aspect_ratio,expected_size",
    [
        ("3:4", "1024x1536"),
        ("portrait", "1024x1536"),
        ("1:1", "1024x1024"),
        ("square", "1024x1024"),
        ("4:3", "1536x1024"),
        ("landscape", "1536x1024"),
    ],
)
@patch("http.client.HTTPSConnection")
def test_aspect_ratio_maps_to_size_param(
    mock_conn_cls: MagicMock, aspect_ratio: str, expected_size: str
) -> None:
    mock_conn_cls.return_value = _mock_connection()
    openai_image_edit_generate_end_frame(
        INPUT_BYTES, END_PROMPT, API_KEY, aspect_ratio=aspect_ratio
    )
    body: bytes = mock_conn_cls.return_value.request.call_args[1]["body"]
    assert f'name="size"\r\n\r\n{expected_size}\r\n'.encode("utf-8") in body


@patch("http.client.HTTPSConnection")
def test_multipart_posts_edits_with_model_and_input_image(mock_conn_cls: MagicMock) -> None:
    mock_conn_cls.return_value = _mock_connection()
    openai_image_edit_generate_end_frame(INPUT_BYTES, END_PROMPT, API_KEY)
    conn = mock_conn_cls.return_value
    conn.request.assert_called_once()
    method, path, kwargs = conn.request.call_args[0][0], conn.request.call_args[0][1], conn.request.call_args[1]
    assert method == "POST"
    assert path == "/v1/images/edits"
    headers = kwargs["headers"]
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert "multipart/form-data" in headers["Content-Type"]
    body: bytes = kwargs["body"]
    assert b'name="model"\r\n\r\ngpt-image-1\r\n' in body
    assert b'name="quality"\r\n\r\nhigh\r\n' in body
    assert b'name="n"\r\n\r\n1\r\n' in body
    assert b'name="prompt"\r\n\r\n' + END_PROMPT.encode("utf-8") + b"\r\n" in body
    assert b'filename="start.png"\r\n' in body
    assert INPUT_BYTES in body
