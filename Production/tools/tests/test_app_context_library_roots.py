#!/usr/bin/env python3
"""Regression: AppContext library helpers must not reference self.app (BG_REF_APP_CONTEXT_V1)."""

from __future__ import annotations

import ast
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

_SERVER_PY = _TOOLS / "production_server.py"
_APP_CONTEXT_METHODS = frozenset({"_library_root_dirs", "resolve_library_image_path"})


def _app_context_method_sources() -> dict[str, str]:
    """Return {method_name: source_segment} for guarded AppContext methods."""
    tree = ast.parse(_SERVER_PY.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "AppContext":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name not in _APP_CONTEXT_METHODS:
                continue
            seg = ast.get_source_segment(_SERVER_PY.read_text(encoding="utf-8"), item)
            if seg:
                out[item.name] = seg
    return out


class TestAppContextLibraryRoots(unittest.TestCase):
    def test_app_context_has_no_app_attribute(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "Event_2"
            ev.mkdir()
            ensure_event_library_dirs(ev)
            app = PS.AppContext(
                event_dir=ev,
                storyboard_path=ev / "storyboard_v59_prod.html",
                event_id="Event_2",
                state=MagicMock(),
                client=None,
            )
            self.assertFalse(hasattr(app, "app"))

    def test_library_root_dirs_on_app_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev = Path(tmp) / "Event_2"
            ev.mkdir()
            ensure_event_library_dirs(ev)
            (ev.parent / "canonical_images").mkdir(parents=True, exist_ok=True)
            app = PS.AppContext(
                event_dir=ev,
                storyboard_path=ev / "storyboard_v59_prod.html",
                event_id="Event_2",
                state=MagicMock(),
                client=None,
            )
            roots = app._library_root_dirs()
            self.assertIsInstance(roots, list)
            self.assertGreater(len(roots), 0)
            resolved = app.resolve_library_image_path("nonexistent_key_xyz")
            self.assertIsNone(resolved)

    def test_app_context_methods_never_use_self_app_in_source(self):
        segments = _app_context_method_sources()
        self.assertEqual(
            set(segments.keys()),
            _APP_CONTEXT_METHODS,
            "expected guarded AppContext methods in production_server.py",
        )
        for name, seg in segments.items():
            self.assertNotIn(
                "self.app.",
                seg,
                f"AppContext.{name} must use self.event_dir, not self.app (BG_REF_APP_CONTEXT_V1)",
            )
            self.assertIn("self.event_dir", seg, f"AppContext.{name} must reference self.event_dir")


if __name__ == "__main__":
    unittest.main()
