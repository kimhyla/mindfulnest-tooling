"""Phase A lipsync must never ship shorter than the voice stem."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase_a_av_post import ensure_stem_duration_floor, trim_av_trailing_silence  # noqa: E402
from production_server import _ffprobe_duration  # noqa: E402


def _make_av(path: Path, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={duration:.3f}:r=24",
            "-f", "lavfi", "-i", f"sine=f=440:duration={duration:.3f}",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def test_trim_av_trailing_silence_respects_max_trim_s(tmp_path: Path) -> None:
    src = tmp_path / "clip.mp4"
    _make_av(src, 3.0)
    dst = tmp_path / "tailed.mp4"
    _, trimmed = trim_av_trailing_silence(src, dst, max_trim_s=0.0)
    assert trimmed == 0.0
    assert abs(_ffprobe_duration(dst) - 3.0) < 0.15


def test_ensure_stem_duration_floor_pads_short_output(tmp_path: Path) -> None:
    src = tmp_path / "short.mp4"
    _make_av(src, 2.0)
    dst = tmp_path / "floored.mp4"
    _, pad_s = ensure_stem_duration_floor(src, dst, 2.5)
    assert pad_s > 0.4
    assert abs(_ffprobe_duration(dst) - 2.5) < 0.12


def test_sweep_phase_a_resume_exports_marker() -> None:
    src = (HERE / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    assert "sweep_phase_a_lipsync_resume" in src
    assert "phase_a_lipsync_pending_output" in src
    assert "resume=True" in src
