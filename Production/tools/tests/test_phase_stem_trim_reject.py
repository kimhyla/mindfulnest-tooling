#!/usr/bin/env python3
"""Phase A/B voice stem trim + reject lipsync tests."""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "lib"))

os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
os.environ["MINDFULNEST_T1_ENABLED"] = "1"
os.environ.pop("MINDFULNEST_WRITE_PATH", None)

import production_server as PS  # noqa: E402
from server_handlers.phases import _phase_voice_stem_trim_window  # noqa: E402


def _make_event_fixture(tmp: Path) -> tuple[Path, Path, str]:
    proj = tmp / "Claude Mindfulnest Project Files"
    (proj / "Production" / "assets" / "watercolor_library").mkdir(parents=True)
    (proj / "Production" / "assets" / "ambient_library").mkdir(parents=True)
    (proj / "Production" / "assets" / "lipsync_bases").mkdir(parents=True)
    event_dir = proj / "Production" / "Event_V3TEST"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text(
        '<html><head><script>var L=[];var TH={};</script></head>'
        '<body></body></html>\n',
        encoding="utf-8",
    )
    (event_dir / "production_state.json").write_text(
        json.dumps(
            {
                "event_id": "Event_V3TEST",
                "version": 3,
                "videos": {
                    "intro": {
                        "beats": {},
                        "display_order": [],
                        "image_overrides": {},
                    },
                },
                "phase_b_voice_stem_file": "stem.mp3",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return event_dir, storyboard, "Event_V3TEST"


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _start_server(event_dir: Path, storyboard: Path, event_id: str, port: int):
    state_mgr = PS.StateManager(event_dir, event_id)

    class _FakeClient:
        api_key = "fake_key_for_test"

        def submit_and_wait(self, video_path, audio_path, dest):
            dest.write_bytes(b"\x00lipsync_fake\x00")
            return {"ok": True, "cost": 0.15}

    app = PS.AppContext(
        event_dir=event_dir,
        storyboard_path=storyboard,
        event_id=event_id,
        state=state_mgr,
        client=_FakeClient(),
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


def _http_post(port: int, path: str, body: dict) -> tuple[int, dict, bytes]:
    body = dict(body)
    body.setdefault("event_id", "Event_V3TEST")
    body.setdefault("scope_video_role", "intro")
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, json.loads(raw.decode("utf-8")), raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8")), raw
        except Exception:
            return exc.code, {}, raw


class TestPhaseStemTrimHelpers(unittest.TestCase):
    def test_trim_window_defaults_to_zero(self):
        start, back = _phase_voice_stem_trim_window({}, "b")
        self.assertEqual((start, back), (0.0, 0.0))

    def test_trim_window_reads_state(self):
        state = {
            "phase_b_voice_stem_trim_start_s": 1.25,
            "phase_b_voice_stem_trim_back_s": 0.5,
        }
        start, back = _phase_voice_stem_trim_window(state, "b")
        self.assertEqual(start, 1.25)
        self.assertEqual(back, 0.5)

    def test_v2_validate_trim_seconds_roundtrip(self):
        self.assertEqual(PS._v2_validate_trim_seconds(1.23456), 1.235)
        with self.assertRaises(ValueError):
            PS._v2_validate_trim_seconds(-0.1)

    def test_module_patch_accepts_phase_trim_fields(self):
        for field, value in (
            ("phase_b_voice_stem_trim_start_s", 0.5),
            ("phase_b_voice_stem_trim_back_s", 1.0),
            ("phase_a_voice_stem_trim_start_s", 0.25),
            ("phase_a_voice_stem_trim_back_s", 0.75),
        ):
            validator = PS._V2_MODULE_FIELD_VALIDATORS[field]
            self.assertEqual(validator(value), round(float(value), 3))


class TestPhaseRejectLipsyncEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="phase_reject_"))
        cls.event_dir, cls.sb, cls.event_id = _make_event_fixture(cls.tmp)
        cls.port = _find_free_port()
        PS._PATCH_STATE_DEDUP.clear()
        cls.server, cls.thread, cls.app = _start_server(
            cls.event_dir, cls.sb, cls.event_id, cls.port,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_reject_lipsync_clears_state_and_archives_file(self):
        lipsync = self.event_dir / "phase_b_lipsync_test.mp4"
        lipsync.write_bytes(b"\x00mp4fake\x00")

        def _seed(state):
            state["phase_b_lipsync_file"] = lipsync.name
            state["phase_b_lipsync_mtime"] = int(time.time())
            state["phase_b_lipsync_status"] = "done"
            state["phase_b_mixed_audio_file"] = "phase_b_mixed_old.mp3"
            state["phase_b_voice_stem_trim_start_s"] = 0.4
            state["phase_b_voice_stem_trim_back_s"] = 0.2
            return 1

        self.app.state.mutate_state(_seed)

        status, resp, _ = _http_post(
            self.port,
            "/api/phase_b/reject_lipsync",
            {"phase": "b"},
        )
        self.assertEqual(status, 200, resp)
        self.assertTrue(resp.get("ok"))
        self.assertEqual(resp.get("previous_lipsync_file"), lipsync.name)

        state = self.app.state.read_state()
        self.assertNotIn("phase_b_lipsync_file", state)
        self.assertNotIn("phase_b_mixed_audio_file", state)
        self.assertEqual(state.get("phase_b_lipsync_status"), "rejected")
        self.assertTrue(state.get("phase_b_lipsync_requires_regen"))
        self.assertEqual(state.get("phase_b_voice_stem_trim_start_s"), 0.4)
        self.assertFalse(lipsync.exists())
        archived = list((self.event_dir / "_rejected_lipsync").glob("*.mp4"))
        self.assertEqual(len(archived), 1)

    def test_reject_lipsync_404_when_no_video(self):
        def _clear(state):
            state.pop("phase_b_lipsync_file", None)
            return 1

        self.app.state.mutate_state(_clear)
        status, resp, _ = _http_post(
            self.port,
            "/api/phase_b/reject_lipsync",
            {"phase": "b"},
        )
        self.assertEqual(status, 404, resp)


if __name__ == "__main__":
    unittest.main()
