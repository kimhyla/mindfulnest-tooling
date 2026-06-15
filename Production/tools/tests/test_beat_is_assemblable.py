"""Tests for beat_is_assemblable — magic-only beats must be Send Out eligible."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "credentials_lib"))
from ffmpeg_stitch import beat_is_assemblable  # noqa: E402


class BeatIsAssemblableTests(unittest.TestCase):
    def test_selected_option(self):
        self.assertTrue(beat_is_assemblable({"phase_1": {"selected_option": 1}}))

    def test_magic_still_without_selected_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            event_dir = Path(tmp)
            magic = event_dir / "magic_still_beat_02_test.mp4"
            magic.write_bytes(b"\x00")
            beat = {"magic_still_path": magic.name, "phase_1": {"selected_option": None}}
            self.assertTrue(beat_is_assemblable(beat, event_dir=event_dir))

    def test_empty_beat(self):
        self.assertFalse(beat_is_assemblable({"phase_1": {}}, event_dir=Path("/tmp")))


if __name__ == "__main__":
    unittest.main()
