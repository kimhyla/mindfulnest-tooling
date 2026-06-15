#!/usr/bin/env python3
"""Per-event library scoping + canonical image injection tests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parents[1]
_REPO = _TOOLS.parent.parent
for p in (str(_REPO), str(_TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from Production.lib.event_library import (  # noqa: E402
    arc_number_from_event_id,
    canonical_meta_for_arc,
    ensure_event_library_dirs,
    event_images_sources_dir,
    event_watercolors_dir,
    is_canonical_image_path,
    resolve_library_image_path,
)


class TestEventLibraryHelpers(unittest.TestCase):
    def test_arc_number_from_event_id(self):
        self.assertEqual(arc_number_from_event_id("Event_1"), 1)
        self.assertEqual(arc_number_from_event_id("Event_2"), 2)

    def test_canonical_meta_for_arcs_1_and_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            registry = {
                "version": 1,
                "sets": [{
                    "id": "test",
                    "arc_numbers": [1, 2],
                    "images": [{"key": "canonical_arlo_mirror_v1", "filename": "canonical_arlo_mirror_v1.png"}],
                }],
            }
            (prod / "canonical_image_registry.json").write_text(json.dumps(registry), encoding="utf-8")
            meta1 = canonical_meta_for_arc(prod, 1)
            meta2 = canonical_meta_for_arc(prod, 2)
            meta3 = canonical_meta_for_arc(prod, 3)
            self.assertEqual(len(meta1), 1)
            self.assertEqual(len(meta2), 1)
            self.assertEqual(len(meta3), 0)

    def test_resolve_event_scoped_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "Event_1"
            prod = Path(tmp)
            ensure_event_library_dirs(ev)
            src = event_images_sources_dir(ev) / "event1_only.png"
            src.write_bytes(b"png")
            resolved = resolve_library_image_path("event1_only", ev, prod)
            self.assertEqual(resolved, str(src))

    def test_canonical_path_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            prod = Path(tmp)
            can = prod / "canonical_images" / "canonical_arlo_mirror_v1.png"
            can.parent.mkdir(parents=True)
            can.write_bytes(b"x")
            self.assertTrue(is_canonical_image_path(str(can), prod))
            self.assertFalse(is_canonical_image_path(str(prod / "Event_1/foo.png"), prod))

    def test_event_watercolors_dir_empty_for_new_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "Event_2"
            ensure_event_library_dirs(ev)
            wc = event_watercolors_dir(ev)
            self.assertTrue(wc.is_dir())
            self.assertEqual(list(wc.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
