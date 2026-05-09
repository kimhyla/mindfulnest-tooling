#!/usr/bin/env python3
"""Per-beat fade_after_ms override tests (LD PER_ITEM_FADE_AFTER_OVERRIDE_V1).

Spec: HANDOFF Per-Beat Fade-After Override, 2026-04-19.
Parent preflight chain: 90 -> 103 -> 109 -> 110 -> 113 -> 114 -> 117.

8 tests per spec:
  1. test_fade_after_ms_null_uses_global
  2. test_fade_after_ms_overrides_global
  3. test_compute_cache_hash_changes_on_fade_after
  4. test_compute_fade_clamp_per_pair_respects_neighbors
  5. test_compute_fade_clamp_per_pair_zero_stays_zero
  6. test_preview_pipeline_renders_mixed_fades (mocked ffmpeg)
  7. test_v2_patch_accepts_fade_after_ms_int
  8. test_v2_patch_rejects_fade_after_ms_out_of_range

Plus a small test that phase_1 without fade_after_ms is back-compatible.
Mocks subprocess (ffmpeg / ffprobe) end-to-end so the suite runs without an
actual ffmpeg binary in the test sandbox.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_clip(p: Path, body: bytes = b"\x00fakemp4\x00") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)


def _make_snapshot(beats: dict) -> dict:
    return {"beats": beats, "image_overrides": {}}


def _beat(option_files: list[str], selected: int = 1,
          trim_start: float = 0.0, trim_end=None,
          pause_after_ms: int = 0, fade_after_ms=None) -> dict:
    phase_1 = {
        "selected_option": selected,
        "options": [{"file": f} for f in option_files],
        "trim_start": trim_start,
        "trim_end": trim_end,
        "pause_after_ms": pause_after_ms,
    }
    if fade_after_ms is not None:
        phase_1["fade_after_ms"] = fade_after_ms
    return {"phase_1": phase_1, "_version": 1}


# ---------------------------------------------------------------------------
# 1 + 2. resolve_pair_fades correctness
# ---------------------------------------------------------------------------
class TestResolvePairFades(unittest.TestCase):
    def test_fade_after_ms_null_uses_global(self):
        """(1) When a beat has fade_after_ms=None it inherits the global fade."""
        meta = [
            {"beat_id": "beat_01", "fade_after_ms": None},
            {"beat_id": "beat_02", "fade_after_ms": None},
            {"beat_id": "beat_03", "fade_after_ms": None},
        ]
        self.assertEqual(FS.resolve_pair_fades(meta, 200), [200, 200])

    def test_fade_after_ms_overrides_global(self):
        """(2) An int override wins; None around it inherits."""
        meta = [
            {"beat_id": "beat_01", "fade_after_ms": None},
            {"beat_id": "beat_02", "fade_after_ms": 400},
            {"beat_id": "beat_03", "fade_after_ms": None},
        ]
        # pair 0 = beat_01.fade_after = None -> 200 (global)
        # pair 1 = beat_02.fade_after = 400 -> 400 (override)
        self.assertEqual(FS.resolve_pair_fades(meta, 200), [200, 400])

    def test_last_item_fade_after_ignored(self):
        """Last item's fade_after_ms never reaches the pairs list."""
        meta = [
            {"beat_id": "beat_01", "fade_after_ms": None},
            {"beat_id": "beat_02", "fade_after_ms": 999},  # outgoing pair of beat_02 -> none (last)
        ]
        # Only one pair (beat_01 -> beat_02); uses beat_01's override.
        self.assertEqual(FS.resolve_pair_fades(meta, 150), [150])

    def test_empty_items_returns_empty(self):
        self.assertEqual(FS.resolve_pair_fades([], 200), [])


# ---------------------------------------------------------------------------
# 3. cache hash sensitivity to fade_after_ms
# ---------------------------------------------------------------------------
class TestCacheHashOnFadeAfter(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="fadehash_"))
        self.clips_dir = self.tmp / "animation_clips"
        self.clips_dir.mkdir()
        _make_clip(self.clips_dir / "a.mp4")
        _make_clip(self.clips_dir / "b.mp4")

    def tearDown(self) -> None:
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compute_cache_hash_changes_on_fade_after(self):
        """(3) Setting one beat's fade_after_ms invalidates the cache hash."""
        snap_inherit = _make_snapshot({
            "beat_01": _beat(["a.mp4"]),
            "beat_02": _beat(["b.mp4"]),
        })
        snap_override = _make_snapshot({
            "beat_01": _beat(["a.mp4"], fade_after_ms=500),
            "beat_02": _beat(["b.mp4"]),
        })
        h1, meta1 = FS.compute_cache_hash(
            snap_inherit, 200, ["beat_01", "beat_02"], self.clips_dir,
        )
        h2, meta2 = FS.compute_cache_hash(
            snap_override, 200, ["beat_01", "beat_02"], self.clips_dir,
        )
        self.assertNotEqual(h1, h2,
                            "fade_after_ms change must invalidate preview cache")
        # Metadata reflects it too
        self.assertIsNone(meta1[0]["fade_after_ms"])
        self.assertEqual(meta2[0]["fade_after_ms"], 500)

    def test_back_compat_no_fade_after_field(self):
        """A beat that never had fade_after_ms behaves identically to one with None."""
        snap_a = _make_snapshot({
            "beat_01": _beat(["a.mp4"]),  # no fade_after_ms key at all
            "beat_02": _beat(["b.mp4"]),
        })
        # Manually delete to simulate pre-upgrade state
        snap_a["beats"]["beat_01"]["phase_1"].pop("fade_after_ms", None)
        h1, _ = FS.compute_cache_hash(
            snap_a, 200, ["beat_01", "beat_02"], self.clips_dir,
        )
        snap_b = _make_snapshot({
            "beat_01": _beat(["a.mp4"], fade_after_ms=None),
            "beat_02": _beat(["b.mp4"]),
        })
        # _beat with fade_after_ms=None omits the field too; assert that
        # and fall back to explicit-None to confirm hash parity.
        snap_b["beats"]["beat_01"]["phase_1"]["fade_after_ms"] = None
        h2, _ = FS.compute_cache_hash(
            snap_b, 200, ["beat_01", "beat_02"], self.clips_dir,
        )
        self.assertEqual(h1, h2,
                         "Back-compat: missing key and explicit-None must hash identically")


# ---------------------------------------------------------------------------
# 4 + 5. compute_fade_clamp_per_pair behavior
# ---------------------------------------------------------------------------
class TestFadeClampPerPair(unittest.TestCase):
    def test_compute_fade_clamp_per_pair_respects_neighbors(self):
        """(4) Pair with a short neighbor beat clamps correctly."""
        # durations [4.0, 0.5, 3.0]; buffer 0.2s
        # pair 0 (4.0 <-> 0.5): max_safe = min(4.0, 0.5) - 0.2 = 0.3s = 300ms
        #   requested 500ms -> clamped to 300
        # pair 1 (0.5 <-> 3.0): max_safe = 0.3s -> clamped to 300
        result = FS.compute_fade_clamp_per_pair([4.0, 0.5, 3.0], [500, 500])
        self.assertEqual(result, [300, 300])

        # Unconstrained case: both durations long enough, fade passes through
        result2 = FS.compute_fade_clamp_per_pair([4.0, 3.0], [200])
        self.assertEqual(result2, [200])

        # Below-buffer neighbor: max_safe floors at 0
        result3 = FS.compute_fade_clamp_per_pair([4.0, 0.1], [500])
        self.assertEqual(result3, [0])

    def test_compute_fade_clamp_per_pair_zero_stays_zero(self):
        """(5) Requested fade=0 stays 0 (hard-cut marker)."""
        # fade=0 for pair 0, fade=500 for pair 1 (both neighbors long)
        result = FS.compute_fade_clamp_per_pair([4.0, 3.0, 5.0], [0, 500])
        self.assertEqual(result, [0, 500])
        # All zeros
        self.assertEqual(
            FS.compute_fade_clamp_per_pair([4.0, 3.0], [0]),
            [0],
        )

    def test_compute_fade_clamp_per_pair_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            FS.compute_fade_clamp_per_pair([4.0, 3.0, 5.0], [200, 300, 400])
        with self.assertRaises(ValueError):
            FS.compute_fade_clamp_per_pair([], [])


# ---------------------------------------------------------------------------
# 6. end-to-end mocked ffmpeg: mixed fades
# ---------------------------------------------------------------------------
class TestPreviewPipelineMixedFades(unittest.TestCase):
    """(6) End-to-end mocked pipeline with mixed per-pair fades:
    pair 0 = 0ms (hard cut), pair 1 = 500ms (xfade).
    Asserts the concat parts shape + the ffmpeg commands called.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mixfade_"))

    def tearDown(self) -> None:
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preview_pipeline_renders_mixed_fades(self):
        clips_dir = self.tmp / "animation_clips"
        clips_dir.mkdir()
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            (clips_dir / name).write_bytes(b"\x00fake\x00")

        # beat_01 fade_after_ms=0 (hard cut to beat_02)
        # beat_02 fade_after_ms=500 (xfade to beat_03)
        # global fade = 200 (ignored because both beats override)
        snapshot = _make_snapshot({
            "beat_01": _beat(["a.mp4"], trim_start=0.0, trim_end=4.0,
                             fade_after_ms=0),
            "beat_02": _beat(["b.mp4"], trim_start=0.0, trim_end=4.0,
                             fade_after_ms=500),
            "beat_03": _beat(["c.mp4"], trim_start=0.0, trim_end=4.0),
        })

        records: list[list[str]] = []

        def fake_run(cmd, *a, **kw):
            records.append(list(cmd))

            class _R:
                returncode = 0
                stdout = b"4.000\n" if cmd and cmd[0] == "ffprobe" else b""
                stderr = b""
            if cmd and cmd[0] == "ffmpeg":
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x00m4v\x00")
            return _R()

        with mock.patch.object(FS.subprocess, "run", side_effect=fake_run):
            beat_ids = sorted(snapshot["beats"].keys())
            normalized_dir = self.tmp / "preview" / "normalized"
            trimmed_dir = self.tmp / "preview" / "trimmed"
            xfade_dir = self.tmp / "preview" / "xfade"
            body_dir = self.tmp / "preview" / "bodies"
            for d in (normalized_dir, trimmed_dir, xfade_dir, body_dir):
                d.mkdir(parents=True, exist_ok=True)

            trimmed: dict[str, Path] = {}
            durations: list[float] = []
            _, beat_meta = FS.compute_cache_hash(
                snapshot, 200, beat_ids, clips_dir,
            )
            for bid in beat_ids:
                src = FS.resolve_beat_file(bid, snapshot, clips_dir)
                norm = normalized_dir / f"{bid}_normalized.mp4"
                FS.normalize_for_concat(src, norm)
                tr = trimmed_dir / f"{bid}_trimmed.mp4"
                d = FS.trim_normalized(norm, tr, 0.0, 4.0)
                trimmed[bid] = tr
                durations.append(d)

            requested = FS.resolve_pair_fades(beat_meta, 200)
            self.assertEqual(requested, [0, 500])
            clamped = FS.compute_fade_clamp_per_pair(durations, requested)
            self.assertEqual(clamped, [0, 500])

            # Drive the same pipeline logic the server does
            parts: list[Path] = []
            for i, bid in enumerate(beat_ids):
                is_last = (i == len(beat_ids) - 1)
                if is_last:
                    parts.append(trimmed[bid])
                    continue
                pair_fade_ms = clamped[i]
                if pair_fade_ms <= 0:
                    parts.append(trimmed[bid])
                    continue
                body = body_dir / f"{bid}_body.mp4"
                FS.trim_tail(trimmed[bid], body, pair_fade_ms / 1000.0)
                parts.append(body)
                pair = xfade_dir / f"pair_{i:02d}.mp4"
                FS.render_xfade_pair(
                    trimmed[bid], trimmed[beat_ids[i + 1]],
                    pair_fade_ms, pair, dur_a=durations[i],
                )
                parts.append(pair)

            output = self.tmp / "preview" / "final.mp4"
            FS.concat_with_xfade_clips(parts, output)

        # Hard-cut pair must NOT produce a body file for beat_01.
        self.assertFalse((body_dir / "beat_01_body.mp4").is_file(),
                         "hard-cut pair 0 should not trim_tail beat_01")
        # Xfade pair must produce body for beat_02.
        self.assertTrue((body_dir / "beat_02_body.mp4").is_file(),
                        "xfade pair 1 should trim_tail beat_02")
        # Last beat always full trimmed.
        self.assertFalse((body_dir / "beat_03_body.mp4").is_file())

        # Concat parts: [beat_01_trimmed, beat_02_body, pair_01, beat_03_trimmed]
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0].name, "beat_01_trimmed.mp4")
        self.assertEqual(parts[1].name, "beat_02_body.mp4")
        self.assertEqual(parts[2].name, "pair_01.mp4")
        self.assertEqual(parts[3].name, "beat_03_trimmed.mp4")

        # Exactly ONE xfade ffmpeg call — the hard-cut pair doesn't invoke xfade.
        xfade_cmds = [c for c in records
                      if any("xfade=transition=fade" in x for x in c)]
        self.assertEqual(len(xfade_cmds), 1,
                         "mixed-fade pipeline should call xfade exactly once")
        joined = " ".join(xfade_cmds[0])
        self.assertIn("xfade=transition=fade:duration=0.500", joined)


# ---------------------------------------------------------------------------
# 7 + 8. /api/v2/beat/<bid>/patch fade_after_ms plumbing
# ---------------------------------------------------------------------------
def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _make_event_fixture(tmp: Path) -> tuple[Path, Path, str]:
    event_dir = tmp / "Event_FADEOVR"
    event_dir.mkdir(parents=True, exist_ok=True)
    storyboard = event_dir / "storyboard_test.html"
    storyboard.write_text(
        '<html><head><script>var L = []; var TH = {};</script></head>'
        '<body></body></html>\n', encoding="utf-8",
    )
    state = event_dir / "production_state.json"
    state.write_text(json.dumps({
        "event_id": "Event_FADEOVR",
        "beats": {
            "beat_01": _beat(["clip_a.mp4"]),
            "beat_02": _beat(["clip_b.mp4"]),
        },
        "display_order": ["beat_01", "beat_02"],
        "image_overrides": {},
    }, indent=2))
    return event_dir, storyboard, "Event_FADEOVR"


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


class TestV2PatchFadeAfterMs(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="v2fade_"))
        self.event_dir, self.sb, self.event_id = _make_event_fixture(self.tmp)
        self.port = _find_free_port()
        PS._PATCH_STATE_DEDUP.clear()
        self.server, self.thread, self.app = _start_server(
            self.event_dir, self.sb, self.event_id, self.port,
        )

    def tearDown(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:  # noqa: BLE001
            pass
        import shutil  # noqa: PLC0415
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_v2_patch_accepts_fade_after_ms_int(self):
        """(7) POST fade_after_ms=300 -> 200, writes phase_1.fade_after_ms=300."""
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "fade_after_ms", "value": 300},
        )
        self.assertEqual(status, 200, resp)
        self.assertEqual(resp.get("status"), "applied", resp)
        state = self.app.state.read_state()
        beat = state["beats"]["beat_01"]
        self.assertEqual(beat["phase_1"]["fade_after_ms"], 300)

    def test_v2_patch_null_clears_fade_after_ms(self):
        """Additional coverage — null clears the override (inherit global)."""
        # First set it
        self.app.state.mutate_state(
            lambda s: s.setdefault("beats", {})
                       .setdefault("beat_01", {})
                       .setdefault("phase_1", {})
                       .update({"fade_after_ms": 400}),
        )
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "fade_after_ms", "value": None},
        )
        self.assertEqual(status, 200, resp)
        state = self.app.state.read_state()
        # Key popped
        self.assertNotIn("fade_after_ms",
                         state["beats"]["beat_01"].get("phase_1", {}))

    def test_v2_patch_rejects_fade_after_ms_out_of_range(self):
        """(8) Out-of-range int returns 400 with hint."""
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "fade_after_ms", "value": 1500},
        )
        self.assertEqual(status, 400, resp)
        self.assertIn("hint", resp, resp)

    def test_v2_patch_rejects_fade_after_ms_string(self):
        """Non-int non-null input is rejected."""
        status, resp = _http_post(
            self.port, "/api/v2/beat/beat_01/patch",
            {"field": "fade_after_ms", "value": "500ms"},
        )
        self.assertEqual(status, 400, resp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
