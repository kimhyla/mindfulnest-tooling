"""Canonical mirror tail must compose from full speak — not Beat Gen export trims."""
from __future__ import annotations

from pathlib import Path


def test_resolve_speak_clip_for_canonical_skips_sidecar_trim():
    src = (Path(__file__).resolve().parent.parent / "teleport_intro_kit.py").read_text(
        encoding="utf-8",
    )
    block = src.split("def _resolve_speak_clip_for_canonical")[1].split("\ndef ", 1)[0]
    assert "materialize_kling_o3_trimmed_clip" not in block
    assert "export trims not applied at compose" in block
    assert "MIN_CANONICAL_INTRO_TAIL_DURATION_S" in src
    assert "intro_tail too short" in src
