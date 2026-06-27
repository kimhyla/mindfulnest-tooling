"""Phase B whiteout fade — intro-style video-only tail fade (audio copy)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers.phases import (  # noqa: E402
    _apply_whiteout_fade,
)


def test_whiteout_constants_match_intro_pattern() -> None:
    from server_handlers.phases import (  # noqa: PLC0415
        PHASE_B_WHITEOUT_ENABLED,
        PHASE_B_WHITEOUT_FADE_AUDIO,
    )

    assert PHASE_B_WHITEOUT_ENABLED is False
    assert PHASE_B_WHITEOUT_FADE_AUDIO is False


def test_phase_b_lipsync_write_skips_whiteout() -> None:
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    block = src.split("def _write_phase_b_lipsync_complete", 1)[1].split("\ndef ", 1)[0]
    assert "_apply_whiteout_fade" not in block


def test_apply_whiteout_fade_uses_audio_copy_not_afade(tmp_path: Path) -> None:
    from server_handlers.phases import PHASE_B_WHITEOUT_ENABLED  # noqa: PLC0415

    assert PHASE_B_WHITEOUT_ENABLED is False
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

    assert not captured, "whiteout disabled — ffmpeg must not run"
    assert video.read_bytes() == b"fake"
