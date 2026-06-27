"""Phase A Avatar Pro wire — handler contract + HTTP integration."""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock as mock
import urllib.error
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "lib"))

os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
os.environ["MINDFULNEST_T1_ENABLED"] = "1"
os.environ.pop("MINDFULNEST_WRITE_PATH", None)

import production_server as PS  # noqa: E402
from phase_a_arlo_contract import PHASE_A_ARLO_CANONICAL_STILL_REL  # noqa: E402


def test_phases_handler_uses_avatar_pro_not_bytedance():
    src = TOOLS / "server_handlers" / "phases.py"
    block = src.read_text(encoding="utf-8").split("def handle_phase_a_lipsync", 1)[1]
    block = block.split("\ndef handle_phase_b_lipsync", 1)[0]
    assert "submit_avatar_pro" in block
    assert "resolve_phase_a_arlo_avatar_still" in block
    assert "run_phase_a_base_clip_bytedance_lipsync" not in block
    assert 'lipsync_method = "base_clip_bytedance_tight_v1"' not in block


def test_sweep_polls_both_phase_a_and_phase_b():
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    assert 'for phase in ("a", "b"):' in src or "_sweep_one_phase_module_lipsync_poll" in src
    assert "PHASE_A_LIPSYNC_METHOD_AVATAR" in src


def _make_event_fixture(tmp: Path) -> tuple[Path, Path, str]:
    proj = tmp / "Claude Mindfulnest Project Files"
    still_dir = proj / "Production" / "NEW STYLE CHARACTERS" / "ARLO"
    still_dir.mkdir(parents=True, exist_ok=True)
    (still_dir / Path(PHASE_A_ARLO_CANONICAL_STILL_REL).name).write_bytes(
        b"\x89PNG\r\n\x1a\nfake_arlo_still",
    )
    event_dir = proj / "Production" / "Event_V3TEST"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text(
        '<html><head><script>var L=[];var TH={};</script></head><body></body></html>\n',
        encoding="utf-8",
    )
    (event_dir / "production_state.json").write_text(
        json.dumps(
            {
                "event_id": "Event_V3TEST",
                "version": 3,
                "videos": {"intro": {"beats": {}, "display_order": [], "image_overrides": {}}},
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

        def poll(self, _task_id):
            return {"status": "completed", "outputs": ["http://fake/avatar.mp4"]}

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


def _http_post(port: int, path: str, body: dict, timeout: float = 30.0):
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
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if "application/json" in r.headers.get("Content-Type", ""):
                return r.status, json.loads(raw.decode("utf-8")), dict(r.headers)
            return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload, dict(e.headers or {})


class TestPhaseAAvatarProHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phase_a_avatar_"))
        self.event_dir, self.storyboard, self.event_id = _make_event_fixture(self.tmp)
        self.port = _find_free_port()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.storyboard, self.event_id, self.port,
        )

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)

    def test_lipsync_submits_avatar_pro(self):
        vs = self.event_dir / "phase_a_voice_stem_test.mp3"
        vs.write_bytes(b"\x00fakevoice\x00")

        def _apply(state):
            state["phase_a_voice_stem_file"] = vs.name
            state["phase_a_voice_stem_mtime"] = int(time.time())
            return 1

        self.app.state.mutate_state(_apply)

        def dispatch(cmd, *a, **kw):
            class _R:
                returncode = 0
                stderr = b""
                stdout = b""

            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "show_entries" in cmd_str:
                _R.stdout = b"23.000\n"
            else:
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x00trim\x00")
            return _R()

        def _fake_lipsync_client(*_a, **_kw):
            class _LSC:
                def submit_avatar_pro(self, _still, _audio, _prompt):
                    return "fake_phase_a_avatar_task_id"

                def download(self, _url, dest):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(b"\x00avatar_out\x00")

            return _LSC()

        with mock.patch.object(PS.subprocess, "run", side_effect=dispatch), \
             mock.patch(
                 "phase_module_lipsync_delivery.finalize_phase_module_lipsync_delivery",
                 side_effect=lambda path, **kw: {
                     "delivery_profile": "voice_first_upscale",
                     "delivery_recipe": "PHASE_MODULE_LIPSYNC_DELIVERY_V1",
                     "raw_width": 720,
                     "raw_height": 544,
                     "width": 1280,
                     "height": 720,
                     "bitrate_bps": 1_800_000,
                     "path": str(path),
                 },
             ), \
             mock.patch("server_handlers.phases.LipSyncClient", create=True, new=_fake_lipsync_client):
            status, resp, _ = _http_post(
                self.port, "/api/phase_a/lipsync", {"phase": "a"},
            )
            self.assertEqual(status, 202, resp)
            self.assertEqual(resp.get("status"), "submitted")
            self.assertEqual(resp.get("task_id"), "fake_phase_a_avatar_task_id")
            self.assertEqual(resp.get("lipsync_method"), "kling_avatar_pro_v1")
            self.assertEqual(resp.get("lipsync_route"), "single_full_stem_v1")

            state_after = self.app.state.read_state()
            self.assertEqual(state_after.get("phase_a_lipsync_status"), "polling")
            self.assertEqual(state_after.get("phase_a_lipsync_task_id"), "fake_phase_a_avatar_task_id")
            self.assertEqual(state_after.get("phase_a_lipsync_method"), "kling_avatar_pro_v1")
            self.assertTrue(state_after.get("phase_a_avatar_still_file"))

            from server_handlers.phases import sweep_phase_module_lipsync_polls

            lipsync_file = None
            for _ in range(10):
                sweep_phase_module_lipsync_polls(self.app.state, self.app.client)
                state = self.app.state.read_state()
                lipsync_file = state.get("phase_a_lipsync_file")
                if lipsync_file:
                    break
                time.sleep(0.02)

        self.assertTrue(
            lipsync_file and lipsync_file.startswith("phase_a_lipsync_"),
            f"expected poller to finalize phase_a lipsync; state={state}",
        )
        self.assertEqual(state.get("phase_a_lipsync_status"), "done")
        self.assertNotIn("phase_a_lipsync_task_id", state)


if __name__ == "__main__":
    unittest.main()
