#!/usr/bin/env python3
"""FF-039 — ambient period junction crossfade (no extraneous bed restart)."""
from __future__ import annotations

import math
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "server_handlers"))

from server_handlers.stitch_ambient_loop import (  # noqa: E402
    STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1,
    build_ambient_bed_filter_lane,
    build_ambient_period_junction_loop,
    clamp_ambient_loop_crossfade_s,
)


def _load_mono(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    sr = w.getframerate()
    samples = [
        struct.unpack("<h", raw[i : i + 2])[0] / 32768.0
        for i in range(0, len(raw), 2)
    ]
    return samples, sr


def _seg(samples: list[float], sr: int, t0: float, t1: float) -> list[float]:
    i0, i1 = int(t0 * sr), int(t1 * sr)
    return samples[i0:i1]


def _corr(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 100:
        return 0.0
    ma = sum(a[:n]) / n
    mb = sum(b[:n]) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n)))
    db = math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
    return num / (da * db) if da * db else 0.0


class AmbientPeriodJunctionTests(unittest.TestCase):
    def test_junction_loop_uses_acrossfade_not_hard_concat(self):
        xf = clamp_ambient_loop_crossfade_s(32.808)
        lane = build_ambient_period_junction_loop("ptile", 32.808, 70.0, junction_xfade_s=xf)
        self.assertIn("acrossfade", lane)
        self.assertNotIn("concat=n=", lane)

    def test_filter_lane_uses_period_junction_marker(self):
        lane = build_ambient_bed_filter_lane(1, 32.808, 65.0, 0.15)
        self.assertIn("acrossfade", lane)
        self.assertNotRegex(lane, r"concat=n=\d+:v=0:a=1\[amb1loop\]")

    def test_intro_bed_no_restart_fingerprint(self):
        bed = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
            / "Production/assets/sound_library/ambient/Intro video ambient bed.mp3"
        )
        if not bed.is_file():
            self.skipTest("intro ambient bed not on disk")
        period = 32.808
        slot_s = 70.0
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ambient.wav"
            lane = build_ambient_bed_filter_lane(0, period, slot_s, 0.15, out_label="aout")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(bed),
                    "-filter_complex", lane,
                    "-map", "[aout]",
                    "-ac", "1", "-ar", "48000",
                    str(out),
                ],
                check=True,
                capture_output=True,
                timeout=90,
            )
            samples, sr = _load_mono(out)
            start = _seg(samples, sr, 0.0, 0.5)
            for loop_t in (period, period * 2):
                before = _seg(samples, sr, loop_t - 0.5, loop_t)
                after = _seg(samples, sr, loop_t, loop_t + 0.5)
                restart = _corr(after, start)
                after_open = _corr(
                    _seg(samples, sr, loop_t + 0.05, loop_t + 0.25),
                    _seg(samples, sr, 0.05, 0.25),
                )
                self.assertLessEqual(
                    restart, 0.55,
                    f"ambient restarts bed opening @{loop_t}s (corr={restart:.3f})",
                )
                self.assertLessEqual(
                    after_open, 0.55,
                    f"post-loop opening matches bed head @{loop_t}s (corr={after_open:.3f})",
                )

    def test_marker_in_sig_token(self):
        from server_handlers.stitch_ambient_loop import ambient_loop_sig_token

        self.assertIn(
            STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1,
            ambient_loop_sig_token(),
        )


if __name__ == "__main__":
    unittest.main()
