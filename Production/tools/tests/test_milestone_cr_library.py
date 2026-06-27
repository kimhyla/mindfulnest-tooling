#!/usr/bin/env python3
"""Milestone library CR handlers use skeleton library_event_dir (same as events)."""
from __future__ import annotations

import base64
import json
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


class _CaptureHandler:
    def __init__(self, app, path: str = "/api/cr/library"):
        self.app = app
        self.path = path
        self.status = None
        self.payload = None

    def _send_json(self, status, payload):
        self.status = status
        self.payload = payload

    def _send_error_v59(self, status, **kwargs):
        self.status = status
        self.payload = kwargs

    def _scope_body(self, body):
        return body or {}

    def _check_event_pin(self, pin, label):
        return True

    def _assert_event_scope(self, scope, allow_missing=False, allow_missing_video_role=False):
        return True


def _milestone_fixture(prod: Path):
    ev2 = prod / "Event_2"
    ev1 = prod / "Event_1"
    mdir = prod / "Milestones" / "milestone1_arc1"
    src1 = ev1 / "library" / "images" / "sources"
    src2 = ev2 / "library" / "images" / "sources"
    src1.mkdir(parents=True)
    src2.mkdir(parents=True)
    mdir.mkdir(parents=True)
    (mdir / "state.json").write_text(
        json.dumps({
            "milestone_id": "milestone1_arc1",
            "milestone_label": "Oliver enters",
            "active_video": "standalone",
            "videos": {"standalone": {"beats": {}, "display_order": []}},
        }),
        encoding="utf-8",
    )
    app = MagicMock()
    app.event_dir = ev2
    app.event_id = "Event_2"
    app.event_generation = 1
    app.scope_type = "milestone"
    app.active_milestone_id = "milestone1_arc1"
    return ev1, ev2, mdir, app


class MilestoneCrLibraryTests(unittest.TestCase):
    def test_library_lists_upload_on_skeleton_library_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev1, ev2, _mdir, app = _milestone_fixture(prod)
            src1 = ev1 / "library" / "images" / "sources"
            src2 = ev2 / "library" / "images" / "sources"
            upload_name = "milestone_only_upload.png"
            (src1 / upload_name).write_bytes(_MIN_PNG)
            (src2 / "pinned_event_only.png").write_bytes(_MIN_PNG)

            h = _CaptureHandler(app, "/api/cr/library?scope_milestone_id=milestone1_arc1")
            cropper.handle_cr_library(h)

            self.assertEqual(h.status, 200)
            self.assertTrue((h.payload or {}).get("metadata_only"))
            images = (h.payload or {}).get("images") or []
            filenames = {img.get("filename") for img in images if img.get("tier") == "source"}
            self.assertIn(upload_name, filenames)
            self.assertNotIn("pinned_event_only.png", filenames)
            self.assertEqual(h.payload.get("library_event_id"), "Event_1")
            for img in images:
                self.assertNotIn("thumb_b64", img)
                if img.get("abs_path"):
                    self.assertIn("thumb_url", img)

    def test_milestone_cr_upload_writes_to_skeleton_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev1, ev2, _mdir, app = _milestone_fixture(prod)
            upload_name = "milestone_manual_add.png"
            body = {
                "scope_milestone_id": "milestone1_arc1",
                "filename": upload_name,
                "image_b64": base64.b64encode(_MIN_PNG).decode(),
                "tier": "source",
            }
            h = _CaptureHandler(app)
            cropper.handle_cr_upload(h, body)

            self.assertEqual(h.status, 200, h.payload)
            dest = ev1 / "library" / "images" / "sources" / upload_name
            wrong = ev2 / "library" / "images" / "sources" / upload_name
            self.assertTrue(dest.is_file(), f"expected upload at {dest}")
            self.assertFalse(wrong.is_file(), f"upload must not land on pinned event {wrong}")

    def test_library_excludes_canonical_registry_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev1 = prod / "Event_1"
            src = ev1 / "library" / "images" / "sources"
            src.mkdir(parents=True)
            can_dir = prod / "canonical_images"
            can_dir.mkdir(parents=True)
            can_name = "canonical_arlo_mirror_v1.png"
            (can_dir / can_name).write_bytes(_MIN_PNG)
            (prod / "canonical_image_registry.json").write_text(
                json.dumps({
                    "arcs": {
                        "1": {
                            "images": [{
                                "key": "canonical_arlo_mirror_v1",
                                "filename": can_name,
                                "display_name": "Arlo mirror",
                            }],
                        },
                    },
                }),
                encoding="utf-8",
            )
            app = MagicMock()
            app.event_dir = ev1
            app.event_id = "Event_1"
            app.event_generation = 1
            app.scope_type = "event"
            app.active_milestone_id = None

            h = _CaptureHandler(app, "/api/cr/library")
            cropper.handle_cr_library(h)

            self.assertEqual(h.status, 200)
            tiers = {img.get("tier") for img in (h.payload or {}).get("images") or []}
            filenames = {img.get("filename") for img in (h.payload or {}).get("images") or []}
            self.assertNotIn("canonical", tiers)
            self.assertNotIn(can_name, filenames)


    def test_milestone_cr_upload_on_event_pinned_server(self):
        """Event_2 server + scope_milestone_id in body — same library path as milestone server."""
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev1, ev2, _mdir, app = _milestone_fixture(prod)
            app.scope_type = "event"
            app.active_milestone_id = None
            upload_name = "event_server_milestone_upload.png"
            body = {
                "scope_milestone_id": "milestone1_arc1",
                "filename": upload_name,
                "image_b64": base64.b64encode(_MIN_PNG).decode(),
                "tier": "source",
            }
            h = _CaptureHandler(app)
            cropper.handle_cr_upload(h, body)

            self.assertEqual(h.status, 200, h.payload)
            dest = ev1 / "library" / "images" / "sources" / upload_name
            self.assertTrue(dest.is_file(), f"expected upload at {dest}")

    def test_upload_tolerates_legacy_event_id_with_milestone_scope(self):
        """v59 clients send event_id on every mutation; must not SCOPE_AMBIGUOUS."""
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev1, _ev2, _mdir, app = _milestone_fixture(prod)
            body = {
                "scope_milestone_id": "milestone1_arc1",
                "event_id": "Event_2",
                "filename": "legacy_event_id_ok.png",
                "image_b64": base64.b64encode(_MIN_PNG).decode(),
                "tier": "source",
            }
            h = _CaptureHandler(app)
            cropper.handle_cr_upload(h, body)
            self.assertEqual(h.status, 200, h.payload)
            self.assertTrue(
                (ev1 / "library" / "images" / "sources" / "legacy_event_id_ok.png").is_file(),
            )


if __name__ == "__main__":
    unittest.main()
