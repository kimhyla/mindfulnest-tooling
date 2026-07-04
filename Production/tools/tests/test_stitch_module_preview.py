"""Stitch module preview defaults and job hydration."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_editor as se  # noqa: E402


def test_default_stitch_transitions_late_fade_budgets() -> None:
    trans = se.default_stitch_transitions()
    assert len(trans) == 3
    for i, t in enumerate(trans):
        assert t["after_slot"] == i
        assert t["kind"] == "dissolve"
        assert t["fade_ms"] == se.STITCH_MODULE_BOUNDARY_PAIR_FADE_MS[i]
        assert t["audio_xfade_ms"] == 0


def test_stitch_preview_includes_slot_start_offsets() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    assert '"slot_start_offsets_ms": slot_start_offsets_ms' in src
