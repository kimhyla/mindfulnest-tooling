#!/usr/bin/env python3
"""Offline coverage for Production/tools/lipsync_sender.py.

task_id = LD-260-pytest-3-pipeline-scripts-20260418
preflight = 72
LD coverage = LD-260 PIPELINE_PYTEST_3_CRITICAL_SCRIPTS.

Scope: import surface, pure-function behavior (lipsync_poll_url,
_build_multipart, file_to_data_uri). No WaveSpeed, no catbox, no ffmpeg.
"""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


class LipsyncSenderImportTests(unittest.TestCase):
    """Module must import cleanly."""

    def test_module_imports(self) -> None:
        import lipsync_sender  # noqa: F401
        self.assertTrue(hasattr(lipsync_sender, "LipSyncClient"))
        self.assertTrue(hasattr(lipsync_sender, "lipsync_poll_url"))
        self.assertTrue(hasattr(lipsync_sender, "file_to_data_uri"))
        self.assertTrue(hasattr(lipsync_sender, "_build_multipart"))


class LipsyncPollUrlTests(unittest.TestCase):
    """lipsync_poll_url concatenates the shared predictions base with /{id}/result."""

    def test_url_shape(self) -> None:
        import lipsync_sender
        url = lipsync_sender.lipsync_poll_url("abc123")
        self.assertTrue(url.startswith(lipsync_sender.PREDICTIONS_POLL_BASE))
        self.assertTrue(url.endswith("/abc123/result"))

    def test_different_ids_produce_different_urls(self) -> None:
        import lipsync_sender
        a = lipsync_sender.lipsync_poll_url("job-a")
        b = lipsync_sender.lipsync_poll_url("job-b")
        self.assertNotEqual(a, b)


class BuildMultipartTests(unittest.TestCase):
    """_build_multipart produces a valid body + content-type header."""

    def test_fields_only(self) -> None:
        import lipsync_sender
        body, ctype = lipsync_sender._build_multipart({"foo": "bar", "baz": "qux"}, {})
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="foo"', body)
        self.assertIn(b"bar", body)
        self.assertIn(b'name="baz"', body)
        self.assertIn(b"qux", body)
        # Body must end with closing boundary token
        boundary = ctype.split("boundary=", 1)[1]
        self.assertIn(f"--{boundary}--".encode(), body)

    def test_file_embedded(self) -> None:
        import lipsync_sender
        payload = b"PNGfakebytes\x00\x01\x02"
        body, ctype = lipsync_sender._build_multipart(
            {"meta": "value"},
            {"image": ("pic.png", payload, "image/png")},
        )
        self.assertIn(payload, body)
        self.assertIn(b'filename="pic.png"', body)
        self.assertIn(b"Content-Type: image/png", body)


class FileToDataUriTests(unittest.TestCase):
    """file_to_data_uri base64-encodes file contents with the given mime."""

    def test_roundtrip(self) -> None:
        import tempfile
        import lipsync_sender

        payload = b"\x00\x01\x02hello-lipsync"
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        try:
            uri = lipsync_sender.file_to_data_uri(tmp_path, "application/octet-stream")
            self.assertTrue(uri.startswith("data:application/octet-stream;base64,"))
            decoded = base64.b64decode(uri.split(",", 1)[1])
            self.assertEqual(decoded, payload)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
