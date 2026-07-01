#!/usr/bin/env python3
"""FF-026 — ambient loop seam budget: full-period tile, not crossfade-only repeat."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "server_handlers"))

from server_handlers.stitch_ambient_loop import (  # noqa: E402
    STITCH_AMBIENT_FULL_PERIOD_TILE_V2,
    build_ambient_bed_filter_lane,
    build_ambient_bed_filter_lane_for_file,
    build_ambient_seamless_period_tile,
    clamp_ambient_loop_crossfade_s,
    estimate_ambient_tile_period_s,
    probe_ambient_bed_active_span,
)


def _broken_crossfade_only_lane(
    input_idx: int,
    content_s: float,
    slot_s: float,
    vol: float,
    *,
    start_s: float = 0.0,
    end_s: float | None = None,
) -> str:
    """Regression helper — SINGLE_SEAM misimplementation (2.5s tile only)."""
    from server_handlers.stitch_ambient_loop import (  # noqa: PLC0415
        _ambient_bed_lane_out,
        clamp_ambient_loop_crossfade_s,
    )

    file_s = content_s if end_s is None else end_s
    base = f"[{input_idx}:a]aresample=44100,aformat=channel_layouts=mono"
    trimmed = f"{base},atrim=start={start_s:.3f}:end={file_s:.3f},asetpts=PTS-STARTPTS"
    xf = clamp_ambient_loop_crossfade_s(content_s)
    p = f"amb{input_idx}"
    lane_body = (
        f"{trimmed},asplit=2[{p}tail_src][{p}head_src];"
        f"[{p}tail_src]atrim=start={max(0.0, content_s - xf):.3f}:"
        f"duration={xf:.3f},asetpts=PTS-STARTPTS[{p}tail];"
        f"[{p}head_src]atrim=0:{xf:.3f},asetpts=PTS-STARTPTS[{p}head];"
        f"[{p}tail][{p}head]acrossfade=d={xf:.3f}:c1=tri:c2=tri[{p}tile];"
        f"[{p}tile]aloop=loop=-1:size=2147483647,atrim=duration={slot_s:.3f}"
    )
    return _ambient_bed_lane_out(lane_body, vol, "aout", slot_s)


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        text=True,
        timeout=15,
    ).strip()
    return float(out)


def _extract_mono_pcm(path: Path) -> tuple[list[float], int]:
    """Return normalized mono samples and sample rate."""
    import struct

    raw = subprocess.check_output(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-ac", "1", "-ar", "8000", "-f", "f32le", "pipe:1",
        ],
        timeout=120,
    )
    count = len(raw) // 4
    samples = list(struct.unpack(f"<{count}f", raw))
    return samples, 8000


def _top_loop_periods_s(
    samples: list[float],
    sample_rate: int,
    *,
    top_k: int = 5,
) -> list[float]:
    """Return top autocorrelation peak lags in seconds (coarse scan)."""
    n = min(len(samples), sample_rate * 30)
    if n < sample_rate * 4:
        return []
    chunk = samples[:n]
    mean = sum(chunk) / n
    centered = [x - mean for x in chunk]
    min_lag = int(sample_rate * 1.5)
    max_lag = min(n // 2, int(sample_rate * 40))
    step = max(1, sample_rate // 20)
    peaks: list[tuple[float, float]] = []
    for lag in range(min_lag, max_lag, step):
        corr = sum(centered[i] * centered[i + lag] for i in range(0, n - lag, step))
        peaks.append((corr, lag / sample_rate))
    peaks.sort(reverse=True)
    out: list[float] = []
    for _corr, period in peaks:
        if not out or all(abs(period - p) > 0.75 for p in out):
            out.append(period)
        if len(out) >= top_k:
            break
    return out


def _dominant_loop_period_s(samples: list[float], sample_rate: int) -> float:
    periods = _top_loop_periods_s(samples, sample_rate, top_k=1)
    return periods[0] if periods else 0.0


class StitchAmbientLoopSeamBudgetTests(unittest.TestCase):
    def test_full_period_tile_has_pre_and_wrap_not_glue_only(self):
        content_s = 27.35
        xf = clamp_ambient_loop_crossfade_s(content_s)
        body_end = content_s - xf
        lane = build_ambient_bed_filter_lane(
            1, 35.0, 49.0, 0.15,
            active_start_s=0.0,
            active_end_s=content_s,
        )
        self.assertIn("[amb1pre]", lane)
        self.assertIn("[amb1wrap]", lane)
        self.assertIn("concat=n=2:v=0:a=1[amb1tile]", lane)
        self.assertIn(f"atrim=0:{body_end:.3f}", lane)
        self.assertNotIn(
            "acrossfade=d=" + f"{xf:.3f}:c1=tri:c2=tri[amb1tile];"
            "[amb1tile]aloop",
            lane,
        )

    def test_estimate_tile_period_matches_content(self):
        self.assertAlmostEqual(estimate_ambient_tile_period_s(27.35), 27.35)

    def test_seamless_period_tile_fragment_length_fields(self):
        trimmed = "[0:a]aresample=44100,aformat=channel_layouts=mono,atrim=0:8,asetpts=PTS-STARTPTS"
        frag = build_ambient_seamless_period_tile(
            trimmed, prefix_label="amb0", content_s=8.0,
        )
        self.assertIn("[amb0pre]", frag)
        self.assertIn("[amb0wrap]", frag)
        self.assertIn("acrossfade=d=", frag)
        self.assertIn("c1=tri:c2=tri", frag)

    def test_rendered_loop_period_is_bed_not_crossfade(self):
        """49s slot, 8s sine bed — dominant autocorr peak must be ~8s, not ~2.5s."""
        with tempfile.TemporaryDirectory() as tmp:
            bed = Path(tmp) / "bed.mp3"
            out = Path(tmp) / "looped.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-ac", "1", "-ar", "44100", str(bed),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            lane = build_ambient_bed_filter_lane(0, 8.0, 49.0, 0.15, out_label="aout")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(bed),
                    "-filter_complex", lane,
                    "-map", "[aout]",
                    "-ac", "1", "-ar", "44100", str(out),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            self.assertAlmostEqual(_ffprobe_duration(out), 49.0, delta=0.2)
            samples, sr = _extract_mono_pcm(out)
            period = _dominant_loop_period_s(samples, sr)
            self.assertGreater(period, 6.0, msg=f"loop period {period:.2f}s too short (crossfade-only bug)")
            self.assertLess(period, 10.0, msg=f"loop period {period:.2f}s unexpected")

    def test_resolution_bed_filter_is_full_period(self):
        bed = (
            Path.home()
            / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files"
            / "Production/assets/sound_library/ambient/ambien bed pretty option4.mp3"
        )
        if not bed.is_file():
            self.skipTest("resolution ambient bed not on disk")
        start, end = probe_ambient_bed_active_span(bed)
        content_s = end - start
        self.assertGreater(content_s, 20.0)
        lane = build_ambient_bed_filter_lane_for_file(
            0, bed, _ffprobe_duration(bed), 55.0, 0.15, out_label="aout",
        )
        xf = clamp_ambient_loop_crossfade_s(content_s)
        body_end = content_s - xf
        self.assertIn("[amb0pre]", lane)
        self.assertIn("[amb0wrap]", lane)
        self.assertIn(f"atrim=0:{body_end:.3f}", lane)
        self.assertIn("concat=n=2:v=0:a=1[amb0tile]", lane)

    def test_broken_crossfade_only_regression_on_sine(self):
        """SINGLE_SEAM bug repeats ~2.5s; full-period tile repeats ~8s on sine bed."""
        with tempfile.TemporaryDirectory() as tmp:
            bed = Path(tmp) / "bed.mp3"
            fixed_out = Path(tmp) / "fixed.mp3"
            broken_out = Path(tmp) / "broken.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                    "-ac", "1", "-ar", "44100", str(bed),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            fixed_lane = build_ambient_bed_filter_lane(0, 8.0, 49.0, 0.15, out_label="aout")
            broken_lane = _broken_crossfade_only_lane(0, 8.0, 49.0, 0.15)
            for lane, out in ((fixed_lane, fixed_out), (broken_lane, broken_out)):
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(bed),
                        "-filter_complex", lane,
                        "-map", "[aout]",
                        "-ac", "1", "-ar", "44100", str(out),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
            fixed_period = _dominant_loop_period_s(*_extract_mono_pcm(fixed_out))
            broken_period = _dominant_loop_period_s(*_extract_mono_pcm(broken_out))
            self.assertGreater(fixed_period, 6.0)
            self.assertLess(broken_period, 4.0)
            self.assertGreater(fixed_period, broken_period * 2.0)


if __name__ == "__main__":
    unittest.main()
