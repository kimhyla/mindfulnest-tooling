"""Phase B whiteout fade — intro-style video-only tail fade (audio copy)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers.phases import (  # noqa: E402
    PHASE_B_WHITEOUT_DURATION_SEC,
    PHASE_B_WHITEOUT_FADE_AUDIO,
    _apply_whiteout_fade,
)


def test_whiteout_constants_match_intro_pattern() -> None:
    assert PHASE_B_WHITEOUT_FADE_AUDIO is False
    assert PHASE_B_WHITEOUT_DURATION_SEC == 0.6


def test_apply_whiteout_fade_uses_audio_copy_not_afade(tmp_path: Path) -> None:
    video = tmp_path / "phase_b_lipsync_test.mp4"
    video.write_bytes(b"fake")
    captured: list[list[str]] = []

    def _run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return mock.Mock(stdout="10.000\n", returncode=0)
        captured.append(list(cmd))
        tmp = video.with_suffix(".whiteout_tmp.mp4")
        tmp.write_bytes(b"out")
        return mock.Mock(returncode=0)

    with mock.patch("server_handlers.phases.subprocess.run", side_effect=_run):
        _apply_whiteout_fade(video)

    assert captured, "ffmpeg command not captured"
    cmd = captured[0]
    assert "-c:a" in cmd
    assert "copy" in cmd
    assert "-af" not in cmd
    vf_idx = cmd.index("-vf")
    assert "fade=out" in cmd[vf_idx + 1]
    assert f"d={PHASE_B_WHITEOUT_DURATION_SEC:.3f}" in cmd[vf_idx + 1]
    assert video.is_file()
