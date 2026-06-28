#!/usr/bin/env python3
"""LIBRARY_PANEL_CLASSIFICATION_V1 — panel_tabs contract + Directus overlay."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))
sys.path.insert(0, str(TOOLS))

from Production.lib.library_panel_contract import (  # noqa: E402
    attach_panel_tabs,
    attach_panel_tabs_all,
    panel_tabs_for_cr_library_row,
    row_matches_panel_filter,
)
from Production.tools.server_handlers import cropper  # noqa: E402

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT"
    b"\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x1d\xf3\x00\x00\x00\x00IEND\xaeB`\x82"
)


class LibraryPanelContractUnitTests(unittest.TestCase):
    def test_disk_tiers_map_to_images_tab(self):
        for tier in ("source", "cropped", "character_master", "element_pose"):
            self.assertEqual(panel_tabs_for_cr_library_row({"tier": tier}), ["images"])

    def test_watercolor_tier(self):
        self.assertEqual(panel_tabs_for_cr_library_row({"tier": "watercolor"}), ["watercolors"])

    def test_canonical_empty(self):
        self.assertEqual(panel_tabs_for_cr_library_row({"tier": "canonical"}), [])

    def test_directus_overlay_does_not_change_panel_tabs(self):
        row = {"tier": "element_pose", "asset_type": "element_pose"}
        attach_panel_tabs(row)
        row["asset_type"] = "watercolor_static"  # simulate bad Directus overwrite
        attach_panel_tabs(row)
        self.assertEqual(row["panel_tabs"], ["images"])

    def test_row_matches_panel_filter(self):
        row = attach_panel_tabs({"tier": "element_pose"})
        self.assertTrue(row_matches_panel_filter(row, "images"))
        self.assertFalse(row_matches_panel_filter(row, "watercolors"))


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


class CrLibraryPanelTabsIntegrationTests(unittest.TestCase):
    def test_cr_library_emits_panel_tabs_on_all_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            event = prod / "Event_99_panel_test"
            sources = event / "library" / "images" / "sources"
            sources.mkdir(parents=True)
            (sources / "test_still.png").write_bytes(_MIN_PNG)

            app = MagicMock()
            app.event_id = "Event_99_panel_test"
            app.event_dir = event
            app.prod_root = prod

            h = _CaptureHandler(app)
            ctx = MagicMock()
            ctx.library_event_dir = event
            ctx.prod_root = prod
            ctx.scope_type = "event"
            ctx.skeleton_ref = None

            with patch.object(cropper, "_resolve_cr_library_scope", return_value=ctx), patch.object(
                cropper,
                "_bg_module",
            ) as bg_mod:
                bg = bg_mod.return_value
                bg.read_sidecar_for_poll_snapshot.return_value = {"arcs": {}}
                bg.BG_STILLS_DIR = str(sources)
                cropper.handle_cr_library(h)

            self.assertEqual(h.status, 200)
            images = h.payload.get("images") or []
            self.assertGreater(len(images), 0)
            for row in images:
                self.assertIn("panel_tabs", row, row)
                self.assertTrue(row["panel_tabs"], row)
                self.assertIn("images", row["panel_tabs"])

    def test_panel_query_filters_server_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp) / "Production"
            event = prod / "Event_99_panel_test"
            sources = event / "library" / "images" / "sources"
            wc = event / "library" / "watercolors"
            sources.mkdir(parents=True)
            wc.mkdir(parents=True)
            (sources / "still.png").write_bytes(_MIN_PNG)
            (wc / "overlay.png").write_bytes(_MIN_PNG)

            app = MagicMock()
            app.event_id = "Event_99_panel_test"
            app.event_dir = event
            app.prod_root = prod

            h = _CaptureHandler(app, path="/api/cr/library?panel=images")
            ctx = MagicMock()
            ctx.library_event_dir = event
            ctx.prod_root = prod
            ctx.scope_type = "event"
            ctx.skeleton_ref = None

            with patch.object(cropper, "_resolve_cr_library_scope", return_value=ctx), patch.object(
                cropper,
                "_bg_module",
            ) as bg_mod, patch.object(
                cropper,
                "list_watercolor_items",
                return_value=[
                    {
                        "key": "overlay",
                        "filename": "overlay.png",
                        "abs_path": str(wc / "overlay.png"),
                        "thumb_url": "/api/cr/thumb?x",
                        "tags": ["watercolor"],
                    }
                ],
            ):
                bg = bg_mod.return_value
                bg.read_sidecar_for_poll_snapshot.return_value = {"arcs": {}}
                bg.BG_STILLS_DIR = str(sources)
                cropper.handle_cr_library(h)

            images = h.payload.get("images") or []
            self.assertEqual(h.payload.get("panel_filter"), "images")
            self.assertTrue(all("images" in (i.get("panel_tabs") or []) for i in images))
            self.assertFalse(any(i.get("tier") == "watercolor" for i in images))


if __name__ == "__main__":
    unittest.main()
