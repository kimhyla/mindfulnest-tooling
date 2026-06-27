#!/usr/bin/env python3
"""Ambient preset path resolution — mix_audio vs catalog alignment."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from server_handlers.phases import _resolve_ambient_preset_path  # noqa: E402


class TestResolveAmbientPresetPath(unittest.TestCase):
    def test_prefers_sound_library_over_legacy_ambient_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sound = root / "Production" / "assets" / "sound_library" / "ambient"
            legacy = root / "Production" / "assets" / "ambient_library"
            sound.mkdir(parents=True)
            legacy.mkdir(parents=True)
            (sound / "phase a ambient bed.mp3").write_bytes(b"sound")
            (legacy / "phase a ambient bed.mp3").write_bytes(b"legacy")
            h = SimpleNamespace(
                _stitch_project_root=mock.Mock(return_value=root),
            )
            path = _resolve_ambient_preset_path(h, "phase a ambient bed")
            self.assertIsNotNone(path)
            self.assertEqual(path.read_bytes(), b"sound")

    def test_falls_back_to_ambient_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "Production" / "assets" / "ambient_library"
            legacy.mkdir(parents=True)
            (legacy / "meditation_pretty_v1.mp3").write_bytes(b"legacy")
            h = SimpleNamespace(
                _stitch_project_root=mock.Mock(return_value=root),
            )
            path = _resolve_ambient_preset_path(h, "meditation_pretty_v1")
            self.assertIsNotNone(path)
            self.assertEqual(path.read_bytes(), b"legacy")


if __name__ == "__main__":
    unittest.main()
