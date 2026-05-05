#!/usr/bin/env python3
"""Contract test: PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 — m_number=N → Event_N.

Per Δ-C5 closure (post-redeploy-bug-triage 2026-05-05). The 1:1
m_number=event_number identity is the design contract per Kim's authoring
model (one distinct module per event); page header note "author each by
creating an Event" implies authoring-order numbering. This test pins the
contract.

If a future authoring workflow ever creates a module out of N-order such
that m_number ≠ event_number, this test will fail and a HARD upgrade to
schema-backed lookup (`prod_modules.event_number` field) is the right
next step at that point.

Mirrors test_tier3_server.py's HTTP-based pattern: real ProductionServer
on an ephemeral port, fixture event_dirs on disk, real /api/production/map
fetch. Mocks DirectusAdminClient so the test runs without Directus
credentials.

Run:
    python3 -m unittest Production.tools.tests.test_production_map_m_to_event_convention
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

# Directus lock bypass — required for isolated tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"

import production_server as PS  # noqa: E402


SYNTHETIC_PROD_MODULES = [
    {"id": 1, "m_number": 1, "creature_name": "Tessa",  "video_role": "intro"},
    {"id": 2, "m_number": 2, "creature_name": "Luna",   "video_role": "intro"},
    {"id": 3, "m_number": 3, "creature_name": "Benson", "video_role": "intro"},
]


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _make_production_root(tmp: Path) -> tuple[Path, Path, str]:
    """Create a Production/ root with Event_1, Event_2; deliberately omit Event_3.

    Returns (event_dir for server pin, storyboard_path, event_id).
    """
    production_root = tmp / "Production"
    production_root.mkdir()
    # Event_1 — pinned event for the server. Has a state.json + storyboard.
    event_dir = production_root / "Event_1"
    event_dir.mkdir()
    storyboard_path = event_dir / "storyboard_v59_prod.html"
    storyboard_path.write_text(
        "<!doctype html><html><body>fixture</body></html>",
        encoding="utf-8",
    )
    state_path = event_dir / "production_state.json"
    state_path.write_text(json.dumps({
        "event_id": "Event_1",
        "videos": {"intro": {"beats": {}, "display_order": []}},
    }, indent=2))
    # Event_2 — exists, M2 should resolve to it.
    (production_root / "Event_2").mkdir()
    # Event_3 — DELIBERATELY NOT CREATED. M3's lookup should resolve to None.
    return event_dir, storyboard_path, "Event_1"


def _start_server(event_dir: Path, storyboard_path: Path, event_id: str, port: int):
    state_mgr = PS.StateManager(event_dir, event_id)
    app = PS.AppContext(
        event_dir=event_dir,
        storyboard_path=storyboard_path,
        event_id=event_id,
        state=state_mgr,
        client=None,
    )
    if not hasattr(app, "touch"):
        app.touch = lambda: None  # type: ignore[attr-defined]
    server = PS.ProductionServer(("127.0.0.1", port), app)
    thread = threading.Thread(
        target=server.serve_forever, name="prodmap-conv-test-server", daemon=True,
    )
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.05)
    return server, thread, app


def _http_get(port: int, path: str, timeout: float = 5.0) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload


class ProductionMapMtoEventConventionTest(unittest.TestCase):
    """Pin the m_number → Event_<m_number> resolution + None-on-missing.

    PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 (SOFT) — promoted from the prior
    `event_dirs[0]` always-Event_1 bug. Convention-based; no schema column.
    Identity is the design contract per Kim 2026-05-05.
    """

    @classmethod
    def setUpClass(cls):
        if hasattr(signal, "alarm"):
            def _timeout_handler(signum, frame):
                print("[CONV TEST] signal.alarm fired — aborting hung test",
                      file=sys.stderr, flush=True)
                os._exit(2)
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(30)

    @classmethod
    def tearDownClass(cls):
        if hasattr(signal, "alarm"):
            signal.alarm(0)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prodmap_conv_"))
        self.event_dir, self.sb_path, self.event_id = _make_production_root(self.tmp)
        self.port = _find_free_port()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.sb_path, self.event_id, self.port,
        )
        # Reset the 60s production-map cache between tests so each run is fresh.
        PS.ProductionHandler._PRODUCTION_MAP_CACHE = None
        PS.ProductionHandler._PRODUCTION_MAP_CACHE_TS = 0

    def tearDown(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mocked_directus_client(self):
        """Return a mock that simulates DirectusAdminClient with our synthetic prod_modules."""
        mock_client = MagicMock()
        mock_client._request.return_value = list(SYNTHETIC_PROD_MODULES)
        return mock_client

    def test_m1_resolves_to_event_1_dir(self):
        with patch("lib.directus_admin_client.DirectusAdminClient",
                   return_value=self._mocked_directus_client()):
            status, payload = _http_get(self.port, "/api/production/map")
        self.assertEqual(status, 200, f"unexpected status: {status} body={payload}")
        rows = payload.get("modules", [])
        m1 = next((r for r in rows if r.get("m_number") == 1), None)
        self.assertIsNotNone(m1, "M1 row missing from /api/production/map")
        self.assertEqual(
            m1["event_dir"], "Event_1",
            "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 violated: "
            f"M1 resolved to {m1.get('event_dir')!r}, expected 'Event_1'.",
        )

    def test_m2_resolves_to_event_2_dir(self):
        with patch("lib.directus_admin_client.DirectusAdminClient",
                   return_value=self._mocked_directus_client()):
            status, payload = _http_get(self.port, "/api/production/map")
        self.assertEqual(status, 200)
        rows = payload.get("modules", [])
        m2 = next((r for r in rows if r.get("m_number") == 2), None)
        self.assertIsNotNone(m2, "M2 row missing from /api/production/map")
        self.assertEqual(
            m2["event_dir"], "Event_2",
            "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 violated: "
            f"M2 resolved to {m2.get('event_dir')!r}, expected 'Event_2'. "
            "If M2 reports 'Event_1' the always-Event_1 fallback bug is back.",
        )

    def test_m3_resolves_to_none_when_event_3_missing(self):
        """Event_3/ deliberately not on disk — convention should fall through to None,
        NOT silently use Event_1 as fallback (that was the original Bug C symptom)."""
        with patch("lib.directus_admin_client.DirectusAdminClient",
                   return_value=self._mocked_directus_client()):
            status, payload = _http_get(self.port, "/api/production/map")
        self.assertEqual(status, 200)
        rows = payload.get("modules", [])
        m3 = next((r for r in rows if r.get("m_number") == 3), None)
        self.assertIsNotNone(m3, "M3 row missing from /api/production/map")
        self.assertIsNone(
            m3["event_dir"],
            "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 violated: "
            f"M3 resolved to {m3.get('event_dir')!r} when Event_3/ does not "
            "exist on disk. Expected None — the SOFT convention's null path "
            "is what prevents the always-Event_1 silent fallback bug from "
            "returning. If this test sees 'Event_1' a regression has landed.",
        )

    def test_no_row_silently_falls_back_to_event_1(self):
        """Aggregate guard: every row's event_dir is either its own Event_<m_number>
        or None. No row resolves to a different Event_<N>/ via silent fallback."""
        with patch("lib.directus_admin_client.DirectusAdminClient",
                   return_value=self._mocked_directus_client()):
            status, payload = _http_get(self.port, "/api/production/map")
        self.assertEqual(status, 200)
        rows = payload.get("modules", [])
        for r in rows:
            mn = r.get("m_number")
            ed = r.get("event_dir")
            if ed is None:
                continue
            expected = f"Event_{mn}"
            self.assertEqual(
                ed, expected,
                "PRODUCTION_MAP_MULTI_EVENT_MAPPING_V1 violated: "
                f"M{mn} resolved to {ed!r}; expected {expected!r} or None. "
                "Cross-row silent fallback is the original Bug C symptom.",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
