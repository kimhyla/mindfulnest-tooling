"""Phase A ByteDance idle-base extension — crossfade loop (not hard concat)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import phase_a_chipper_bytedance_lipsync as bd  # noqa: E402
from phase_a_chipper_lipsync_base import (  # noqa: E402
    DEFAULT_CLIP_ID,
    LEGACY_CLIP_ID,
    PHASE_A_BASE_CLIP_DURATION_S,
)
from production_server import _ffprobe_duration  # noqa: E402


def _make_test_clip(path: Path, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=red:s=640x480:d={duration:.3f}:r=24",
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )


def test_bytedance_uses_crossfade_extend_not_forward_loop() -> None:
    src = Path(bd.__file__).read_text(encoding="utf-8")
    assert "def extend_idle_base" in src
    assert "crossfade_loop_video" in src
    assert "def forward_loop" not in src
    assert "idle_base_crossfade_loop" in src
    assert "idle_base_forward_loop" not in src


def test_extend_idle_base_reaches_target_duration(tmp_path: Path) -> None:
    src = tmp_path / "base.mp4"
    dst = tmp_path / "extended.mp4"
    _make_test_clip(src, 2.0)
    bd.extend_idle_base(src, dst, 7.5)
    dur = _ffprobe_duration(dst)
    assert 7.2 <= dur <= 7.8


def test_phase_a_base_clip_defaults_v2_15s() -> None:
    assert DEFAULT_CLIP_ID == "arlo_idle_wizard_desk_v2"
    assert PHASE_A_BASE_CLIP_DURATION_S == 15
    assert LEGACY_CLIP_ID == "arlo_idle_wizard_desk_v1"
