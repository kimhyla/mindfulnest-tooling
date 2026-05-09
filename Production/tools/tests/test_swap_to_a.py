#!/usr/bin/env python3
"""Tests for POST /api/v2/beat/<beat_id>/swap_to_a.

Unblocks Kim's "park the favorite in slot A so Regenerate B+C doesn't
overwrite it" workflow. The endpoint atomically swaps content between
slot 1 (Option A — protected from regen) and slot N (Option B=2 or C=3),
updates selected_option + lipsync.source_option, and clears
lipsync.source_changed / audio_changed because the lipsync file still
corresponds to the same CONTENT post-swap (only the slot pointer moved).
"""

from __future__ import annotations

import json
import os
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
sys.path.insert(0, str(TOOLS / "credentials_lib"))

# Bypass cross-machine Directus lock — required for isolated tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
os.environ["MINDFULNEST_T1_ENABLED"] = "1"
os.environ.pop("MINDFULNEST_WRITE_PATH", None)

import production_server as PS  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _option(file: str, task_id: str, size: int, status: str = "completed",
            source: str = "kling_v3_pro") -> dict:
    return {
        "file": file,
        "task_id": task_id,
        "size_bytes": size,
        "status": status,
        "retries": 0,
        "source": source,
        "end_frame_prompt": f"end frame for {file}",
    }


def _make_event_fixture(tmp: Path, *, beats: dict | None = None) -> tuple[Path, Path, str]:
    event_dir = tmp / "Event_SWAPTEST"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text(
        '<html><head><script>var L = []; var TH = {};</script></head>'
        '<body></body></html>\n', encoding="utf-8",
    )
    state = event_dir / "production_state.json"
    if beats is None:
        beats = {
            "beat_01": {
                "text": "hello",
                "phase_1": {
                    "status": "completed",
                    "selected_option": 2,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        _option("beat_01_option_2.mp4", "task_B", 1_200_000),
                        _option("beat_01_option_3.mp4", "task_C", 1_100_000),
                    ],
                    "trim_start": 0.0,
                    "trim_end": None,
                    "pause_after_ms": 0,
                },
                "lipsync": {
                    "status": "completed",
                    "source_option": 2,
                    "source_changed": False,
                    "audio_changed": False,
                    "file": "beat_01_lipsync.mp4",
                },
                "_version": 3,
            },
        }
    state.write_text(json.dumps({
        "event_id": "Event_SWAPTEST",
        "beats": beats,
        "display_order": list(beats.keys()),
        "image_overrides": {},
    }, indent=2))
    return event_dir, storyboard, "Event_SWAPTEST"


def _start_server(event_dir: Path, storyboard: Path, event_id: str, port: int):
    state_mgr = PS.StateManager(event_dir, event_id)
    app = PS.AppContext(
        event_dir=event_dir, storyboard_path=storyboard,
        event_id=event_id, state=state_mgr, client=None,
    )
    if not hasattr(app, "touch"):
        app.touch = lambda: None  # type: ignore[attr-defined]
    server = PS.ProductionServer(("127.0.0.1", port), app)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return server, t, app
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server failed to start")


def _http_post(port: int, path: str, body: dict, timeout: float = 10.0):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw.decode("utf-8"))
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
class TestSwapToA(unittest.TestCase):
    """Full behavioral coverage of /api/v2/beat/<beat_id>/swap_to_a."""

    def _setup_with(self, beats: dict | None = None):
        self.tmp = Path(tempfile.mkdtemp(prefix="swaptoa_"))
        self.event_dir, self.sb, self.event_id = _make_event_fixture(self.tmp, beats=beats)
        self.port = _find_free_port()
        PS._PATCH_STATE_DEDUP.clear()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.sb, self.event_id, self.port,
        )

    def setUp(self) -> None:
        self._setup_with()

    def tearDown(self) -> None:
        try:
            self.server.shutdown(); self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # 1. Full content swap (files, task_ids, size, source, end_frame_prompt)
    # ------------------------------------------------------------------
    def test_swap_b_to_a_moves_option_content(self):
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["status"], "swapped")
        self.assertEqual(resp["from_slot"], 2)
        self.assertEqual(resp["to_slot"], 1)

        state = self.app.state.read_state()
        opts = state["beats"]["beat_01"]["phase_1"]["options"]
        # Slot 0 (A) now holds what used to be in slot 1 (B).
        self.assertEqual(opts[0]["file"], "beat_01_option_2.mp4")
        self.assertEqual(opts[0]["task_id"], "task_B")
        self.assertEqual(opts[0]["size_bytes"], 1_200_000)
        self.assertEqual(opts[0]["source"], "kling_v3_pro")
        self.assertEqual(opts[0]["end_frame_prompt"], "end frame for beat_01_option_2.mp4")
        # Slot 1 (B) now holds what used to be in slot 0 (A).
        self.assertEqual(opts[1]["file"], "beat_01_option_1.mp4")
        self.assertEqual(opts[1]["task_id"], "task_A")
        self.assertEqual(opts[1]["size_bytes"], 1_000_000)
        # Slot 2 (C) untouched.
        self.assertEqual(opts[2]["file"], "beat_01_option_3.mp4")
        self.assertEqual(opts[2]["task_id"], "task_C")

    # ------------------------------------------------------------------
    # 2. selected_option toggles N <-> 1
    # ------------------------------------------------------------------
    def test_swap_updates_selected_option(self):
        # Case A: selected=2, swap from_slot=2 => selected becomes 1.
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["new_selected_option"], 1)
        state = self.app.state.read_state()
        self.assertEqual(state["beats"]["beat_01"]["phase_1"]["selected_option"], 1)

        # Case B: setup fresh with selected=1, swap from_slot=3 => selected becomes 3.
        self.tearDown()
        self._setup_with(beats={
            "beat_01": {
                "text": "hello",
                "phase_1": {
                    "status": "completed",
                    "selected_option": 1,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        _option("beat_01_option_2.mp4", "task_B", 1_200_000),
                        _option("beat_01_option_3.mp4", "task_C", 1_100_000),
                    ],
                },
                "_version": 1,
            },
        })
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 3})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["new_selected_option"], 3)
        state = self.app.state.read_state()
        self.assertEqual(state["beats"]["beat_01"]["phase_1"]["selected_option"], 3)

    def test_swap_preserves_unrelated_selected_option(self):
        # selected=3, swap from_slot=2 => selected should remain 3.
        self.tearDown()
        self._setup_with(beats={
            "beat_01": {
                "text": "hello",
                "phase_1": {
                    "status": "completed",
                    "selected_option": 3,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        _option("beat_01_option_2.mp4", "task_B", 1_200_000),
                        _option("beat_01_option_3.mp4", "task_C", 1_100_000),
                    ],
                },
                "_version": 1,
            },
        })
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["new_selected_option"], 3)

    # ------------------------------------------------------------------
    # 3. lipsync.source_option toggles N <-> 1
    # ------------------------------------------------------------------
    def test_swap_updates_lipsync_source_option(self):
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["new_source_option"], 1)
        state = self.app.state.read_state()
        self.assertEqual(state["beats"]["beat_01"]["lipsync"]["source_option"], 1)

    # ------------------------------------------------------------------
    # 4. swap from slot C works same as slot B
    # ------------------------------------------------------------------
    def test_swap_from_c_to_a_works(self):
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 3})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["from_slot"], 3)
        state = self.app.state.read_state()
        opts = state["beats"]["beat_01"]["phase_1"]["options"]
        # Slot 0 (A) now holds old slot 2 (C).
        self.assertEqual(opts[0]["file"], "beat_01_option_3.mp4")
        self.assertEqual(opts[0]["task_id"], "task_C")
        # Slot 2 (C) now holds old slot 0 (A).
        self.assertEqual(opts[2]["file"], "beat_01_option_1.mp4")
        self.assertEqual(opts[2]["task_id"], "task_A")
        # Slot 1 (B) untouched.
        self.assertEqual(opts[1]["file"], "beat_01_option_2.mp4")
        self.assertEqual(opts[1]["task_id"], "task_B")

    # ------------------------------------------------------------------
    # 4b. Slot 4 (Option D) works on a beat with 4+ options — follow-up
    # fix 2026-04-19: beat_05 has 4 options, beat_06 has 6, beat_11 has 5
    # due to Regenerate-B+C adding without replacing. Validation must not
    # hardcode a 2-or-3 cap.
    # ------------------------------------------------------------------
    def test_swap_from_slot_4_works_when_beat_has_4_options(self):
        self.tearDown()
        self._setup_with(beats={
            "beat_01": {
                "text": "four-opt beat",
                "phase_1": {
                    "status": "completed",
                    "selected_option": 4,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        _option("beat_01_option_2.mp4", "task_B", 1_200_000),
                        _option("beat_01_option_3.mp4", "task_C", 1_100_000),
                        _option("beat_01_option_4.mp4", "task_D", 1_300_000),
                    ],
                },
                "lipsync": {
                    "status": "completed",
                    "source_option": 4,
                    "file": "beat_01_lipsync.mp4",
                },
                "_version": 1,
            },
        })
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 4})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp["from_slot"], 4)
        self.assertEqual(resp["new_selected_option"], 1)
        self.assertEqual(resp["new_source_option"], 1)
        state = self.app.state.read_state()
        opts = state["beats"]["beat_01"]["phase_1"]["options"]
        self.assertEqual(opts[0]["file"], "beat_01_option_4.mp4")
        self.assertEqual(opts[0]["task_id"], "task_D")
        self.assertEqual(opts[3]["file"], "beat_01_option_1.mp4")
        self.assertEqual(opts[3]["task_id"], "task_A")

    # ------------------------------------------------------------------
    # 5. Invalid from_slot (<2, non-int, missing) returns 400. Slots >=2
    # that exceed the beat's actual option count are covered by the
    # separate 'too_few_options' test.
    # ------------------------------------------------------------------
    def test_swap_rejects_invalid_slot(self):
        # from_slot=1 is invalid — slot 1 is already A.
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 1})
        self.assertEqual(status, 400, resp)
        self.assertIn("error", resp)
        self.assertIn("hint", resp)

        # from_slot=0 and negative are invalid.
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 0})
        self.assertEqual(status, 400, resp)

        # Missing from_slot field.
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {})
        self.assertEqual(status, 400, resp)

        # Non-int from_slot.
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": "two"})
        self.assertEqual(status, 400, resp)

    # ------------------------------------------------------------------
    # 6. Beat doesn't exist returns 400
    # ------------------------------------------------------------------
    def test_swap_rejects_missing_beat(self):
        status, resp = _http_post(self.port, "/api/v2/beat/beat_99/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 400, resp)
        self.assertIn("error", resp)
        self.assertIn("hint", resp)
        self.assertIn("not found", resp["error"])

    # ------------------------------------------------------------------
    # 7. Option at from_slot - 1 has no file returns 400
    # ------------------------------------------------------------------
    def test_swap_rejects_empty_option(self):
        self.tearDown()
        self._setup_with(beats={
            "beat_01": {
                "text": "hello",
                "phase_1": {
                    "status": "partial",
                    "selected_option": 1,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        # Slot 2 is empty (no file) — should reject.
                        {"status": "pending"},
                        _option("beat_01_option_3.mp4", "task_C", 1_100_000),
                    ],
                },
                "_version": 1,
            },
        })
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 400, resp)
        self.assertIn("error", resp)
        self.assertIn("empty", resp["error"])

    def test_swap_rejects_too_few_options(self):
        # Beat has only 2 options; swapping from slot 3 should fail.
        self.tearDown()
        self._setup_with(beats={
            "beat_01": {
                "text": "hello",
                "phase_1": {
                    "status": "partial",
                    "selected_option": 1,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        _option("beat_01_option_2.mp4", "task_B", 1_200_000),
                    ],
                },
                "_version": 1,
            },
        })
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 3})
        self.assertEqual(status, 400, resp)
        self.assertIn("hint", resp)

    # ------------------------------------------------------------------
    # 8. source_changed flag is cleared (audio_changed too)
    # ------------------------------------------------------------------
    def test_swap_clears_source_changed_flag(self):
        self.tearDown()
        self._setup_with(beats={
            "beat_01": {
                "text": "hello",
                "phase_1": {
                    "status": "completed",
                    "selected_option": 2,
                    "options": [
                        _option("beat_01_option_1.mp4", "task_A", 1_000_000),
                        _option("beat_01_option_2.mp4", "task_B", 1_200_000),
                        _option("beat_01_option_3.mp4", "task_C", 1_100_000),
                    ],
                },
                "lipsync": {
                    "status": "completed",
                    "source_option": 2,
                    "source_changed": True,  # stale flag set
                    "audio_changed": True,   # stale flag set
                    "file": "beat_01_lipsync.mp4",
                },
                "_version": 5,
            },
        })
        status, resp = _http_post(self.port, "/api/v2/beat/beat_01/swap_to_a",
                                  {"from_slot": 2})
        self.assertEqual(status, 200, resp)
        state = self.app.state.read_state()
        ls = state["beats"]["beat_01"]["lipsync"]
        self.assertFalse(ls["source_changed"], "source_changed should be cleared after swap")
        self.assertFalse(ls["audio_changed"], "audio_changed should be cleared after swap")
        # source_option should have moved from 2 -> 1.
        self.assertEqual(ls["source_option"], 1)
        # Lipsync file reference unchanged (content is unchanged, just slot).
        self.assertEqual(ls["file"], "beat_01_lipsync.mp4")


if __name__ == "__main__":
    unittest.main()
