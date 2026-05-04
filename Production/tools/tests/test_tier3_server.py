#!/usr/bin/env python3
"""Tier 3 server-side HTTP tests (April 18 2026).

Covers the LDs:
  TIER3_SERVER_WHITELIST_EXTENSIONS_PAUSE_SPEAKER_DISPLAY_ORDER (HIGH)
  TIER3_BEAT_CREATE_ENDPOINT (HIGH)

Philosophy: match the Tier 1A HTTP-based pattern. Spin up a live
ProductionServer on an ephemeral port with a synthetic event_dir, fire real
HTTP requests via urllib.request, and validate both the response AND the
written production_state.json + sidecar .L.json.

signal.alarm(30) prevents hangs.

Run:
    python3 -m unittest Production.tools.tests.test_tier3_server
  or
    cd Production/tools/tests && python3 test_tier3_server.py
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

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

# Bypass cross-machine Directus lock — required for isolated tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
# Explicitly enable Tier 1 feature flag (covers Tier 3 logic).
os.environ["MINDFULNEST_T1_ENABLED"] = "1"
# Ensure v2 write path is active (default, but be explicit).
os.environ.pop("MINDFULNEST_WRITE_PATH", None)

import production_server as PS  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors test_tier1a_debounce.py)
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _build_storyboard_html(beat_ids: list[str]) -> str:
    entries = []
    for bid in beat_ids:
        n = int(bid.split("_")[1])
        entries.append(
            f'{{a:"line_{n:02d}",t:"placeholder",i:"shot{n}_initial"}}'
        )
    return (
        "<html><head><script>\n"
        "var L = [" + ",".join(entries) + "];\n"
        "var TH = {};\n"
        "</script></head><body></body></html>\n"
    )


def _make_event_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    event_dir = tmp_path / "Event_TIER3"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard_path = event_dir / "storyboard_test_t3.html"
    storyboard_path.write_text(
        _build_storyboard_html(["beat_01", "beat_02", "beat_99_test"]),
        encoding="utf-8",
    )
    state_path = event_dir / "production_state.json"
    state_path.write_text(json.dumps({
        "event_id": "Event_TIER3",
        "beats": {
            "beat_01": {"text": "one", "phase_1": {}, "_version": 1},
            "beat_02": {"text": "two", "phase_1": {}, "_version": 1},
            # Non-standard beat_id that won't affect beat_NN numbering
            "beat_99_test": {"text": "test fixture", "phase_1": {}, "_version": 1},
        },
        "image_overrides": {},
    }, indent=2))
    return event_dir, storyboard_path, "Event_TIER3"


def _start_server(event_dir: Path, storyboard_path: Path, event_id: str,
                  port: int):
    state_mgr = PS.StateManager(event_dir, event_id)
    app = PS.AppContext(
        event_dir=event_dir,
        storyboard_path=storyboard_path,
        event_id=event_id,
        state=state_mgr,
        client=None,
    )
    assert state_mgr.read_state()["beats"]["beat_01"]["text"] == "one"
    if not hasattr(app, "touch"):
        app.touch = lambda: None  # type: ignore[attr-defined]
    server = PS.ProductionServer(("127.0.0.1", port), app)
    thread = threading.Thread(
        target=server.serve_forever, name="tier3-test-server", daemon=True,
    )
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.05)
    return server, thread, app


def _http_post(port: int, path: str, body: dict,
               timeout: float = 5.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
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


def _http_get(port: int, path: str,
              timeout: float = 5.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method="GET",
    )
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


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestTier3Server(unittest.TestCase):
    """HTTP-based tests for Tier 3 server-side changes."""

    @classmethod
    def setUpClass(cls):
        if hasattr(signal, "alarm"):
            def _timeout_handler(signum, frame):
                print("[T3 TEST] signal.alarm fired — test hung — aborting",
                      file=sys.stderr, flush=True)
                os._exit(2)
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(30)

    @classmethod
    def tearDownClass(cls):
        if hasattr(signal, "alarm"):
            signal.alarm(0)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t3_"))
        self.event_dir, self.sb_path, self.event_id = _make_event_fixture(self.tmp)
        self.port = _find_free_port()
        # Clear LRU dedup cache between tests so mutation_id collisions don't
        # false-positive into dedup returns.
        PS._PATCH_STATE_DEDUP.clear()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.sb_path, self.event_id, self.port,
        )

    def tearDown(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read_state(self) -> dict:
        return self.app.state.read_state()

    # ------------------------------------------------------------------
    # Whitelist extensions
    # ------------------------------------------------------------------

    def test_patch_pause_after_ms_valid(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_99_test/patch",
            {"field": "pause_after_ms", "value": 2500},
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        state = self._read_state()
        self.assertEqual(
            state["beats"]["beat_99_test"]["phase_1"]["pause_after_ms"],
            2500,
        )

    def test_patch_pause_after_ms_over_cap_rejected(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_99_test/patch",
            {"field": "pause_after_ms", "value": 99999},
        )
        # 4xx expected
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)
        state = self._read_state()
        # Must NOT have been written
        self.assertNotIn(
            "pause_after_ms",
            state["beats"]["beat_99_test"].get("phase_1", {}),
        )

    def test_patch_pause_after_ms_negative_rejected(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_99_test/patch",
            {"field": "pause_after_ms", "value": -1},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    def test_patch_pause_after_ms_non_int_rejected(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_99_test/patch",
            {"field": "pause_after_ms", "value": "not a number"},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    def test_patch_speaker_sets_mismatch(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_99_test/patch",
            {"field": "speaker", "value": "tessa"},
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        p1 = self._read_state()["beats"]["beat_99_test"]["phase_1"]
        self.assertEqual(p1.get("speaker"), "tessa")
        self.assertTrue(p1.get("speaker_mismatch"), p1)

    def test_patch_speaker_empty_rejected(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_99_test/patch",
            {"field": "speaker", "value": "   "},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    # ------------------------------------------------------------------
    # display_order on __global__ sentinel
    # ------------------------------------------------------------------

    def test_patch_display_order_global(self):
        order = ["beat_99_test", "beat_01", "beat_02"]
        status, resp = _http_post(
            self.port, "/api/v2/beat/__global__/patch",
            {"field": "display_order", "value": order},
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        state = self._read_state()
        self.assertEqual(state.get("display_order"), order)

    def test_patch_display_order_unknown_beat_rejected(self):
        order = ["beat_01", "beat_does_not_exist"]
        status, resp = _http_post(
            self.port, "/api/v2/beat/__global__/patch",
            {"field": "display_order", "value": order},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)
        self.assertIn("beat_does_not_exist", json.dumps(resp))

    def test_patch_display_order_non_list_rejected(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/__global__/patch",
            {"field": "display_order", "value": "beat_01,beat_02"},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    def test_display_order_on_non_global_rejected(self):
        # display_order is a top-level field — rejecting it on a specific beat
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "display_order", "value": ["beat_01"]},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    def test_pause_after_ms_on_global_rejected(self):
        # Individual-beat field on __global__ — rejected
        status, resp = _http_post(
            self.port, "/api/v2/beat/__global__/patch",
            {"field": "pause_after_ms", "value": 1000},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    # ------------------------------------------------------------------
    # /api/v2/beat/create
    # ------------------------------------------------------------------

    def test_beat_create_appends_when_insert_after_null(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/create",
            {"insert_after": None},
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "created", resp)
        new_bid = resp.get("beat_id")
        self.assertIsNotNone(new_bid)
        # New beat_id should be numerical max+1 from existing beat_NN (2 → 3)
        # beat_99_test doesn't match beat_NN so doesn't count for numbering.
        self.assertEqual(new_bid, "beat_03")
        state = self._read_state()
        self.assertIn(new_bid, state["beats"])
        beat = state["beats"][new_bid]
        self.assertEqual(beat.get("text"), "")
        self.assertEqual(beat.get("_version"), 0)
        self.assertEqual(beat["phase_1"].get("status"), "pending")
        self.assertEqual(beat["phase_1"].get("options"), [])
        # display_order should be populated, with new beat appended
        self.assertIn("display_order", state)
        self.assertEqual(state["display_order"][-1], new_bid)

    def test_beat_create_inserts_after(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/create",
            {"insert_after": "beat_01"},
        )
        self.assertEqual(status, 200, resp)
        new_bid = resp.get("beat_id")
        self.assertIsNotNone(new_bid)
        state = self._read_state()
        order = state["display_order"]
        idx = order.index(new_bid)
        self.assertEqual(order[idx - 1], "beat_01",
                         f"expected new beat right after beat_01, got order={order}")
        self.assertEqual(resp.get("inserted_after"), "beat_01", resp)

    def test_beat_create_mutation_id_idempotent(self):
        mid = "tier3-test-mutation-" + str(time.time())
        status1, resp1 = _http_post(
            self.port, "/api/v2/beat/create",
            {"insert_after": None, "mutation_id": mid},
        )
        self.assertEqual(status1, 200, resp1)
        # Replay — should return dedup, NOT create a second beat
        beats_after_first = len(self._read_state()["beats"])
        status2, resp2 = _http_post(
            self.port, "/api/v2/beat/create",
            {"insert_after": None, "mutation_id": mid},
        )
        self.assertEqual(status2, 200, resp2)
        self.assertEqual(resp2.get("status"), "dedup", resp2)
        self.assertEqual(resp2.get("beat_id"), resp1.get("beat_id"))
        beats_after_second = len(self._read_state()["beats"])
        self.assertEqual(beats_after_first, beats_after_second,
                         "Replay must not create a second beat")

    def test_beat_create_invalid_insert_after_type(self):
        status, resp = _http_post(
            self.port, "/api/v2/beat/create",
            {"insert_after": 42},
        )
        self.assertGreaterEqual(status, 400, resp)
        self.assertLess(status, 500, resp)

    # ------------------------------------------------------------------
    # Fresh beat default exposure
    # ------------------------------------------------------------------

    def test_fresh_beat_no_pause_defaults_to_absent(self):
        # Create a fresh beat
        status, resp = _http_post(
            self.port, "/api/v2/beat/create", {"insert_after": None},
        )
        self.assertEqual(status, 200, resp)
        new_bid = resp["beat_id"]

        # GET via /api/v2/beat/<id>
        status, resp = _http_get(self.port, f"/api/v2/beat/{new_bid}")
        self.assertEqual(status, 200, resp)
        beat = resp.get("beat", {})
        p1 = beat.get("phase_1", {})
        # Not set → absent (UI falls through to 0 or null default)
        self.assertNotIn("pause_after_ms", p1, p1)
        self.assertNotIn("speaker", p1, p1)
        self.assertNotIn("speaker_mismatch", p1, p1)

    # ------------------------------------------------------------------
    # Sidecar projection of new fields
    # ------------------------------------------------------------------

    def test_sidecar_projects_tier3_fields(self):
        # Patch three fields, then patch display_order
        status, _ = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "pause_after_ms", "value": 1500},
        )
        self.assertEqual(status, 200)
        status, _ = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "speaker", "value": "cedric"},
        )
        self.assertEqual(status, 200)
        status, _ = _http_post(
            self.port, "/api/v2/beat/__global__/patch",
            {"field": "display_order",
             "value": ["beat_99_test", "beat_01", "beat_02"]},
        )
        self.assertEqual(status, 200)

        # Sidecar path
        sidecar = self.event_dir / (self.sb_path.stem + ".L.json")
        self.assertTrue(sidecar.exists(), f"sidecar not written at {sidecar}")
        data = json.loads(sidecar.read_text())

        b01 = data.get("beat_01", {})
        self.assertEqual(b01.get("pause_after_ms"), 1500)
        self.assertEqual(b01.get("speaker"), "cedric")
        self.assertTrue(b01.get("speaker_mismatch"), b01)

        # Top-level display_order projection under __meta__
        self.assertIn("__meta__", data)
        self.assertEqual(
            data["__meta__"].get("display_order"),
            ["beat_99_test", "beat_01", "beat_02"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
