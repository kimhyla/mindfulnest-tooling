"""Export concat uses re-encode path (avoids -c copy A/V desync)."""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from beat_generator import _ffmpeg_concat_kling_clips_reencode  # noqa: E402


def test_concat_single_clip_is_copy(tmp_path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"fake")
    dest = tmp_path / "out.mp4"
    _ffmpeg_concat_kling_clips_reencode([src], dest)
    assert dest.read_bytes() == b"fake"


def test_concat_reencode_produces_aligned_av(tmp_path):
    """Integration: two tiny synthetic clips → single output with near-equal A/V duration."""
    import subprocess

    def _make_clip(path: Path, color: str, dur: float) -> None:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:d={dur}",
                "-f", "lavfi", "-i", f"sine=f=440:duration={dur}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest",
                str(path),
            ],
            check=True,
            timeout=60,
        )

    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    out = tmp_path / "joined.mp4"
    _make_clip(a, "red", 0.5)
    _make_clip(b, "blue", 0.5)
    _ffmpeg_concat_kling_clips_reencode([a, b], out)
    assert out.is_file()
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,duration",
            "-of", "csv=p=0",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    lines = [ln.strip() for ln in probe.stdout.strip().splitlines() if ln.strip()]
    by_type = {}
    for row in lines:
        codec_type, dur = row.split(",")
        by_type[codec_type] = float(dur)
    assert "video" in by_type and "audio" in by_type
    assert abs(by_type["video"] - by_type["audio"]) < 0.15


def test_concat_reencode_mixed_silent_and_audio_clips(tmp_path):
    """Magic-on-still (no audio) + Kling/TTS clip must concat without filter errors."""
    import subprocess

    def _make_video_only(path: Path, color: str, dur: float) -> None:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:d={dur}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                str(path),
            ],
            check=True,
            timeout=60,
        )

    def _make_av(path: Path, color: str, dur: float) -> None:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", f"color=c={color}:s=640x360:d={dur}",
                "-f", "lavfi", "-i", f"sine=f=440:duration={dur}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest",
                str(path),
            ],
            check=True,
            timeout=60,
        )

    silent = tmp_path / "magic_still.mp4"
    voiced = tmp_path / "kling.mp4"
    out = tmp_path / "joined.mp4"
    _make_video_only(silent, "green", 0.4)
    _make_av(voiced, "red", 0.5)
    _ffmpeg_concat_kling_clips_reencode([voiced, silent, voiced], out)
    assert out.is_file()
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    types = {ln.strip() for ln in probe.stdout.strip().splitlines() if ln.strip()}
    assert types == {"video", "audio"}
