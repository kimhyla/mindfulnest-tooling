"""Canonical intro_tail compose caps LD-737 burst via manifest (WYSIWYG, not export trim)."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from teleport_intro_kit import _manifest_burst_use_s  # noqa: E402


def test_manifest_burst_use_s_prefers_canonical_burst_max(tmp_path: Path) -> None:
    burst = tmp_path / "burst.mp4"
    burst.write_bytes(b"x")
    manifest = {
        "teleport_glass": {"duration_s": 5.0},
        "intro_canonical_beats": {"canonical_burst_max_s": 4.0},
    }

    import teleport_intro_kit as tik

    orig = tik.ffprobe_duration
    try:
        tik.ffprobe_duration = lambda _p: 5.04
        assert _manifest_burst_use_s(manifest, burst) == 4.0
    finally:
        tik.ffprobe_duration = orig


def test_manifest_burst_use_s_falls_back_to_teleport_glass_duration() -> None:
    manifest = {"teleport_glass": {"duration_s": 3.5}}

    import teleport_intro_kit as tik

    orig = tik.ffprobe_duration
    try:
        tik.ffprobe_duration = lambda _p: 5.04
        assert _manifest_burst_use_s(manifest, Path("/tmp/x.mp4")) == 3.5
    finally:
        tik.ffprobe_duration = orig
