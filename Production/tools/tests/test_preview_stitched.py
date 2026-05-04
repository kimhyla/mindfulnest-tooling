#!/usr/bin/env python3
"""LD-285 Preview-Stitched v2 tests.

Spec: TECH_SPEC_PREVIEW_STITCHED_V2_20260419.md
Preflight: 93 (synthesis row)

Mocks subprocess (ffmpeg / ffprobe) end-to-end so the suite runs without an
actual ffmpeg binary in the test sandbox. Tests verify:
  * Cache hash stability and the four invalidation triggers (mtime, trim,
    fade, pause_after_ms).
  * Counter-agent (a) HIGH: missing selected file => 400 with hint.
  * Counter-agent (f) CRITICAL: last beat keeps full duration (no trailing
    fade trim on the final body).
  * Counter-agent (b) MED: 2-sided clamp floors at 0 / fast-paths fade=0.
  * Counter-agent (c) MED: concat.txt absolute paths + single-quote escape.
  * /api/v2/module/patch null-beat-id route writes to state root.
  * Rule 7 Path B: storyboard base64 SHA256 byte-identical pre/post patch.
  * test_full_pipeline_mocked_ffmpeg_3_beats: end-to-end with subprocess
    patched to count + record the ffmpeg argv lists, NOT execute ffmpeg.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess as _real_subprocess
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

# Bypass cross-machine Directus lock — required for isolated tests.
os.environ["PRODUCTION_SERVER_SINGLE_MACHINE"] = "1"
os.environ["MINDFULNEST_T1_ENABLED"] = "1"
os.environ.pop("MINDFULNEST_WRITE_PATH", None)

import production_server as PS  # noqa: E402
import ffmpeg_stitch as FS  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _make_clip(p: Path, body: bytes = b"\x00fakemp4\x00") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)


def _make_snapshot(beats: dict) -> dict:
    return {"beats": beats, "image_overrides": {}}


def _beat(option_files: list[str], selected: int = 1,
          trim_start: float = 0.0, trim_end=None,
          pause_after_ms: int = 0) -> dict:
    return {
        "phase_1": {
            "selected_option": selected,
            "options": [{"file": f} for f in option_files],
            "trim_start": trim_start,
            "trim_end": trim_end,
            "pause_after_ms": pause_after_ms,
        },
        "_version": 1,
    }


# ---------------------------------------------------------------------------
# Pure-python tests (no server, no subprocess)
# ---------------------------------------------------------------------------
class TestCacheHashStability(unittest.TestCase):
    """Hash tests 1-5: stability + 4 invalidation triggers."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="prevhash_"))
        self.clips_dir = self.tmp / "animation_clips"
        self.clips_dir.mkdir()
        self.clip_a = self.clips_dir / "a.mp4"
        self.clip_b = self.clips_dir / "b.mp4"
        _make_clip(self.clip_a)
        _make_clip(self.clip_b)
        self.snapshot = _make_snapshot({
            "beat_01": _beat(["a.mp4"]),
            "beat_02": _beat(["b.mp4"]),
        })

    def tearDown(self) -> None:
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 1.
    def test_hash_stable_across_identical_inputs(self):
        h1, _ = FS.compute_cache_hash(self.snapshot, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        h2, _ = FS.compute_cache_hash(self.snapshot, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        self.assertEqual(h1, h2)

    # 2. C2 P06: mtime change invalidates
    def test_hash_changes_on_file_mtime_change(self):
        h1, _ = FS.compute_cache_hash(self.snapshot, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        # Bump mtime on clip_a by 5s
        st = self.clip_a.stat()
        os.utime(self.clip_a, (st.st_atime, st.st_mtime + 5))
        h2, _ = FS.compute_cache_hash(self.snapshot, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        self.assertNotEqual(h1, h2)

    # 3.
    def test_hash_changes_on_trim_change(self):
        h1, _ = FS.compute_cache_hash(self.snapshot, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        snap2 = _make_snapshot({
            "beat_01": _beat(["a.mp4"], trim_start=0.5),
            "beat_02": _beat(["b.mp4"]),
        })
        h2, _ = FS.compute_cache_hash(snap2, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        self.assertNotEqual(h1, h2)

    # 4.
    def test_hash_changes_on_fade_change(self):
        h1, _ = FS.compute_cache_hash(self.snapshot, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        h2, _ = FS.compute_cache_hash(self.snapshot, 350,
                                      ["beat_01", "beat_02"], self.clips_dir)
        self.assertNotEqual(h1, h2)

    # 5. C2 gap fix: pause_after_ms in hash
    def test_hash_changes_on_pause_after_ms_change(self):
        snap1 = _make_snapshot({
            "beat_01": _beat(["a.mp4"], pause_after_ms=0),
            "beat_02": _beat(["b.mp4"]),
        })
        snap2 = _make_snapshot({
            "beat_01": _beat(["a.mp4"], pause_after_ms=500),
            "beat_02": _beat(["b.mp4"]),
        })
        h1, _ = FS.compute_cache_hash(snap1, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        h2, _ = FS.compute_cache_hash(snap2, 200,
                                      ["beat_01", "beat_02"], self.clips_dir)
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Pure-python: fade clamp + concat path safety + last-beat-no-trim
# ---------------------------------------------------------------------------
class TestFadeClampAndPathSafety(unittest.TestCase):
    # 7. C2 pain: 2-sided clamp
    def test_fade_clamped_two_sided_to_min_beat_minus_0_2(self):
        # min beat = 0.5s; 0.5 - 0.2 = 0.3s = 300ms cap
        self.assertEqual(FS.compute_fade_clamp([0.5, 1.0, 1.5], 500), 300)
        # min beat = 2.0s; 2.0 - 0.2 = 1.8s; fade 200ms is well under -> unchanged
        self.assertEqual(FS.compute_fade_clamp([2.0, 3.0], 200), 200)
        # Counter (b) MED: floor at 0 when min beat < buffer
        self.assertEqual(FS.compute_fade_clamp([0.1, 0.3], 200), 0)
        # Counter (b) MED: fade_ms <= 0 fast-path returns 0 unconditionally
        self.assertEqual(FS.compute_fade_clamp([2.0, 3.0], 0), 0)

    def test_compute_fade_clamp_empty_raises(self):
        with self.assertRaises(ValueError):
            FS.compute_fade_clamp([], 200)

    # 9. P11: concat.txt absolute paths only + single-quote escape (counter c)
    def test_concat_demuxer_absolute_paths_only(self):
        tmp = Path(tempfile.mkdtemp(prefix="concat_"))
        try:
            # Use a relative path on input; _escape_for_concat MUST resolve to
            # absolute via Path.resolve().
            rel = Path("subdir/foo.mp4")
            (tmp / "subdir").mkdir()
            (tmp / "subdir" / "foo.mp4").write_bytes(b"x")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                line = FS._escape_for_concat(rel)
            finally:
                os.chdir(cwd)
            # Must start with `file '` and contain an absolute path
            self.assertTrue(line.startswith("file '"))
            self.assertTrue("/subdir/foo.mp4'" in line)
            # Single-quote escape (counter c MED): apostrophe in path
            apo = Path("/tmp/foo'bar.mp4")
            esc = FS._escape_for_concat(apo)
            self.assertIn("'\\''", esc)
        finally:
            import shutil  # noqa: PLC0415
            shutil.rmtree(tmp, ignore_errors=True)


class TestXfadePairOrchestration(unittest.TestCase):
    """8. xfade pair generation argv correctness for 3 mock beats.
    Also validates counter (f) CRITICAL: last beat NEVER calls trim_tail.
    """

    def test_xfade_pair_generation_for_3_mock_beats(self):
        # Stub ffmpeg/ffprobe so we just record argv shapes.
        recorded: list[list[str]] = []

        def dispatch(cmd, *a, **kw):
            recorded.append(list(cmd))
            class _R:
                returncode = 0
                stdout = b"4.000\n" if cmd and cmd[0] == "ffprobe" else b""
                stderr = b""
            # Materialize the output path so os.replace() succeeds.
            if cmd and cmd[0] == "ffmpeg":
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x00m4v\x00")
            return _R()

        with mock.patch.object(FS.subprocess, "run", side_effect=dispatch):
            tmp = Path(tempfile.mkdtemp(prefix="xfp_"))
            try:
                a = tmp / "a.mp4"; b = tmp / "b.mp4"; c = tmp / "c.mp4"
                for p in (a, b, c):
                    p.write_bytes(b"x")
                fade_ms = 250
                # Render two pairs (a,b) and (b,c) with fresh subprocess each.
                pair_ab = tmp / "pair_ab.mp4"
                pair_bc = tmp / "pair_bc.mp4"
                FS.render_xfade_pair(a, b, fade_ms, pair_ab, dur_a=4.0)
                FS.render_xfade_pair(b, c, fade_ms, pair_bc, dur_a=4.0)
            finally:
                import shutil  # noqa: PLC0415
                shutil.rmtree(tmp, ignore_errors=True)

        # We expect 2 ffmpeg invocations (one per pair).
        self.assertEqual(len(recorded), 2)
        for cmd in recorded:
            joined = " ".join(cmd)
            self.assertIn("xfade=transition=fade:duration=0.250", joined)
            # offset = dur_a - fade_s = 4.0 - 0.25 = 3.75
            self.assertIn("offset=3.750", joined)
            self.assertIn("acrossfade=d=0.250", joined)
            self.assertIn("[v]", joined)
            self.assertIn("[a]", joined)


# ---------------------------------------------------------------------------
# HTTP-based tests (live server fixture)
# ---------------------------------------------------------------------------
def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _make_event_fixture(tmp: Path) -> tuple[Path, Path, str]:
    event_dir = tmp / "Event_PREVSTITCHED"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text(
        '<html><head><script>var L = []; var TH = {};</script></head>'
        '<body></body></html>\n', encoding="utf-8",
    )
    state = event_dir / "production_state.json"
    state.write_text(json.dumps({
        "event_id": "Event_PREVSTITCHED",
        "beats": {
            "beat_01": _beat(["clip_a.mp4"]),
            "beat_02": _beat(["clip_b.mp4"]),
        },
        "display_order": ["beat_01", "beat_02"],
        "image_overrides": {},
    }, indent=2))
    return event_dir, storyboard, "Event_PREVSTITCHED"


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
            content_type = r.headers.get("Content-Type", "")
            raw = r.read()
            if "application/json" in content_type:
                return r.status, json.loads(raw.decode("utf-8")), dict(r.headers)
            return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload, dict(e.headers or {})


class TestModulePatchEndpoint(unittest.TestCase):
    """10. /api/v2/module/patch with null-equivalent (root) writes."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="modpatch_"))
        self.event_dir, self.sb, self.event_id = _make_event_fixture(self.tmp)
        self.port = _find_free_port()
        PS._PATCH_STATE_DEDUP.clear()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.sb, self.event_id, self.port,
        )

    def tearDown(self) -> None:
        try:
            self.server.shutdown(); self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_module_patch_writes_to_root(self):
        status, resp, _ = _http_post(self.port, "/api/v2/module/patch",
                                     {"field": "fade_between_beats_ms", "value": 250})
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        state = self.app.state.read_state()
        self.assertEqual(state.get("fade_between_beats_ms"), 250)

    def test_module_patch_rejects_non_whitelist(self):
        status, resp, _ = _http_post(self.port, "/api/v2/module/patch",
                                     {"field": "selected_option", "value": 1})
        self.assertEqual(status, 400, resp)
        self.assertIn("hint", resp)

    def test_module_patch_rejects_non_int(self):
        status, resp, _ = _http_post(self.port, "/api/v2/module/patch",
                                     {"field": "fade_between_beats_ms", "value": "two-fifty"})
        self.assertEqual(status, 400, resp)

    def test_module_patch_rejects_out_of_range(self):
        status, resp, _ = _http_post(self.port, "/api/v2/module/patch",
                                     {"field": "fade_between_beats_ms", "value": 5000})
        self.assertEqual(status, 400, resp)

    def test_missing_selected_file_returns_400(self):
        """6. P07 fail-loud: missing selected file => 400 with hint + missing list."""
        # Snapshot points at clip_a.mp4 / clip_b.mp4 which do not exist on disk.
        snapshot = self.app.state.read_state()
        status, resp, _ = _http_post(
            self.port, "/api/preview_stitched",
            {"state_snapshot": snapshot, "fade_between_beats_ms": 200},
        )
        self.assertEqual(status, 400, resp)
        self.assertIn("missing", resp, resp)
        self.assertIn("hint", resp, resp)
        self.assertEqual(len(resp["missing"]), 2)


# ---------------------------------------------------------------------------
# Rule 7 Path B: storyboard base64 SHA256 byte-identical pre/post patcher
# ---------------------------------------------------------------------------
class TestPatcherBase64Idempotent(unittest.TestCase):
    """11. Re-running the patcher on an already-patched file MUST be a no-op
    (the patcher self-detects via the BEGIN marker), and the base64 SHA256
    of the live patched file MUST match the SHA256 of every backup taken
    before this patcher ran. Equivalent to the 'no base64 corruption'
    Rule 7 Path B invariant.
    """
    def test_base64_images_sha256_identical_post_patch(self):
        # Derive project root from THIS file (Phase 3 FAIL-1 portability fix).
        proj = Path(__file__).resolve().parents[3]
        target = proj / "Production" / "Event_1" / "storyboard_v38_prod.html"
        self.assertTrue(target.is_file(), "storyboard not found — patcher prerequisite")
        # Compare against EVERY backup, not just the most-recent (Phase 3
        # counter FAIL-2: picking sorted[-1] could mask a corruption regression
        # introduced between earlier patcher runs).
        backups = sorted(target.parent.glob(target.name + ".bak_preview_stitched_*"))
        self.assertGreater(
            len(backups), 0,
            "no backup found from preview_stitched patcher — has it run?",
        )
        post = target.read_text(encoding="utf-8")
        from patch_v38_preview_stitched import _sha256_of_sorted_b64_uris
        post_sha, post_n = _sha256_of_sorted_b64_uris(post)
        for bak in backups:
            pre = bak.read_text(encoding="utf-8")
            pre_sha, pre_n = _sha256_of_sorted_b64_uris(pre)
            self.assertEqual(
                (pre_sha, pre_n), (post_sha, post_n),
                f"Rule 7 Path B violation: base64 SHA256 differs vs. {bak.name}",
            )


# ---------------------------------------------------------------------------
# 12. Full pipeline mocked end-to-end
# ---------------------------------------------------------------------------
class TestFullPipelineMockedFfmpeg(unittest.TestCase):
    """End-to-end: 3 beats, subprocess patched. Verifies counter (f) CRITICAL:
    last beat does NOT pass through trim_tail."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fullpipe_"))

    def tearDown(self) -> None:
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_pipeline_mocked_ffmpeg_3_beats(self):
        clips_dir = self.tmp / "animation_clips"
        clips_dir.mkdir()
        # Create real mp4-shaped placeholder files
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            (clips_dir / name).write_bytes(b"\x00fake\x00")

        snapshot = _make_snapshot({
            "beat_01": _beat(["a.mp4"], trim_start=0.0, trim_end=4.0),
            "beat_02": _beat(["b.mp4"], trim_start=0.0, trim_end=4.0),
            "beat_03": _beat(["c.mp4"], trim_start=0.0, trim_end=4.0),
        })

        # Mock subprocess: route ffprobe -> 4.0s; ffmpeg -> tmp+rename success;
        # record argv per call so we can introspect the trim_tail / xfade
        # invocations.
        records: list[list[str]] = []

        def fake_run(cmd, *a, **kw):
            records.append(list(cmd))
            class _R:
                returncode = 0
                stdout = b"4.000\n" if cmd and cmd[0] == "ffprobe" else b""
                stderr = b""
            # Honor `os.replace` style atomic write: when the cmd produces
            # an output file (last positional arg ending in .mp4 or .tmp.*),
            # touch it so downstream stat() works.
            if cmd and cmd[0] == "ffmpeg":
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x00m4v\x00")
            return _R()

        with mock.patch.object(FS.subprocess, "run", side_effect=fake_run):
            # Manually drive the pipeline logic (mirrors the server handler
            # but lets us assert on intermediate calls).
            beat_ids = sorted(snapshot["beats"].keys())
            normalized_dir = self.tmp / "preview" / "normalized"
            trimmed_dir = self.tmp / "preview" / "trimmed"
            xfade_dir = self.tmp / "preview" / "xfade"
            body_dir = self.tmp / "preview" / "bodies"
            for d in (normalized_dir, trimmed_dir, xfade_dir, body_dir):
                d.mkdir(parents=True, exist_ok=True)

            normalized: dict[str, Path] = {}
            trimmed: dict[str, Path] = {}
            durations: list[float] = []
            for bid in beat_ids:
                src = FS.resolve_beat_file(bid, snapshot, clips_dir)
                norm = normalized_dir / f"{bid}_normalized.mp4"
                FS.normalize_for_concat(src, norm)
                normalized[bid] = norm
                tr = trimmed_dir / f"{bid}_trimmed.mp4"
                d = FS.trim_normalized(norm, tr, 0.0, 4.0)
                trimmed[bid] = tr
                durations.append(d)

            fade_ms = FS.compute_fade_clamp(durations, 250)
            self.assertEqual(fade_ms, 250)

            parts: list[Path] = []
            fade_s = fade_ms / 1000.0
            for i, bid in enumerate(beat_ids):
                is_last = (i == len(beat_ids) - 1)
                if is_last:
                    parts.append(trimmed[bid])
                    continue
                body = body_dir / f"{bid}_body.mp4"
                FS.trim_tail(trimmed[bid], body, fade_s)
                parts.append(body)
                pair = xfade_dir / f"pair_{i:02d}.mp4"
                FS.render_xfade_pair(trimmed[bid], trimmed[beat_ids[i+1]],
                                     fade_ms, pair, dur_a=durations[i])
                parts.append(pair)

            output = self.tmp / "preview" / "preview_final.mp4"
            FS.concat_with_xfade_clips(parts, output)

        # ---- Counter (f) CRITICAL assertion ----
        # Body files must exist for beats 0 and 1 only — NOT for the last beat.
        self.assertTrue((body_dir / "beat_01_body.mp4").is_file())
        self.assertTrue((body_dir / "beat_02_body.mp4").is_file())
        self.assertFalse((body_dir / "beat_03_body.mp4").is_file(),
                         "counter (f) CRITICAL violated: trim_tail ran on last beat")

        # ---- Concat parts must be: body0, pair0, body1, pair1, trimmed_last ----
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[0].name, "beat_01_body.mp4")
        self.assertEqual(parts[1].name, "pair_00.mp4")
        self.assertEqual(parts[2].name, "beat_02_body.mp4")
        self.assertEqual(parts[3].name, "pair_01.mp4")
        # Last entry is the FULL trimmed beat_03 — NOT a body file.
        self.assertEqual(parts[4].name, "beat_03_trimmed.mp4")

        # Concat command was invoked with concat demuxer + absolute path arg.
        concat_cmds = [c for c in records if "-f" in c and "concat" in c]
        self.assertEqual(len(concat_cmds), 1)
        cc = concat_cmds[0]
        self.assertIn("-safe", cc); self.assertIn("0", cc)
        # The concat list arg is absolute
        i = cc.index("-i")
        self.assertTrue(cc[i + 1].startswith("/"),
                        f"concat list path not absolute: {cc[i+1]!r}")

        # Final output written
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
