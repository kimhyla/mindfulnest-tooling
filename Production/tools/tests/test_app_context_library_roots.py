#!/usr/bin/env python3
"""Regression: AppContext library helpers must not reference self.app."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parents[1]
_REPO = _TOOLS.parent.parent
for p in (str(_REPO), str(_TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from Production.lib.event_library import ensure_event_library_dirs  # noqa: E402
import production_server as PS  # noqa: E402


class TestAppContextLibraryRoots(unittest.TestCase):
    def test_library_root_dirs_on_app_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "Event_2"
            ev.mkdir()
            ensure_event_library_dirs(ev)
            (ev.parent / "canonical_images").mkdir(parents=True, exist_ok=True)
            state = MagicMock()
            app = PS.AppContext(
                event_dir=ev,
                storyboard_path=ev / "storyboard_v59_prod.html",
                event_id="Event_2",
                state=state,
                client=None,
            )
            roots = app._library_root_dirs()
            self.assertIsInstance(roots, list)
            self.assertGreater(len(roots), 0)
            resolved = app.resolve_library_image_path("nonexistent_key_xyz")
            self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
