"""LIBRARY_SCOPE_ROOT_PARITY_V1 — milestone scope uses ctx.library_event_dir."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from server_handlers import cropper


class TestCrLibraryMilestoneScopeParity(unittest.TestCase):
    def test_resolve_cr_library_scope_delegates_to_assert_production_scope(self) -> None:
        handler = mock.MagicMock()
        expected = {
            "event_dir": Path("/library/Event_4"),
            "scope_type": "milestone",
            "event_id": "Event_4",
        }
        with mock.patch(
            "server_handlers.milestone_scope.assert_production_scope",
            return_value=expected,
        ) as scope_mock:
            ctx = cropper._resolve_cr_library_scope(handler, {"scope_type": "milestone"})
        scope_mock.assert_called_once()
        self.assertEqual(ctx["event_dir"], Path("/library/Event_4"))
        self.assertEqual(ctx["scope_type"], "milestone")

    def test_project_scope_uses_server_event_dir_from_assert(self) -> None:
        handler = mock.MagicMock()
        expected = {
            "event_dir": Path("/server/Event_4"),
            "scope_type": "project",
            "event_id": "Event_4",
        }
        with mock.patch(
            "server_handlers.milestone_scope.assert_production_scope",
            return_value=expected,
        ):
            ctx = cropper._resolve_cr_library_scope(handler, {"scope_type": "project"})
        self.assertEqual(ctx["event_dir"], Path("/server/Event_4"))


if __name__ == "__main__":
    unittest.main()
