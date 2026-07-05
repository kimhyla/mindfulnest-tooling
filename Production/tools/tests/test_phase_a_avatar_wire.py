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


def test_phases_handler_uses_arlo_startend_kling_not_avatar_pro():
    src = TOOLS / "server_handlers" / "phases.py"
    block = src.read_text(encoding="utf-8").split("def handle_phase_a_lipsync", 1)[1]
    block = block.split("\ndef handle_phase_b_lipsync", 1)[0]
    assert "submit_avatar_pro" not in block
    assert "run_phase_a_arlo_idle_lipsync_startend_still" in block
    assert "_finalize_phase_a_lipsync_delivery" in block
    assert 'lipsync_method = "idle_kling_lipsync_startend_still"' in block


def test_sweep_resume_arlo_startend_not_bytedance():
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    resume = src.split("def sweep_phase_a_lipsync_resume", 1)[1].split("\ndef handle_phase_a_lipsync", 1)[0]
    assert "run_phase_a_arlo_idle_lipsync_startend_still" in resume
    assert "resubmit with Avatar Pro" not in resume


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

    def test_lipsync_submits_arlo_startend_worker(self):
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

        def _fake_arlo_startend(_audio, out_path, **_kw):
            Path(out_path).write_bytes(b"\x00arlo_startend_out\x00")
            return {"method": "idle_kling_lipsync_startend_still"}

        with mock.patch.object(PS.subprocess, "run", side_effect=dispatch), \
             mock.patch(
                 "phase_a_arlo_idle_lipsync.run_phase_a_arlo_idle_lipsync_startend_still",
                 side_effect=_fake_arlo_startend,
             ), \
             mock.patch(
                 "phase_a_av_post.av_duration_gap",
                 return_value=(23.0, 23.0, 0.0),
             ), \
             mock.patch(
                 "phase_a_middle_permanent.extract_qa_frames",
                 return_value=None,
             ), \
             mock.patch(
                 "server_handlers.phases._finalize_phase_a_lipsync_delivery",
                 return_value={
                     "delivery_profile": "voice_first_upscale",
                     "delivery_recipe": "PHASE_MODULE_LIPSYNC_DELIVERY_V2",
                     "width": 1280,
                     "height": 720,
                 },
             ):
            status, resp, _ = _http_post(
                self.port,
                "/api/phase_a/lipsync",
                {"phase": "a", "base_clip_id": "arlo_idle_wizard_desk_v8"},
            )
            self.assertEqual(status, 202, resp)
            self.assertEqual(resp.get("status"), "running")
            self.assertEqual(resp.get("vendor"), "idle_kling_lipsync_startend_still")

            for _ in range(50):
                state = self.app.state.read_state()
                if state.get("phase_a_lipsync_status") == "needs_manual_visual_review":
                    break
                time.sleep(0.05)

        state = self.app.state.read_state()
        self.assertEqual(state.get("phase_a_lipsync_status"), "needs_manual_visual_review")
        self.assertEqual(state.get("phase_a_lipsync_method"), "idle_kling_lipsync_startend_still")
        self.assertTrue(state.get("phase_a_lipsync_file", "").startswith("phase_a_lipsync_"))


if __name__ == "__main__":
    unittest.main()
