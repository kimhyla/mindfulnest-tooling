#!/usr/bin/env python3
"""CROP_SAVE_LIBRARY_VISIBILITY_V1 — crop save naming, parent link, library row shape."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS.parent.parent))
sys.path.insert(0, str(TOOLS))

from Production.tools.server_handlers import cropper  # noqa: E402


class CropSaveLibraryTests(unittest.TestCase):
    def test_crop_delivery_names_from_source_path(self):
        source = (
            "http://localhost:5114/api/cr/full?abs_path="
            + "%2Ftmp%2FChatGPT%20Image%20Jun%2030%2C%202026%2C%2003_00_36%20PM.png"
        )
        filename, key, display = cropper._crop_delivery_names(source, "lib", 999)
        self.assertTrue(filename.endswith("_crop_999.webp"))
        self.assertIn("ChatGPT", filename)
        self.assertEqual(display, "ChatGPT Image Jun 30, 2026, 03_00_36 PM (4:3 crop)")
        self.assertEqual(key, Path(filename).stem.replace(" ", "_"))

    def test_crop_delivery_names_fallback_without_source(self):
        filename, key, display = cropper._crop_delivery_names("", "lib", 42)
        self.assertEqual(filename, "crop_lib_42.webp")
        self.assertEqual(key, "crop_lib_42")
        self.assertEqual(display, "Crop lib")

    def test_resolve_parent_prefers_file_path(self):
        source = (
            "http://localhost:5114/api/cr/full?abs_path="
            + "%2FEvent%2Flibrary%2Fimages%2Fsources%2Fmaster.png"
        )
        real = cropper._source_abs_path_from_source_key(source)
        self.assertTrue(str(real).endswith("master.png"))
        client = MagicMock()
        client.get_items.return_value = [{"id": 99}]
        with patch.object(cropper, "DirectusAdminClient", create=True):
            with patch(
                "lib.directus_admin_client.DirectusAdminClient",
                return_value=client,
            ):
                pid = cropper._resolve_parent_asset_id_from_source_key(source)
        self.assertEqual(pid, 99)
        client.get_items.assert_called()
        call_filters = client.get_items.call_args.kwargs.get("filters") or client.get_items.call_args[0]
        # first call should be file_path match
        self.assertTrue(client.get_items.called)

    def test_save_crop_handler_emits_library_item_shape(self):
        h = MagicMock()
        h.app.state = MagicMock()
        ctx = MagicMock()
        ctx.library_event_dir = MagicMock()
        ctx.library_event_dir.name = "Event_4"
        body = {
            "crop_png_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            "source_key": "http://localhost/api/cr/full?abs_path=%2Ftmp%2Ftree.png",
        }
        with patch.object(cropper, "_resolve_cr_library_scope", return_value=ctx):
            with patch.object(cropper, "_bg_module") as bg_mod:
                bg = bg_mod.return_value
                bg.process_crop.return_value = (b"webp", 800, 600, "data:thumb", "data:gal")
                with patch.object(
                    cropper,
                    "event_images_crops_dir",
                    return_value="/tmp/crops",
                ):
                    with patch("builtins.open", unittest.mock.mock_open()):
                        with patch.object(cropper.os, "makedirs"):
                            with patch.object(cropper.os.path, "realpath", side_effect=lambda p: p):
                                with patch.object(
                                    cropper,
                                    "_source_abs_path_from_source_key",
                                    return_value="/tmp/tree.png",
                                ):
                                    with patch.object(
                                        cropper,
                                        "_resolve_parent_asset_id_from_source_key",
                                        return_value=12,
                                    ):
                                        with patch.object(cropper, "invalidate_cr_library_cache"):
                                            cropper.handle_cr_save_crop(h, body)
        self.assertEqual(h._send_json.call_args[0][0], 200)
        payload = h._send_json.call_args[0][1]
        self.assertTrue(payload.get("ok"))
        self.assertIn("library_item", payload)
        self.assertIn("(4:3 crop)", payload.get("display_name", ""))
        self.assertEqual(payload.get("parent_library_key"), "tree")


if __name__ == "__main__":
    unittest.main()
