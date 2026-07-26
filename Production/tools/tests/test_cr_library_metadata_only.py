#!/usr/bin/env python3
"""GET /api/cr/library is metadata-only; thumbs via GET /api/cr/thumb."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))
sys.path.insert(0, str(TOOLS))

from Production.tools.server_handlers import cropper  # noqa: E402

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
    b"\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x1d\xf3\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Many tiny rows — inline thumbs would blow past this bound.
_MAX_LIST_JSON_BYTES = 120_000


class _CaptureHandler:
    def __init__(self, app, path: str = "/api/cr/library"):
        self.app = app
        self.path = path
        self.status = None
        self.payload = None
        self.body_bytes = None
        self.content_type = None
        self.headers = None

    def _send_json(self, status, payload):
        self.status = status
        self.payload = payload

    def _send_error_v59(self, status, **kwargs):
        self.status = status
        self.payload = kwargs

    def _send_bytes(self, status, body, content_type, extra_headers=None):
        self.status = status
        self.body_bytes = body
        self.content_type = content_type
        self.headers = extra_headers or {}

    def _scope_body(self, body):
        return body or {}

    def _check_event_pin(self, pin, label):
        return True

    def _assert_event_scope(self, scope, allow_missing=False, allow_missing_video_role=False):
        return True


def _event_app(prod: Path) -> tuple[Path, MagicMock]:
    ev = prod / "Event_1"
    src = ev / "library" / "images" / "sources"
    src.mkdir(parents=True)
    app = MagicMock()
    app.event_dir = ev
    app.event_id = "Event_1"
    app.event_generation = 1
    app.scope_type = "event"
    app.active_milestone_id = None
    return ev, app


class CrLibraryMetadataOnlyTests(unittest.TestCase):
    def test_library_list_has_no_inline_thumbs_and_is_small(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev, app = _event_app(prod)
            src = ev / "library" / "images" / "sources"
            for i in range(40):
                (src / f"meta_only_{i:02d}.png").write_bytes(_MIN_PNG)

            h = _CaptureHandler(app)
            cropper.handle_cr_library(h)

            self.assertEqual(h.status, 200)
            payload = h.payload or {}
            self.assertTrue(payload.get("metadata_only"))
            images = payload.get("images") or []
            self.assertGreaterEqual(len(images), 40)
            for img in images:
                self.assertNotIn("thumb_b64", img)
                self.assertNotIn("gallery_b64", img)
                if img.get("abs_path"):
                    self.assertIn("thumb_url", img)
                    self.assertIn("/api/cr/thumb", img["thumb_url"])

            raw = json.dumps(payload).encode("utf-8")
            self.assertLess(
                len(raw),
                _MAX_LIST_JSON_BYTES,
                f"list JSON {len(raw)} bytes exceeds {_MAX_LIST_JSON_BYTES}",
            )

    def test_cr_thumb_returns_jpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev, app = _event_app(prod)
            fp = ev / "library" / "images" / "sources" / "thumb_target.png"
            fp.write_bytes(_MIN_PNG)
            import urllib.parse
            from unittest.mock import patch

            q = urllib.parse.quote(str(fp), safe="")
            h = _CaptureHandler(app, f"/api/cr/thumb?abs_path={q}")
            with patch.object(
                cropper,
                "require_realpath_under_project",
                side_effect=lambda p: os.path.realpath(p),
            ):
                cropper.handle_cr_thumb(h)

            self.assertEqual(h.status, 200, h.payload)
            self.assertEqual(h.content_type, "image/jpeg")
            self.assertTrue(h.body_bytes and h.body_bytes[:2] == b"\xff\xd8")

    def test_cr_thumb_hot_serves_before_decode_when_dropbox_deadlocks(self):
        """CR_THUMB_HOT_SERVE_V1 — errno 11 on Dropbox master still yields JPEG."""
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev, app = _event_app(prod)
            fp = ev / "library" / "images" / "sources" / "cloudish.png"
            fp.write_bytes(_MIN_PNG)
            local = Path(tmp) / "local_hot.png"
            local.write_bytes(_MIN_PNG)
            import urllib.parse
            from unittest.mock import patch

            q = urllib.parse.quote(str(fp), safe="")
            h = _CaptureHandler(app, f"/api/cr/thumb?abs_path={q}")

            def _deadlock_open(path, *a, **kw):
                if os.path.realpath(str(path)) == os.path.realpath(str(fp)):
                    raise OSError(11, "Resource deadlock avoided")
                return open(path, *a, **kw)

            with patch.object(
                cropper,
                "require_realpath_under_project",
                side_effect=lambda p: os.path.realpath(p),
            ), patch(
                "media_playback_cache.ensure_hot_serve_file",
                return_value=local,
            ):
                cropper.handle_cr_thumb(h)

            self.assertEqual(h.status, 200, h.payload)
            self.assertEqual(h.content_type, "image/jpeg")
            self.assertTrue(h.body_bytes and h.body_bytes[:2] == b"\xff\xd8")

    def test_cr_thumb_materialize_failed_maps_503(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev, app = _event_app(prod)
            fp = ev / "library" / "images" / "sources" / "busy.png"
            fp.write_bytes(_MIN_PNG)
            import urllib.parse
            from unittest.mock import patch

            q = urllib.parse.quote(str(fp), safe="")
            h = _CaptureHandler(app, f"/api/cr/thumb?abs_path={q}")
            with patch.object(
                cropper,
                "require_realpath_under_project",
                side_effect=lambda p: os.path.realpath(p),
            ), patch(
                "media_playback_cache.ensure_hot_serve_file",
                side_effect=OSError(11, "Resource deadlock avoided"),
            ):
                cropper.handle_cr_thumb(h)

            self.assertEqual(h.status, 503, h.payload)
            self.assertEqual(
                (h.payload or {}).get("error_code"),
                "THUMB_MATERIALIZE_FAILED",
            )


if __name__ == "__main__":
    unittest.main()
