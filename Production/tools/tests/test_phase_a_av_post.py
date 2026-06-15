"""Tests for phase_a_av_post helpers (ffmpeg integration)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase_a_av_post import (  # noqa: E402
    TRAILING_SPEECH_HOLD_S,
    av_duration_gap,
    crossfade_loop_video,
    pad_video_to_match_audio,
    trim_av_lead_in,
    trim_av_trailing_silence,
    upscale_lipsync_to_bookend,
)
from phase_a_chipper_idle_lipsync import (  # noqa: E402
    PHASE_A_ZOOM_END,
    PHASE_A_ZOOM_RAMP_DELAY_SEC,
    PHASE_A_ZOOM_RAMP_SEC,
    _preroll_seconds,
)
from production_server import _ffprobe_duration  # noqa: E402


def _make_test_clip(path: Path, duration: float, *, with_audio: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=red:s=640x480:d={duration:.3f}:r=24",
    ]
    if with_audio:
        cmd += [
            "-f", "lavfi", "-i", f"sine=f=440:duration={duration:.3f}",
            "-c:a", "aac", "-b:a", "128k", "-shortest",
        ]
    else:
        cmd += ["-an"]
    cmd += [
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)


def test_trailing_speech_hold_avoids_aggressive_clip() -> None:
    """Hold after last speech must leave room for final syllable (intro fade parity)."""
    assert TRAILING_SPEECH_HOLD_S >= 0.5


def test_crossfade_loop_extends_duration(tmp_path: Path) -> None:
    src = tmp_path / "seg.mp4"
    dst = tmp_path / "looped.mp4"
    _make_test_clip(src, 1.0)
    crossfade_loop_video(src, dst, 3.0, xfade_s=0.2, fps=24)
    dur = _ffprobe_duration(dst)
    assert 2.8 <= dur <= 3.2


def test_pad_video_closes_av_gap(tmp_path: Path) -> None:
    src = tmp_path / "av_mismatch.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2:r=24",
            "-f", "lavfi", "-i", "sine=f=220:duration=3",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    v_before, a_before, gap_before = av_duration_gap(src)
    assert a_before > v_before + 0.2, f"v={v_before} a={a_before}"

    dst = tmp_path / "padded.mp4"
    _, pad_s = pad_video_to_match_audio(src, dst)
    assert pad_s > 0.2
    _, _, gap_after = av_duration_gap(dst)
    assert gap_after <= 0.08


def test_trim_av_lead_in(tmp_path: Path) -> None:
    src = tmp_path / "av.mp4"
    _make_test_clip(src, 2.0, with_audio=True)
    dst = tmp_path / "trimmed.mp4"
    trim_av_lead_in(src, dst, 0.5)
    dur = _ffprobe_duration(dst)
    assert 1.3 <= dur <= 1.7


def test_trim_av_trailing_silence(tmp_path: Path) -> None:
    src = tmp_path / "speech_then_silence.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=320x240:d=2.5:r=24",
            "-f", "lavfi", "-i", "sine=f=440:duration=1.0",
            "-filter_complex", "[1:a]apad=whole_dur=2.5[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    before = _ffprobe_duration(src)
    dst = tmp_path / "tailed.mp4"
    _, trimmed = trim_av_trailing_silence(src, dst)
    after = _ffprobe_duration(dst)
    assert trimmed > 0.4
    assert after < before - 0.3
    assert 1.0 <= after <= 1.25


def test_preroll_seconds_helper() -> None:
    assert _preroll_seconds({"preroll_processing": {"preroll_added_s": 0.632}}) == 0.632
    assert _preroll_seconds({}) == 0.0


def test_upscale_lipsync_to_bookend(tmp_path: Path) -> None:
    src = tmp_path / "lowres.mp4"
    _make_test_clip(src, 1.0, with_audio=True)
    dst = tmp_path / "bookend.mp4"
    upscale_lipsync_to_bookend(src, dst, width=320, height=240)
    assert dst.is_file()
    dur = _ffprobe_duration(dst)
    assert 0.8 <= dur <= 1.2


def test_phase_a_zoom_constants() -> None:
    assert PHASE_A_ZOOM_END == 1.03
    assert PHASE_A_ZOOM_RAMP_SEC == 18.0
    assert PHASE_A_ZOOM_RAMP_DELAY_SEC == 1.5
