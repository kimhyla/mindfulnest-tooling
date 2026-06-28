#!/usr/bin/env python3
"""Unit tests for EVENT_DEDICATED_SERVER_PROVISION_V1."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
PROD = REPO / "Production"
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))

from lib.event_server_provision import (  # noqa: E402
    DEFAULT_WAIT_SECONDS,
    bookmark_url_for_event,
    provision_dedicated_event_server,
)


class TestEventServerProvision(unittest.TestCase):
    def test_cold_boot_wait_matches_launchd_gate(self) -> None:
        self.assertGreaterEqual(DEFAULT_WAIT_SECONDS, 180)

    def test_bookmark_url(self) -> None:
        self.assertEqual(
            bookmark_url_for_event("Event_3", 5113),
            "http://localhost:5113/?event=Event_3",
        )

    def test_skip_non_dedicated_event_id(self) -> None:
        result = provision_dedicated_event_server("M5E1")
        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "not_dedicated_event")

    @mock.patch("lib.event_server_provision._event_http_ready", return_value=True)
    def test_already_running_short_circuit(self, _ready: mock.MagicMock) -> None:
        with mock.patch.object(Path, "is_dir", return_value=True):
            result = provision_dedicated_event_server("Event_2")
        self.assertTrue(result.ok)
        self.assertTrue(result.ready)
        self.assertTrue(result.already_running)
        self.assertEqual(result.port, 5112)

    @mock.patch("lib.event_server_provision.wait_for_event_server_http", return_value=True)
    @mock.patch("lib.event_server_provision._run_bash_script")
    @mock.patch("lib.event_server_provision._event_http_ready", return_value=False)
    def test_provision_runs_bash_scripts(
        self,
        _ready: mock.MagicMock,
        run_bash: mock.MagicMock,
        _wait: mock.MagicMock,
    ) -> None:
        with mock.patch.object(Path, "is_dir", return_value=True):
            result = provision_dedicated_event_server("Event_4")
        self.assertTrue(result.ok)
        self.assertTrue(result.ready)
        self.assertEqual(result.port, 5114)
        self.assertEqual(run_bash.call_count, 2)
        run_bash.assert_any_call(
            "ensure_server_port.sh",
            "5114",
            "Event_4",
            mock.ANY,
        )
        run_bash.assert_any_call("install_production_server_launchagent.sh", "Event_4")

    def test_missing_event_dir(self) -> None:
        with mock.patch.object(Path, "is_dir", return_value=False):
            result = provision_dedicated_event_server("Event_50")
        self.assertFalse(result.ok)
        self.assertIn("missing", (result.error or "").lower())


if __name__ == "__main__":
    unittest.main()
