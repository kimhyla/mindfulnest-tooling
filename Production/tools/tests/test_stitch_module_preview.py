"""Stitch module preview defaults and job hydration."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_editor as se  # noqa: E402


def test_default_stitch_transitions_dissolve_2800ms() -> None:
    trans = se.default_stitch_transitions()
    assert len(trans) == 3
    for i, t in enumerate(trans):
        assert t["after_slot"] == i
        assert t["kind"] == "dissolve"
        assert t["fade_ms"] == 2800
        assert t["audio_xfade_ms"] == 2800
