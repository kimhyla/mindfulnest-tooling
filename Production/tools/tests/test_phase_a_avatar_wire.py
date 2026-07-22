"""Phase A ByteDance base-clip route — handler contract + HTTP integration."""
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
from phase_a_arlo_contract import PHASE_A_ARLO_BASE_CLIP_CANONICAL  # noqa: E402

# Module may already be imported by earlier tests without the env flag.
PS.SINGLE_MACHINE_MODE = True


def test_phases_handler_uses_bytedance_not_layered():
    src = TOOLS / "server_handlers" / "phases.py"
    block = src.read_text(encoding="utf-8").split("def handle_phase_a_lipsync", 1)[1]
    block = block.split("\ndef handle_phase_b_lipsync", 1)[0]
    assert "submit_avatar_pro" not in block
    assert "run_phase_a_arlo_idle_lipsync_startend_still" not in block
    assert "execute_layered_job" not in block
    assert "create_layered_job" not in block
    assert "run_phase_a_base_clip_bytedance_lipsync" in block
    assert "PHASE_A_BYTEDANCE_METHOD" in block or "base_clip_bytedance_tight_v1" in block
    assert "_finalize_phase_a_lipsync_delivery" in block
    assert 'needs_manual_visual_review' in block


def test_phase_a_resume_wired_not_orphan_default():
    phases = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    assert "def sweep_phase_a_lipsync_resume" in phases
    assert "def reconcile_phase_a_layered_lipsync" in phases  # available, not Send default
    assert "def sweep_phase_a_lipsync_orphan" not in phases
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "sweep_phase_a_lipsync_resume" in server
    assert "sweep_phase_a_lipsync_orphan" not in server
    assert "reconcile_phase_b_layered_lipsync" in server


def _make_event_fixture(tmp: Path) -> tuple[Path, Path, str]:
    proj = tmp / "Claude Mindfulnest Project Files"
    bases = proj / "Production" / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)
    (bases / f"{PHASE_A_ARLO_BASE_CLIP_CANONICAL}.mp4").write_bytes(b"\x00fake_arlo_idle\x00")
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


class TestPhaseABytedanceHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phase_a_bytedance_"))
        self.event_dir, self.storyboard, self.event_id = _make_event_fixture(self.tmp)
        self.port = _find_free_port()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.storyboard, self.event_id, self.port,
        )

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)

    def test_lipsync_submits_bytedance_worker(self):
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

        def _fake_bytedance(base_video, audio_raw, out_path, **kwargs):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\x00bytedance_out\x00")
            return {
                "method": "base_clip_bytedance_tight_v1",
                "base_clip": base_video.name,
                "output": out_path.name,
            }

        with mock.patch.object(PS.subprocess, "run", side_effect=dispatch), \
             mock.patch(
                 "phase_a_middle_permanent.run_phase_a_base_clip_bytedance_lipsync",
                 side_effect=_fake_bytedance,
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
                {"phase": "a"},
            )
            self.assertEqual(status, 202, resp)
            self.assertEqual(resp.get("status"), "running")
            self.assertEqual(resp.get("vendor"), "base_clip_bytedance_tight_v1")
            self.assertEqual(resp.get("base_clip_id"), PHASE_A_ARLO_BASE_CLIP_CANONICAL)

            for _ in range(80):
                state = self.app.state.read_state()
                if state.get("phase_a_lipsync_status") == "needs_manual_visual_review":
                    break
                time.sleep(0.05)

        state = self.app.state.read_state()
        self.assertEqual(state.get("phase_a_lipsync_status"), "needs_manual_visual_review")
        self.assertEqual(
            state.get("phase_a_lipsync_method"),
            "base_clip_bytedance_tight_v1",
        )
        self.assertTrue(state.get("phase_a_lipsync_file", "").startswith("phase_a_lipsync_"))


if __name__ == "__main__":
    unittest.main()
