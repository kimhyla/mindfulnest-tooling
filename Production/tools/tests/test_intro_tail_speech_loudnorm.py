"""Canonical intro_tail must ship at speech-bus loudness (−19 LUFS recipe)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "credentials_lib"))


def _make_quiet_speak_mp4(path: Path, duration_s: float = 2.0) -> None:
    """Synthetic VO-like clip well below speech-bus target (needs loudnorm boost)."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={duration_s:.3f}",
            "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={duration_s:.3f}",
            "-filter_complex", "[0:a]volume=0.05[a]",
            "-map", "1:v", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def _mean_volume_db(path: Path) -> float:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    for line in p.stderr.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0].strip())
    raise AssertionError(f"mean_volume not found for {path}")


def _stream_duration_s(path: Path, stream: str) -> float:
    sel = "v:0" if stream.startswith("v") else "a:0"
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", sel,
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float((r.stdout or "").strip() or "0")


class IntroTailSpeechLoudnormTests(unittest.TestCase):
    def test_apply_intro_tail_speech_loudnorm_raises_quiet_speak(self):
        from teleport_intro_kit import apply_intro_tail_speech_loudnorm  # noqa: WPS433

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "quiet_tail.mp4"
            out = Path(tmp) / "leveled_tail.mp4"
            _make_quiet_speak_mp4(src)
            before = _mean_volume_db(src)
            apply_intro_tail_speech_loudnorm(src, out)
            after = _mean_volume_db(out)
            self.assertGreater(
                after - before,
                6.0,
                f"expected loudnorm boost >6dB, before={before} after={after}",
            )
            self.assertTrue(out.is_file())

    def test_loudnorm_output_av_drift_within_export_budget(self):
        """Regression: AAC loudnorm alone left ~58ms drift and blocked Send to Stitcher."""
        from teleport_intro_kit import apply_intro_tail_speech_loudnorm  # noqa: WPS433

        # Match beat_generator concat gate (STITCH_EXPORT_CUMULATIVE_AV_MAX_DRIFT_S).
        max_drift_s = 0.05
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "quiet_tail.mp4"
            out = Path(tmp) / "leveled_tail.mp4"
            _make_quiet_speak_mp4(src, duration_s=2.5)
            apply_intro_tail_speech_loudnorm(src, out)
            drift = abs(_stream_duration_s(out, "v") - _stream_duration_s(out, "a"))
            self.assertLessEqual(
                drift,
                max_drift_s,
                f"intro_tail A/V drift {drift:.3f}s exceeds export budget {max_drift_s}s",
            )

    def test_compose_source_applies_speech_loudnorm(self):
        text = (TOOLS / "teleport_intro_kit.py").read_text(encoding="utf-8")
        block = text.split("def ffmpeg_compose_intro_tail", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("apply_intro_tail_speech_loudnorm", block)
        loud_block = text.split("def apply_intro_tail_speech_loudnorm", 1)[1].split(
            "\ndef ffmpeg_compose_intro_tail", 1
        )[0]
        self.assertIn("lock_intro_tail_av_to_video_timeline", loud_block)


if __name__ == "__main__":
    unittest.main()
