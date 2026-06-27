"""STITCH_OPERATOR_PLAYBACK_TIMESTAMPS_V1 — browser/QuickTime-safe MP4 for Stitcher preview."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib import ffmpeg_stitch as fs  # noqa: E402
import server_handlers.stitch_editor as se  # noqa: E402


def test_stitch_cached_mp4_playable_heals_negative_dts(tmp_path: Path) -> None:
    import subprocess

    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    fs.render_black_pause_clip(2.0, a)
    fs.render_black_pause_clip(2.0, b)
    bad = tmp_path / "stitch_preview_bad.mp4"
    lst = tmp_path / "list.txt"
    lst.write_text(f"file '{a.resolve()}'\nfile '{b.resolve()}'\n")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", str(bad),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    dts = fs.mp4_first_video_dts_s(bad)
    assert dts is not None
    if fs.mp4_quicktime_timestamps_safe(bad):
        pytest.skip("concat copy produced safe DTS on this ffmpeg build")
    assert se.stitch_cached_mp4_playable(bad)
    assert fs.mp4_operator_playback_timestamps_safe(bad)


def test_operator_gate_rejects_positive_first_video_dts(tmp_path: Path) -> None:
    """Positive first DTS with zero stream start must fail until browser normalize."""
    import subprocess

    src = tmp_path / "src.mp4"
    fs.render_black_pause_clip(5.0, src)
    gap = tmp_path / "gap.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src.resolve()),
            "-vf", "tpad=start_duration=1.833:start_mode=add", "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            str(gap),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    dts = fs.mp4_first_video_dts_s(gap)
    if dts is None or dts <= 0.001:
        pytest.skip("could not synthesize positive first DTS on this ffmpeg build")
    assert fs.mp4_quicktime_timestamps_safe(gap)
    assert not fs.mp4_operator_playback_timestamps_safe(gap)
    fs.normalize_mp4_browser_playback_timeline(gap)
    assert fs.mp4_operator_playback_timestamps_safe(gap)


def test_stitch_preview_serve_gate_wires_playable_check() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    block = src.split("def _serve_stitch_preview_file", 1)[1].split("\n    def ", 1)[0]
    assert "ensure_mp4_playback_timestamps" in block
    assert "stitch_cached_mp4_playable" in block


def test_rebase_clears_nonzero_stream_start_after_audio_mix_copy(tmp_path: Path) -> None:
    """Simulate post-amix -c:v copy MP4 with ~80ms stream start (Chrome mid-playback stall)."""
    import subprocess

    src = tmp_path / "src.mp4"
    fs.render_black_pause_clip(3.0, src)
    mixed = tmp_path / "mixed.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src.resolve()),
            "-i", str(src.resolve()),
            "-filter_complex", "[1:a]volume=0.3[a2];[0:a][a2]amix=inputs=2:duration=first[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            str(mixed),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    v_start = fs.ffprobe_video_start_time(mixed)
    if v_start <= 0.001:
        pytest.skip("amix copy produced zero start_time on this ffmpeg build")
    assert not fs.mp4_operator_playback_timestamps_safe(mixed)
    fs.rebase_mp4_stream_start_times(mixed)
    assert fs.mp4_operator_playback_timestamps_safe(mixed)
    assert fs.ffprobe_video_start_time(mixed) <= 0.001
    assert fs.ffprobe_audio_start_time(mixed) <= 0.001


def test_concat_kling_export_calls_playback_timestamp_pass() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    block = src.split("def concat_kling_o3_approved_beats", 1)[1].split("\ndef ", 1)[0]
    assert "ensure_mp4_playback_timestamps(out_path)" in block


def test_stitch_cached_playable_gate_requires_operator_timestamps_safe() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def stitch_cached_mp4_playable", 1)[1].split("\ndef ", 1)[0]
    assert "ensure_mp4_playback_timestamps" in block
    assert "mp4_operator_playback_timestamps_safe" in block
