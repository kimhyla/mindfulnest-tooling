"""SCOPE_RESTART_RECONCILE_V1 — contract tests for post-restart scope package."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parents[1]
STORYBOARD_SRC = TOOLS / "storyboard-v2" / "src"


def _read(relative: str) -> str:
    return (STORYBOARD_SRC / relative).read_text(encoding="utf-8")


class ScopeRestartReconcileSourceContract(unittest.TestCase):
    """Static guards — markers must stay wired for all five category fixes."""

    def test_scope_ready_gate_exists(self) -> None:
        client = _read("api/client.ts")
        self.assertIn("SCOPE_SNAPSHOT_FAIL_CLOSED_V1", client)
        self.assertIn("scopeReady.value", client)
        self.assertIn("SCOPE_NOT_READY", client)
        self.assertIn("fetchEventCurrentWithRetry", client)

    def test_reconcile_module_exists(self) -> None:
        reconcile = _read("state/scopeReconcile.ts")
        self.assertIn("SCOPE_RESTART_RECONCILE_V1", reconcile)
        self.assertIn("reconcileScopeAfterRestart", reconcile)
        self.assertIn("reconcileClientScope", reconcile)
        self.assertIn("restoreMilestoneScopeAfterRestart", reconcile)
        self.assertIn("readPersistedMilestoneId", reconcile)
        self.assertIn("confirmServerMilestoneScope", reconcile)
        gate = _read("state/milestoneScopeGate.ts")
        self.assertIn("MILESTONE_SCOPE_GATE_V1", gate)
        self.assertIn("confirmServerMilestoneScope", gate)
        boundary = _read("components/ScopeBoundary.tsx")
        self.assertIn("confirmServerMilestoneScope", boundary)
        watcher = _read("components/ServerRehydrateWatcher.tsx")
        self.assertIn("reconcileScopeAfterRestart", watcher)

    def test_pathapp_always_injects_event_scope(self) -> None:
        client = _read("api/client.ts")
        self.assertIn("Library event is always required", client)
        self.assertIn("payload['scope_event_id'] = scope.event_id", client)

    def test_dedicated_port_retry_schedule(self) -> None:
        current = _read("state/scopeEventCurrent.ts")
        self.assertIn("EVENT_CURRENT_RETRY_DELAYS_MS", current)
        self.assertIn("503", current)

    def test_error_dedupe(self) -> None:
        err = _read("api/errorBoundary.ts")
        self.assertIn("SCOPE_ERROR_DEDUPE_V1", err)
        self.assertIn("SCOPE_MISMATCH_DEDUPE_MS", err)
        banner = _read("components/ScopeBanner.tsx")
        self.assertIn("SCOPE_ERROR_DEDUPE_V1", banner)

    def test_server_scope_ready_marker(self) -> None:
        server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
        self.assertIn("self.scope_ready", server)
        self.assertIn("app.scope_ready = True", server)
        self.assertIn("cli_pinned_event_id", server)
        ev = (TOOLS / "server_handlers" / "event_video.py").read_text(encoding="utf-8")
        self.assertIn("SCOPE_RESTART_RECONCILE_V1", ev)
        self.assertIn("SCOPE_NOT_READY", ev)
        self.assertIn("scope_ready", ev)
        self.assertIn("DEDICATED_PORT_PIN_IMMUTABLE", ev)
        reconcile = _read("state/scopeReconcile.ts")
        self.assertIn("readAuthoritativeEventId", reconcile)
        self.assertIn("readDedicatedPortEventId", reconcile)


class HandleEventCurrentScopeReady(unittest.TestCase):
    """Live handler behavior for scope_ready gate."""

    def test_503_when_not_ready(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "event_video_test_mod",
            TOOLS / "server_handlers" / "event_video.py",
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["event_video_test_mod"] = mod
        spec.loader.exec_module(mod)

        handler = MagicMock()
        handler.app = MagicMock(scope_ready=False)
        mod.handle_event_current(handler)
        handler._send_error_v59.assert_called_once()
        args, kwargs = handler._send_error_v59.call_args
        self.assertEqual(args[0], 503)
        self.assertEqual(kwargs.get("error_code") or args[1], "SCOPE_NOT_READY")

    def test_200_when_ready(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "event_video_test_mod2",
            TOOLS / "server_handlers" / "event_video.py",
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["event_video_test_mod2"] = mod
        spec.loader.exec_module(mod)

        handler = MagicMock()
        handler.app = MagicMock(
            scope_ready=True,
            event_id="Event_2",
            event_dir=Path("/tmp/Event_2"),
            event_generation=3,
            scope_type="event",
            active_milestone_id=None,
        )
        handler.app.state.read_state.return_value = {
            "active_video": "resolution",
            "videos": {"intro": {}, "resolution": {}},
        }
        mod.handle_event_current(handler)
        handler._send_json.assert_called_once()
        status, body = handler._send_json.call_args[0]
        self.assertEqual(status, 200)
        self.assertEqual(body["event_id"], "Event_2")


if __name__ == "__main__":
    unittest.main()
