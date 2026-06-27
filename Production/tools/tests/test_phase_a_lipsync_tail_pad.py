"""Durable guards: Phase A ByteDance trim must keep LIPSYNC_PAD_END face-return tail."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import lipsync_sender as ls  # noqa: E402
import phase_a_chipper_bytedance_lipsync as bd  # noqa: E402
from production_server import _ffprobe_duration  # noqa: E402


def test_trim_padded_lipsync_segment_keeps_face_return_tail() -> None:
    src = Path(bd.__file__).read_text(encoding="utf-8")
    assert "speech_duration_s + tail_s" in src
    assert "LIPSYNC_PAD_END" in src or "face_return_tail_s" in src


def test_trim_padded_duration_includes_tail(tmp_path: Path) -> None:
    """Simulated ByteDance raw: 0.5s lead + 2.0s speech + 2.5s tail silence."""
    speech_s = 2.0
    pad_start = ls.LIPSYNC_PAD_START
    pad_end = ls.LIPSYNC_PAD_END
    total = pad_start + speech_s + pad_end
    raw = tmp_path / "raw_bd.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={total:.3f}:r=24",
            "-f", "lavfi", "-i", f"sine=f=440:duration={total:.3f}",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(raw),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    dst = tmp_path / "trimmed.mp4"
    bd.trim_padded_lipsync_segment(raw, dst, speech_s)
    dur = _ffprobe_duration(dst)
    # speech + full tail (not speech-only freeze)
    assert dur >= speech_s + pad_end - 0.15
    assert dur <= speech_s + pad_end + 0.15


def test_ensure_stem_floor_uses_tail_loop_not_long_clone() -> None:
    src = Path(__file__).resolve().parent.parent / "phase_a_av_post.py"
    text = src.read_text(encoding="utf-8")
    assert "tail_loop" in text
    assert "crossfade_loop_video" in text
