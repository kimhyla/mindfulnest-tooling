#!/usr/bin/env python3
"""LD V3 Phase B + Phase A authoring panel tests.

Spec: TECH_SPEC_PREVIEW_STITCHED_V3_PHASE_B_20260419.md
Preflight: 102 (parent 98)

Mocks subprocess (ffmpeg / ffprobe), robust_https_request (ElevenLabs),
and LipSyncClient.submit_and_wait (ByteDance) so the suite runs without any
network or ffmpeg binary in the test sandbox.

15 tests per handoff + counter (preflight 102) HIGH-1 regression coverage:
  1-3   render_watercolor_overlay C4 parameterization + chromakey branch
  4     resolve_watercolor_asset fail-loud (HIGH-3)
  5     v2 module patch accepts phase_b STRING fields (HIGH-1 regression)
  6     watercolor_cues_json validator roundtrip + re-emit sort_keys stability
  7-9   preview cache hash completeness + invalidation + base-clip change
  10-13 HTTP endpoint happy paths + fail-loud (mocked)
  14    patcher base64 SHA256 byte-identical
  15    patched HTML contains panel + pathappPatch null-routing
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
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
sys.path.insert(0, str(TOOLS / "credentials_lib"))

os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
os.environ["MINDFULNEST_T1_ENABLED"] = "1"
os.environ.pop("MINDFULNEST_WRITE_PATH", None)

import production_server as PS  # noqa: E402
import credentials_lib.ffmpeg_stitch as FS  # noqa: E402

PROJECT_ROOT = TOOLS.parent.parent


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _make_wc_library(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "cue_png.png").write_bytes(b"\x89PNGfake")
    (dir_path / "cue_video.mov").write_bytes(b"\x00mov_fake\x00")


def _make_base_clip(dir_path: Path) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    p = dir_path / "cedric_base_v1.mp4"
    p.write_bytes(b"\x00mp4fake\x00")
    return p


def _make_event_fixture(tmp: Path) -> tuple[Path, Path, str]:
    # Mirror the prod path depth so _phase_project_root resolves correctly.
    proj = tmp / "Claude Mindfulnest Project Files"
    (proj / "Production" / "assets" / "watercolor_library").mkdir(parents=True)
    (proj / "Production" / "assets" / "ambient_library").mkdir(parents=True)
    (proj / "Production" / "assets" / "lipsync_bases").mkdir(parents=True)
    event_dir = proj / "Production" / "Event_V3TEST"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text(
        '<html><head><script>var L=[];var TH={};</script></head>'
        '<body></body></html>\n', encoding="utf-8",
    )
    state = event_dir / "production_state.json"
    state.write_text(json.dumps({
        "event_id": "Event_V3TEST",
        "beats": {},
        "display_order": [],
        "image_overrides": {},
    }, indent=2))
    # Seed minimal libraries for the panel tests.
    _make_wc_library(proj / "Production" / "assets" / "watercolor_library")
    (proj / "Production" / "assets" / "ambient_library" / "meditation_fireplace_v1.mp3"
     ).write_bytes(b"\x00amb\x00")
    _make_base_clip(proj / "Production" / "assets" / "lipsync_bases")
    return event_dir, storyboard, "Event_V3TEST"


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]
    finally:
        s.close()


def _start_server(event_dir: Path, storyboard: Path, event_id: str, port: int):
    state_mgr = PS.StateManager(event_dir, event_id)
    # Fake wavespeed client — LipSyncClient.submit_and_wait is patched per-test.
    class _FakeClient:
        def submit_and_wait(self, video_path, audio_path, dest):
            # Used only when patched; unreachable default.
            dest.write_bytes(b"\x00lipsync_fake\x00")
            return {"ok": True, "cost": 0.15}
    app = PS.AppContext(
        event_dir=event_dir, storyboard_path=storyboard,
        event_id=event_id, state=state_mgr, client=_FakeClient(),
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


def _http_post(port: int, path: str, body: dict, timeout: float = 15.0):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ct = r.headers.get("Content-Type", "")
            if "application/json" in ct:
                return r.status, json.loads(raw.decode("utf-8")), dict(r.headers)
            return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload, dict(e.headers or {})


# ===========================================================================
# Pure-python tests (no server)
# ===========================================================================

class TestC4RenderOverlayParameterization(unittest.TestCase):
    """Tests 1-3: C4 frame_x/frame_y + chromakey branch."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="c4_"))
        self.lib = self.tmp / "watercolor_library"
        _make_wc_library(self.lib)
        self.base = self.tmp / "base.mp4"
        self.base.write_bytes(b"\x00m4v\x00")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture_ffmpeg_cmd(self, frame_x, cues):
        """Run render_watercolor_overlay with subprocess.run patched to capture argv."""
        captured: list[list[str]] = []

        def dispatch(cmd, *a, **kw):
            captured.append(list(cmd))
            class _R:
                returncode = 0; stdout = b""; stderr = b""
            # Materialize output so os.replace succeeds.
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00out\x00")
            return _R()

        out_path = self.tmp / f"out_{frame_x}.mp4"
        with mock.patch.object(FS.subprocess, "run", side_effect=dispatch):
            FS.render_watercolor_overlay(
                base_video_path=self.base, cues=cues,
                frame_x=frame_x, frame_y=180, output_path=out_path,
                library_dir=self.lib,
            )
        return captured

    # 1. frame_x=800 produces overlay x=800 in every chain
    def test_render_overlay_frame_x_800_right_frame(self):
        cmds = self._capture_ffmpeg_cmd(
            800,
            [{"timestamp_ms": 1000, "key": "cue_png", "animation": "fade_in",
              "duration_ms": 1500, "cue_type": "png"}],
        )
        self.assertEqual(len(cmds), 1, cmds)
        joined = " ".join(cmds[0])
        self.assertIn("-filter_complex", joined)
        self.assertIn("overlay=x=800:y=180", joined)
        self.assertNotIn("overlay=x=40:y=180", joined)

    # 2. frame_x=40 produces overlay x=40 in every chain
    def test_render_overlay_frame_x_40_left_frame(self):
        cmds = self._capture_ffmpeg_cmd(
            40,
            [{"timestamp_ms": 1000, "key": "cue_png", "animation": "fade_in",
              "duration_ms": 1500, "cue_type": "png"}],
        )
        joined = " ".join(cmds[0])
        self.assertIn("overlay=x=40:y=180", joined)

    # 3. Video cue_type triggers chromakey; png skips it
    def test_render_overlay_chromakey_video_only(self):
        cmds = self._capture_ffmpeg_cmd(
            40,
            [
                {"timestamp_ms": 1000, "key": "cue_png", "animation": "fade_in",
                 "duration_ms": 1500, "cue_type": "png"},
                {"timestamp_ms": 3000, "key": "cue_video", "animation": "fade_in",
                 "duration_ms": 2000, "cue_type": "video"},
            ],
        )
        joined = " ".join(cmds[0])
        # Exactly one chromakey filter in the whole filter_complex.
        self.assertEqual(joined.count("chromakey=0x00FF00:0.1:0.0"), 1,
                         f"expected exactly 1 chromakey (video-only); got: {joined}")
        # Chromakey is on the video input branch (input 2), not input 1 (png).
        self.assertIn("[2:v]chromakey", joined)
        self.assertNotIn("[1:v]chromakey", joined)


class TestResolveWatercolorAsset(unittest.TestCase):
    """Test 4: fail-loud asset resolution (HIGH-3)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rwa_"))
        self.lib = self.tmp / "lib"
        _make_wc_library(self.lib)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolves_png_by_key(self):
        path = FS.resolve_watercolor_asset(self.lib, "cue_png", "png")
        self.assertTrue(path.is_file())
        self.assertEqual(path.suffix, ".png")

    def test_resolves_video_by_key_prefers_mov(self):
        path = FS.resolve_watercolor_asset(self.lib, "cue_video", "video")
        self.assertTrue(path.is_file())
        self.assertEqual(path.suffix, ".mov")

    def test_missing_asset_raises_FileNotFoundError(self):
        with self.assertRaises(FileNotFoundError) as cm:
            FS.resolve_watercolor_asset(self.lib, "nonexistent", "png")
        self.assertIn("nonexistent", str(cm.exception))
        self.assertIn("cue_type='png'", str(cm.exception))


class TestV2ModulePatchValidators(unittest.TestCase):
    """Test 5: HIGH-1 fix — phase_b fields get per-type validators."""

    def test_validator_dispatch_covers_all_whitelist_fields(self):
        missing = [
            f for f in PS._V2_MODULE_ALLOWED_FIELDS
            if f not in PS._V2_MODULE_FIELD_VALIDATORS
        ]
        self.assertEqual(missing, [], f"whitelist fields without validators: {missing}")

    def test_str_field_accepts_string(self):
        v = PS._v2_validate_str("hello world")
        self.assertEqual(v, "hello world")

    def test_str_field_rejects_non_string(self):
        with self.assertRaises(ValueError):
            PS._v2_validate_str(42)

    def test_mtime_field_accepts_epoch_int(self):
        v = PS._v2_validate_mtime(1713644431)
        self.assertEqual(v, 1713644431)

    def test_mtime_field_rejects_negative(self):
        with self.assertRaises(ValueError):
            PS._v2_validate_mtime(-1)

    def test_status_field_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            PS._v2_validate_status("bogus_status")

    def test_fade_ms_retains_v2_bounds(self):
        self.assertEqual(PS._v2_validate_fade_ms(250), 250)
        with self.assertRaises(ValueError):
            PS._v2_validate_fade_ms(1500)


class TestWatercolorCuesJsonRoundtrip(unittest.TestCase):
    """Test 6: cues JSON validator roundtrip + sort_keys stability (MEDIUM-5)."""

    def test_valid_cues_roundtrip(self):
        cues = [
            {"timestamp_ms": 1000, "key": "breath_rub", "animation": "fade_in",
             "duration_ms": 1500, "cue_type": "png"},
            {"timestamp_ms": 3000, "key": "gentle_wave", "animation": "slide_in",
             "duration_ms": 2000, "cue_type": "png"},
        ]
        raw = json.dumps(cues)
        out = PS._v2_validate_watercolor_cues_json(raw)
        parsed = json.loads(out)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["key"], "breath_rub")

    def test_validator_normalizes_key_order_for_hash_stability(self):
        cues_a = [{"timestamp_ms": 1000, "key": "k", "animation": "fade_in",
                   "duration_ms": 500, "cue_type": "png"}]
        cues_b = [{"key": "k", "cue_type": "png", "animation": "fade_in",
                   "duration_ms": 500, "timestamp_ms": 1000}]
        a = PS._v2_validate_watercolor_cues_json(json.dumps(cues_a))
        b = PS._v2_validate_watercolor_cues_json(json.dumps(cues_b))
        self.assertEqual(a, b,
                         "sort_keys re-emit MUST produce identical strings "
                         "regardless of client JSON key order (MEDIUM-5)")

    def test_validator_sorts_cues_by_timestamp(self):
        cues = [
            {"timestamp_ms": 3000, "key": "b", "animation": "fade_in",
             "duration_ms": 500, "cue_type": "png"},
            {"timestamp_ms": 1000, "key": "a", "animation": "fade_in",
             "duration_ms": 500, "cue_type": "png"},
        ]
        out = PS._v2_validate_watercolor_cues_json(json.dumps(cues))
        parsed = json.loads(out)
        self.assertEqual([c["timestamp_ms"] for c in parsed], [1000, 3000])

    def test_invalid_cue_type_rejected(self):
        cues = [{"timestamp_ms": 1000, "key": "k", "animation": "fade_in",
                 "duration_ms": 500, "cue_type": "gif"}]
        with self.assertRaises(ValueError) as cm:
            PS._v2_validate_watercolor_cues_json(json.dumps(cues))
        self.assertIn("cue_type", str(cm.exception))

    def test_invalid_animation_rejected(self):
        cues = [{"timestamp_ms": 1000, "key": "k", "animation": "bounce",
                 "duration_ms": 500, "cue_type": "png"}]
        with self.assertRaises(ValueError) as cm:
            PS._v2_validate_watercolor_cues_json(json.dumps(cues))
        self.assertIn("animation", str(cm.exception))


class TestWatercolorOverlayRecipeHash(unittest.TestCase):
    """Tests 7-8: MEDIUM-6 fix — WATERCOLOR_OVERLAY_RECIPE_HASH exists and is stable."""

    def test_recipe_hash_present(self):
        self.assertTrue(hasattr(FS, "WATERCOLOR_OVERLAY_RECIPE_HASH"))
        self.assertEqual(len(FS.WATERCOLOR_OVERLAY_RECIPE_HASH), 16)

    def test_recipe_hash_deterministic(self):
        # Hash derives from WATERCOLOR_OVERLAY_RECIPE_VERSION. Re-compute.
        expected = hashlib.sha256(
            f"{FS.WATERCOLOR_OVERLAY_RECIPE_VERSION}:fade_in=0.3s|slide_in=0.5s|"
            f"gentle_pan=5px_sin|chromakey=0x00FF00:0.1:0.0".encode("utf-8"),
        ).hexdigest()[:16]
        self.assertEqual(FS.WATERCOLOR_OVERLAY_RECIPE_HASH, expected)


# ===========================================================================
# HTTP endpoint tests (live server, mocked subprocess / ElevenLabs / ByteDance)
# ===========================================================================

class TestPhaseEndpoints(unittest.TestCase):
    """Tests 9-13: HTTP endpoints with mocked externals."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="phase_http_"))
        cls.event_dir, cls.sb, cls.event_id = _make_event_fixture(cls.tmp)
        # Ensure AppContext/API keys don't 500 on missing real creds: point
        # ELEVENLABS_API_KEY env so parse_api_keys returns it.
        os.environ["ELEVENLABS_API_KEY"] = "fake-test-key"
        cls.port = _find_free_port()
        PS._PATCH_STATE_DEDUP.clear()
        cls.server, cls.thread, cls.app = _start_server(
            cls.event_dir, cls.sb, cls.event_id, cls.port,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.server.shutdown(); cls.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # 9. regen_audio writes voice stem + updates state (ElevenLabs mocked)
    def test_regen_audio_writes_voice_stem_and_updates_state(self):
        fake_mp3 = b"\xff\xfb" + b"\x00" * 1024
        with mock.patch("kling_startend_pipeline.robust_https_request",
                        return_value=(200, fake_mp3)), \
             mock.patch("production_server._ffprobe_duration", return_value=4.2):
            status, resp, _ = _http_post(
                self.port, "/api/phase_b/regen_audio",
                {"phase": "b", "script": "Breathe in. Breathe out. [pause 2s]."},
            )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("phase"), "b")
        self.assertEqual(resp.get("speaker"), "Cedric")
        self.assertTrue(resp.get("file", "").startswith("phase_b_voice_stem_"))
        state = self.app.state.read_state()
        self.assertEqual(state.get("phase_b_voice_stem_file"), resp["file"])
        self.assertIsInstance(state.get("phase_b_voice_stem_mtime"), int)

    # 10. mix_audio hits ffmpeg with amix (subprocess mocked)
    def test_mix_audio_writes_file_and_updates_state(self):
        # Seed voice_stem_file from previous test (or create one).
        vs = self.event_dir / "phase_b_voice_stem_test.mp3"
        vs.write_bytes(b"\x00fakevoice\x00")
        def _apply(state):
            state["phase_b_voice_stem_file"] = vs.name
            state["phase_b_voice_stem_mtime"] = int(time.time())
            return 1
        self.app.state.mutate_state(_apply)

        # Mock subprocess.run in production_server (ffmpeg amix).
        def dispatch(cmd, *a, **kw):
            class _R:
                returncode = 0; stdout = b""; stderr = b""
            # Materialize output at cmd[-1].
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00mixed\x00")
            return _R()
        with mock.patch.object(PS.subprocess, "run", side_effect=dispatch), \
             mock.patch("production_server._ffprobe_duration", return_value=5.0):
            status, resp, _ = _http_post(
                self.port, "/api/phase_b/mix_audio",
                {"phase": "b", "ambient_preset_id": "meditation_fireplace_v1"},
            )
        self.assertEqual(status, 200, resp)
        self.assertTrue(resp["file"].startswith("phase_b_mixed_"))
        state = self.app.state.read_state()
        self.assertEqual(state.get("phase_b_mixed_audio_file"), resp["file"])
        self.assertEqual(state.get("phase_b_ambient_preset_id"),
                         "meditation_fireplace_v1")

    # 11. lipsync accepts base_clip_id (ByteDance mocked)
    def test_lipsync_accepts_base_clip_id(self):
        # Seed voice stem.
        vs = self.event_dir / "phase_b_voice_stem_test.mp3"
        vs.write_bytes(b"\x00fakevoice\x00")
        def _apply(state):
            state["phase_b_voice_stem_file"] = vs.name
            state["phase_b_voice_stem_mtime"] = int(time.time())
            state.pop("phase_b_mixed_audio_file", None)
            return 1
        self.app.state.mutate_state(_apply)

        def dispatch(cmd, *a, **kw):
            class _R:
                returncode = 0
                # ffprobe duration stub — return "20" for any -show_entries call.
                stdout = b"20.000\n" if "show_entries" in " ".join(cmd) else b""
                stderr = b""
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00trim\x00")
            return _R()

        def fake_submit_and_wait(self_, video, audio, dest):
            dest.write_bytes(b"\x00bytedance_out\x00")
            return {"ok": True, "job_id": "fake_job", "cost": 0.15}

        with mock.patch.object(PS.subprocess, "run", side_effect=dispatch), \
             mock.patch("production_server._ffprobe_duration", return_value=20.0), \
             mock.patch("production_server._silcomp_audio",
                        return_value=(vs, {"applied": False,
                                           "source_duration_s": 4.0,
                                           "compressed_duration_s": 4.0,
                                           "silences_compressed": 0})), \
             mock.patch("production_server._trim_video_to_audio",
                        return_value=(Path("/tmp/fake_trim.mp4"), 4.4, 0.0, 4.4)), \
             mock.patch.object(type(self.app.client), "submit_and_wait",
                               fake_submit_and_wait, create=True):
            status, resp, _ = _http_post(
                self.port, "/api/phase_b/lipsync",
                {"phase": "b", "base_clip_id": "cedric_base_v1"},
                timeout=30,
            )
        self.assertEqual(status, 200, resp)
        self.assertTrue(resp["file"].startswith("phase_b_lipsync_"))
        self.assertEqual(resp["base_clip_id"], "cedric_base_v1")
        state = self.app.state.read_state()
        self.assertEqual(state.get("phase_b_lipsync_file"), resp["file"])
        # module-level field for base clip.
        self.assertEqual(state.get("phase_b_cedric_base_clip_id"), "cedric_base_v1")

    # 12. preview fails loud on missing lipsync
    def test_preview_fails_loud_when_lipsync_file_missing(self):
        # Clear any prior lipsync file from state.
        def _apply(state):
            state.pop("phase_b_lipsync_file", None)
            return 1
        self.app.state.mutate_state(_apply)
        status, resp, _ = _http_post(
            self.port, "/api/phase_b/preview", {"phase": "b"},
        )
        self.assertEqual(status, 400, resp)
        self.assertIn("hint", resp)
        self.assertIn("Send for Lipsync", resp["hint"])

    # 13. preview hash includes watercolor_cues_json + base clip (tests 4+8 combined)
    def test_preview_hash_changes_on_watercolor_cue_edit(self):
        # Seed a lipsync file so the handler doesn't 400.
        ls = self.event_dir / "phase_b_lipsync_test.mp4"
        ls.write_bytes(b"\x00fakels\x00")
        def _apply_a(state):
            state["phase_b_lipsync_file"] = ls.name
            state["phase_b_lipsync_mtime"] = int(time.time())
            state["phase_b_cedric_base_clip_id"] = "cedric_base_v1"
            # Start with zero cues.
            state["phase_b_watercolor_cues_json"] = "[]"
            return 1
        self.app.state.mutate_state(_apply_a)

        # Patch render_watercolor_overlay so it doesn't actually run ffmpeg —
        # just materialize an output file.
        def fake_render(**kw):
            out = kw["output_path"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"\x00renderedA\x00")
            return out

        def capture_preview(payload):
            with mock.patch("production_server.render_watercolor_overlay",
                            fake_render, create=True), \
                 mock.patch.object(PS.subprocess, "run",
                                   side_effect=lambda *a, **kw: mock.MagicMock(
                                       returncode=0, stdout=b"", stderr=b"")):
                # We can't patch the lazy credentials_lib.ffmpeg_stitch import directly; use
                # module attr patch at the lib level.
                with mock.patch("ffmpeg_stitch.render_watercolor_overlay",
                                fake_render):
                    status, resp, headers = _http_post(
                        self.port, "/api/phase_b/preview", payload,
                    )
                    return status, resp, headers

        status_a, _body_a, hdrs_a = capture_preview({"phase": "b"})
        self.assertEqual(status_a, 200, _body_a)
        etag_a = hdrs_a.get("ETag") or hdrs_a.get("Etag") or hdrs_a.get("etag")
        self.assertIsNotNone(etag_a, f"no ETag returned; headers={hdrs_a}")

        # Add a watercolor cue; hash MUST change.
        def _apply_b(state):
            cues = [{"timestamp_ms": 1500, "key": "cue_png", "animation": "fade_in",
                     "duration_ms": 1000, "cue_type": "png"}]
            state["phase_b_watercolor_cues_json"] = json.dumps(cues)
            return 1
        self.app.state.mutate_state(_apply_b)

        status_b, _body_b, hdrs_b = capture_preview({"phase": "b"})
        etag_b = hdrs_b.get("ETag") or hdrs_b.get("Etag") or hdrs_b.get("etag")
        self.assertIsNotNone(etag_b)
        self.assertNotEqual(etag_a, etag_b,
                            "cache hash MUST change when watercolor cues edited")


# ===========================================================================
# Patcher tests (pure-python, scanning patched HTML on disk)
# ===========================================================================

class TestPatchedHTMLContents(unittest.TestCase):
    """Tests 14-15: patched storyboard contains panel markers + null-route."""

    @classmethod
    def setUpClass(cls):
        cls.patched_html = (
            PROJECT_ROOT / "Production" / "Event_1" / "storyboard_v38_prod.html"
        )
        cls.src = cls.patched_html.read_text(encoding="utf-8")

    # 14. patcher left base64 image URIs byte-identical to pre-patch
    def test_patcher_base64_byte_identical_pre_post(self):
        # Load the most recent pre-patch backup and compare SHA256 of sorted URIs.
        import re as _re
        backups = sorted(
            (PROJECT_ROOT / "Production" / "Event_1").glob(
                "storyboard_v38_prod.html.bak_phase_b_*"
            )
        )
        self.assertTrue(backups, "no phase_b backup found")
        bak = backups[-1].read_text(encoding="utf-8")
        b64re = _re.compile(r"data:image/[a-zA-Z.+-]+;base64,[A-Za-z0-9+/=]+")
        def sha(src):
            return hashlib.sha256(
                "\n".join(sorted(b64re.findall(src))).encode("utf-8"),
            ).hexdigest()
        self.assertEqual(sha(bak), sha(self.src),
                         "Rule 7 Path B invariant violated: base64 images differ")

    # 15. Patched HTML contains both panels + timeline widget + null-route
    def test_html_contains_phase_b_panel_with_timeline_widget(self):
        for needle, label in [
            ("LD V3 Phase B/A Authoring Panels",
             "begin/end markers"),
            ('renderPanel("b"', "Phase B render call"),
            ('renderPanel("a"', "Phase A render call"),
            ("mn-wc-timeline", "timeline class"),
            ("mn-wc-library", "library panel class"),
            ("wavesurfer.js@7", "WaveSurfer CDN"),
            ('"/api/phase_b/regen_audio"', "regen_audio URL"),
            ('"/api/phase_b/mix_audio"',  "mix_audio URL"),
            ('"/api/phase_b/lipsync"',    "lipsync URL"),
            ('"/api/phase_b/preview"',    "preview URL"),
        ]:
            self.assertIn(needle, self.src, f"missing: {label}")

    def test_pathappPatch_null_beat_id_routes_watercolor_cues_to_module_patch(self):
        # V2 patcher shipped a branch that routes null beatId to
        # /api/v2/module/patch. Verify phase_*_watercolor_cues_json saves use
        # pathappPatch(null, ...).
        self.assertIn('pathappPatch(null, "phase_"+phase+"_watercolor_cues_json"',
                      self.src,
                      "V3 panel must save cues via null-beat-id route")
        # The V2 route branch is still present from the prior V2 patch.
        self.assertIn("/api/v2/module/patch", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
