#!/usr/bin/env python3
"""SHARED_BASELINE_IMAGE_LIBRARY_V1 — global baseline tier + path roots."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))
sys.path.insert(0, str(TOOLS))

from Production.lib.event_library import (  # noqa: E402
    baseline_images_dir,
    baseline_registry_path,
    is_baseline_image_path,
    library_image_roots,
    list_baseline_meta,
    resolve_library_image_path,
)
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

    def _assert_event_scope(self, scope, allow_missing=False, allow_missing_video_role=False):
        return True


def _install_baseline(prod: Path, count: int = 2) -> None:
    bdir = baseline_images_dir(prod)
    bdir.mkdir(parents=True, exist_ok=True)
    images = []
    for i in range(1, count + 1):
        key = f"baseline_still_{i:02d}"
        fname = f"{key}.png"
        (bdir / fname).write_bytes(_MIN_PNG)
        images.append({
            "key": key,
            "filename": fname,
            "display_name": f"Baseline still {i:02d}",
            "tags": ["baseline", "shared"],
        })
    registry = {
        "version": 1,
        "id": "test_baseline",
        "apply_to_all_events": True,
        "images": images,
    }
    baseline_registry_path(prod).write_text(json.dumps(registry), encoding="utf-8")


class BaselineImageLibraryTests(unittest.TestCase):
    def test_list_baseline_meta_apply_to_all_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            _install_baseline(prod, count=3)
            self.assertEqual(len(list_baseline_meta(prod)), 3)

    def test_is_baseline_image_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            _install_baseline(prod, count=1)
            fp = baseline_images_dir(prod) / "baseline_still_01.png"
            self.assertTrue(is_baseline_image_path(str(fp), prod))
            self.assertFalse(is_baseline_image_path(str(prod / "Event_1/x.png"), prod))

    def test_library_image_roots_includes_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_1"
            _install_baseline(prod, count=1)
            roots = library_image_roots(ev, prod)
            baseline_root = str(baseline_images_dir(prod).resolve())
            self.assertIn(baseline_root, roots)

    def test_resolve_library_image_path_finds_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            _install_baseline(prod, count=1)
            ev = prod / "Event_4"
            resolved = resolve_library_image_path("baseline_still_01", ev, prod)
            self.assertEqual(resolved, str(baseline_images_dir(prod) / "baseline_still_01.png"))

    def test_cr_library_includes_shared_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_4"
            (ev / "library" / "images" / "sources").mkdir(parents=True)
            _install_baseline(prod, count=2)

            app = MagicMock()
            app.event_dir = ev
            app.event_id = "Event_4"
            app.event_generation = 1
            app.scope_type = "event"
            app.active_milestone_id = None

            h = _CaptureHandler(app)
            cropper.handle_cr_library(h)

            self.assertEqual(h.status, 200)
            images = (h.payload or {}).get("images") or []
            baseline = [i for i in images if i.get("shared_baseline")]
            self.assertEqual(len(baseline), 2)
            tiers = {i.get("tier") for i in baseline}
            self.assertEqual(tiers, {"source"})
            canonical = [i for i in images if i.get("tier") == "canonical"]
            self.assertEqual(len(canonical), 0)

    def test_event_local_key_wins_over_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_3"
            src = ev / "library" / "images" / "sources"
            src.mkdir(parents=True)
            (src / "baseline_still_01.png").write_bytes(b"local-upload")
            _install_baseline(prod, count=1)

            app = MagicMock()
            app.event_dir = ev
            app.event_id = "Event_3"
            app.event_generation = 1
            app.scope_type = "event"
            app.active_milestone_id = None

            h = _CaptureHandler(app)
            cropper.handle_cr_library(h)

            baseline_rows = [i for i in (h.payload or {}).get("images") or [] if i.get("key") == "baseline_still_01"]
            self.assertEqual(len(baseline_rows), 1)
            self.assertNotIn("shared_baseline", baseline_rows[0])

    def test_baseline_delete_returns_403(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            ev = prod / "Event_3"
            (ev / "library" / "images" / "sources").mkdir(parents=True)
            _install_baseline(prod, count=1)
            fp = baseline_images_dir(prod) / "baseline_still_01.png"

            app = MagicMock()
            app.event_dir = ev
            app.event_id = "Event_3"
            app.event_generation = 1
            app.scope_type = "event"
            app.active_milestone_id = None

            h = _CaptureHandler(app)
            h._scope_body = lambda body: body or {}
            h._check_event_pin = lambda *a, **k: True
            h._assert_event_scope = lambda *a, **k: True

            cropper.handle_cr_library_delete(h, {
                "key": "baseline_still_01",
                "abs_path": str(fp),
            })
            self.assertEqual(h.status, 403)
            self.assertEqual((h.payload or {}).get("error_code"), "BASELINE_IMAGE_PROTECTED")


if __name__ == "__main__":
    unittest.main()
