"""Ambient bed hydration + merge durability for stitch editor."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from server_handlers.stitch_editor import (
    _hydrate_slot_ambient_paths,
    _resolve_stitch_ambient_bed_path,
    _slot_merge_worthy,
)


class _MockHandler:
    def _stitch_project_root(self) -> Path:
        return Path(
            os.environ.get(
                "MN_TEST_PROJECT_ROOT",
                "/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files",
            )
        )


class StitchAmbientHydrateTests(unittest.TestCase):
    def test_slot_merge_worthy_accepts_ambient_only_patch(self):
        self.assertTrue(_slot_merge_worthy({"ambient_bed": "Intro video ambient bed"}))

    def test_hydrate_replaces_stale_path_when_preset_changes(self):
        h = _MockHandler()
        slots = [
            {
                "ambient_bed": "Intro video ambient bed",
                "ambient_bed_path": "/stale/old/path.mp3",
            }
        ]
        _hydrate_slot_ambient_paths(h, slots)
        resolved = _resolve_stitch_ambient_bed_path(h, "Intro video ambient bed")
        if resolved:
            self.assertEqual(slots[0]["ambient_bed_path"], resolved)
            self.assertNotEqual(slots[0]["ambient_bed_path"], "/stale/old/path.mp3")
        else:
            self.skipTest("Intro video ambient bed.mp3 not on disk in this environment")

    def test_hydrate_clears_path_when_preset_cleared(self):
        h = _MockHandler()
        slots = [{"ambient_bed": "", "ambient_bed_path": "/some/path.mp3"}]
        _hydrate_slot_ambient_paths(h, slots)
        self.assertNotIn("ambient_bed_path", slots[0])


if __name__ == "__main__":
    unittest.main()
