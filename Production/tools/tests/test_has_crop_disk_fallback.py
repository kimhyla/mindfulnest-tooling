"""DIRECTUS_HAS_CROP_DISK_FALLBACK_V1 — library list has_crop without Directus."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server_handlers.cropper import _enrich_has_crop_from_disk


class TestHasCropDiskFallback(unittest.TestCase):
    def test_master_has_crop_from_crops_stem_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            crops = event_dir / "library" / "images" / "crops"
            crops.mkdir(parents=True)
            master_name = "ChatGPT_Image_Jun_30_crop"
            (crops / f"{master_name}.webp").write_bytes(b"x")
            master_path = event_dir / "library" / "images" / "source" / "ChatGPT_Image_Jun_30.png"
            master_path.parent.mkdir(parents=True)
            master_path.write_bytes(b"m")
            images = [
                {
                    "key": "master1",
                    "abs_path": str(master_path),
                    "is_master": True,
                    "asset_type": "still_master",
                    "has_crop": False,
                },
            ]
            _enrich_has_crop_from_disk(images, event_dir)
            self.assertTrue(images[0]["has_crop"])
            self.assertEqual(images[0].get("has_crop_source"), "disk_stem_match")


if __name__ == "__main__":
    unittest.main()
