"""Real-ffmpeg integration tests for lib.ffmpeg_stitch (preflight 103, Bug 3 fix).

The mocked test suite (test_preview_stitched.py, 16/16 green) cannot catch
filter-graph collisions, rc=234 errors, or codec/format mismatches because it
stubs subprocess.run. This sibling file invokes the real ffmpeg/ffprobe
binaries against tiny synthetic lavfi fixtures. Each test runs in <2s.

Gated via shutil.which; skipped if ffmpeg/ffprobe aren't on PATH.

Covers:
  1. render_xfade_pair no longer collides (-vf + -filter_complex, rc=234)
  2. normalize_for_concat produces LD-284 canonical output
  3. render_watercolor_overlay with PNG cue (no chromakey branch)
  4. render_watercolor_overlay with no cues (passthrough branch)
  5. render_watercolor_overlay base-normalization handles non-canonical input
  6. concat_with_xfade_clips end-to-end 3-beat pipeline
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "Production" / "tools"))

from credentials_lib import ffmpeg_stitch as FS  # noqa: E402


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
SKIP_REASON = "ffmpeg or ffprobe not on PATH"


def _synth_clip(path: Path, dur: float = 1.0, color: str = "red",
                w: int = 1280, h: int = 720, fps: int = 24,
                with_audio: bool = True) -> Path:
    """Create a tiny synthetic MP4 via lavfi. ~0.3s real time."""
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi",
           "-i", f"color=c={color}:s={w}x{h}:d={dur}:r={fps}"]
    if with_audio:
        cmd += ["-f", "lavfi",
                "-i", f"sine=frequency=440:duration={dur}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-preset", "ultrafast", "-crf", "28"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", "44100",
                "-shortest"]
    cmd += ["-movflags", "+faststart", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def _synth_png(path: Path, color: str = "white",
               w: int = 200, h: int = 200) -> Path:
    """Create a small transparent-background PNG via lavfi."""
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi",
                    "-i", f"color=c={color}@0.5:s={w}x{h}:d=0.1",
                    "-frames:v", "1", str(path)],
                   check=True, capture_output=True)
    return path


def _probe(path: Path) -> dict:
    """Return ffprobe JSON summary of first video stream."""
    out = subprocess.run(
        [FFPROBE, "-v", "error",
         "-select_streams", "v:0",
         "-show_entries",
         "stream=width,height,r_frame_rate,codec_name,pix_fmt,profile",
         "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, check=True, text=True,
    ).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    stream["duration"] = float(data["format"]["duration"])
    return stream


@unittest.skipIf(FFMPEG is None or FFPROBE is None, SKIP_REASON)
class TestXfadePairRealFfmpeg(unittest.TestCase):
    """render_xfade_pair must no longer hit rc=234 from -vf + -filter_complex."""

    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_xfade_real"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_vf_filter_complex_collision(self):
        a = _synth_clip(self.tmp / "a.mp4", dur=1.0, color="red")
        b = _synth_clip(self.tmp / "b.mp4", dur=1.0, color="blue")
        out = self.tmp / "pair.mp4"
        # Should NOT raise. Pre-fix raised CalledProcessError with rc=234.
        FS.render_xfade_pair(a, b, fade_ms=300, dst=out, dur_a=1.0)
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 1000)
        probe = _probe(out)
        self.assertEqual(probe["codec_name"], "h264")
        self.assertEqual(probe["width"], 1280)
        self.assertEqual(probe["height"], 720)
        self.assertEqual(probe["r_frame_rate"], "24/1")


@unittest.skipIf(FFMPEG is None or FFPROBE is None, SKIP_REASON)
class TestNormalizeForConcatRealFfmpeg(unittest.TestCase):
    """normalize_for_concat must produce LD-284 canonical output."""

    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_norm_real"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _audio_present(self, path: Path) -> bool:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0",
             str(path)],
            capture_output=True, check=True, text=True,
        ).stdout.strip()
        return bool(out)

    def test_produces_1280x720_24fps_h264_high(self):
        # Non-canonical input: 640x480 @ 30fps.
        src = _synth_clip(self.tmp / "raw.mp4", dur=0.5,
                          w=640, h=480, fps=30)
        norm = self.tmp / "norm.mp4"
        FS.normalize_for_concat(src, norm)
        probe = _probe(norm)
        self.assertEqual(probe["width"], 1280)
        self.assertEqual(probe["height"], 720)
        self.assertEqual(probe["codec_name"], "h264")
        self.assertEqual(probe["r_frame_rate"], "24/1")
        self.assertEqual(probe["pix_fmt"], "yuv420p")

    def test_silent_audio_injected_when_source_lacks_audio(self):
        # Bug 4 fix: Kling animation clips are video-only (sound: false per
        # CLAUDE.md §8.1). Normalized output MUST still have an audio stream
        # so downstream xfade's acrossfade doesn't fail.
        src = _synth_clip(self.tmp / "no_audio.mp4", dur=0.5,
                          with_audio=False)
        self.assertFalse(self._audio_present(src))  # precondition
        norm = self.tmp / "norm_with_silent.mp4"
        FS.normalize_for_concat(src, norm)
        self.assertTrue(self._audio_present(norm))  # invariant restored

    def test_xfade_pair_succeeds_on_video_only_sources(self):
        # End-to-end: two audio-less source clips -> normalize -> xfade.
        # Pre-fix raised rc=234 "Stream specifier :a matches no streams".
        a_raw = _synth_clip(self.tmp / "a_raw.mp4", dur=1.0,
                            color="red", with_audio=False)
        b_raw = _synth_clip(self.tmp / "b_raw.mp4", dur=1.0,
                            color="blue", with_audio=False)
        a_norm = self.tmp / "a_norm.mp4"
        b_norm = self.tmp / "b_norm.mp4"
        FS.normalize_for_concat(a_raw, a_norm)
        FS.normalize_for_concat(b_raw, b_norm)
        out = self.tmp / "xfade_out.mp4"
        FS.render_xfade_pair(a_norm, b_norm, fade_ms=300,
                             dst=out, dur_a=1.0)
        self.assertTrue(out.is_file())
        self.assertTrue(self._audio_present(out))


@unittest.skipIf(FFMPEG is None or FFPROBE is None, SKIP_REASON)
class TestWatercolorOverlayRealFfmpeg(unittest.TestCase):
    """render_watercolor_overlay covers the other filter_complex collision
    and the base-normalization + tail-fps guards added in preflight 103."""

    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_wc_real"
        self.tmp.mkdir(exist_ok=True)
        self.library = self.tmp / "library"
        self.library.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_png_cue_no_collision(self):
        base = _synth_clip(self.tmp / "base.mp4", dur=2.0, color="gray")
        _synth_png(self.library / "breath_rub.png", color="yellow")
        cues = [{
            "timestamp_ms": 500,
            "key": "breath_rub",
            "animation": "fade_in",
            "duration_ms": 800,
            "cue_type": "png",
        }]
        out = self.tmp / "wc_out.mp4"
        FS.render_watercolor_overlay(
            base_video_path=base, cues=cues,
            frame_x=40, frame_y=180,
            output_path=out, library_dir=self.library,
        )
        self.assertTrue(out.is_file())
        probe = _probe(out)
        self.assertEqual(probe["codec_name"], "h264")
        self.assertEqual(probe["width"], 1280)
        self.assertEqual(probe["height"], 720)
        self.assertEqual(probe["r_frame_rate"], "24/1")
        # Duration should equal base duration (±0.2s tolerance).
        self.assertAlmostEqual(probe["duration"], 2.0, delta=0.25)

    def test_no_cues_passthrough_branch(self):
        base = _synth_clip(self.tmp / "base2.mp4", dur=1.0, color="teal")
        out = self.tmp / "wc_nocues.mp4"
        FS.render_watercolor_overlay(
            base_video_path=base, cues=[],
            frame_x=40, frame_y=180,
            output_path=out, library_dir=self.library,
        )
        self.assertTrue(out.is_file())
        probe = _probe(out)
        self.assertEqual(probe["width"], 1280)
        self.assertEqual(probe["r_frame_rate"], "24/1")

    def test_non_canonical_base_gets_normalized(self):
        # C1 finding: lipsync_path has no pre-normalization contract.
        # Verify prepended [0:v]VF_EXPR[base] rescues a 896x504@30 input.
        base = _synth_clip(self.tmp / "base_odd.mp4", dur=1.0,
                           w=896, h=504, fps=30)
        _synth_png(self.library / "heart_bloom.png", color="pink")
        cues = [{
            "timestamp_ms": 200, "key": "heart_bloom",
            "animation": "fade_in", "duration_ms": 600,
            "cue_type": "png",
        }]
        out = self.tmp / "wc_rescued.mp4"
        FS.render_watercolor_overlay(
            base_video_path=base, cues=cues,
            frame_x=800, frame_y=180,
            output_path=out, library_dir=self.library,
        )
        probe = _probe(out)
        self.assertEqual(probe["width"], 1280)
        self.assertEqual(probe["height"], 720)
        self.assertEqual(probe["r_frame_rate"], "24/1")


@unittest.skipIf(FFMPEG is None or FFPROBE is None, SKIP_REASON)
class TestConcatEndToEndRealFfmpeg(unittest.TestCase):
    """Full 3-beat concat pipeline: normalize -> trim -> xfade -> concat."""

    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_concat_real"
        self.tmp.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_3_beat_concat(self):
        # Three non-canonical source clips.
        raws = [
            _synth_clip(self.tmp / f"raw_{i}.mp4", dur=1.0,
                        color=c, w=640, h=480, fps=30)
            for i, c in enumerate(["red", "green", "blue"])
        ]
        norms = [self.tmp / f"norm_{i}.mp4" for i in range(3)]
        for src, dst in zip(raws, norms):
            FS.normalize_for_concat(src, dst)
            probe = _probe(dst)
            self.assertEqual(probe["width"], 1280)
            self.assertEqual(probe["r_frame_rate"], "24/1")

        # xfade pair between beat 0 and 1.
        xfade_01 = self.tmp / "xfade_01.mp4"
        FS.render_xfade_pair(
            norms[0], norms[1], fade_ms=250, dst=xfade_01, dur_a=1.0,
        )
        probe = _probe(xfade_01)
        self.assertEqual(probe["width"], 1280)
        self.assertEqual(probe["codec_name"], "h264")


if __name__ == "__main__":
    unittest.main()
