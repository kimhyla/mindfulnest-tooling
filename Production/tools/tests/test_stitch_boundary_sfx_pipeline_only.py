"""STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1 — boundary SFX spans dissolve, not slot tail."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_editor as se  # noqa: E402


def test_phase_a_b_not_in_slot_canonical_default_sfx() -> None:
    assert "intro" in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX
    assert "resolution" in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX
    assert "phase_a" not in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX
    assert "phase_b" not in se.STITCH_SLOT_CANONICAL_DEFAULT_SFX


def test_strip_removes_stale_boundary_tail_cues() -> None:
    slots = {
        "phase_a": {
            "video_path": "Production/Event_2/a.mp4",
            "video_dur_ms": 22337,
            "sfx_cues": [
                {
                    "name": "windy_magic.mp3",
                    "auto_default": True,
                    "offset_ms": 20189,
                    "duration_ms": 2148,
                },
            ],
        },
        "phase_b": {
            "video_path": "Production/Event_2/b.mp4",
            "video_dur_ms": 128700,
            "sfx_cues": [
                {
                    "name": "magic_sound.mp3",
                    "auto_default": True,
                    "offset_ms": 122828,
                    "duration_ms": 5880,
                },
            ],
        },
        "intro": {
            "video_path": "Production/Event_2/intro.mp4",
            "sfx_cues": [
                {"name": "whoosh sound.mp3", "auto_default": True, "offset_ms": 1000},
            ],
        },
    }
    assert se.strip_stale_pipeline_boundary_slot_cues(slots) is True
    assert slots["phase_a"]["sfx_cues"] == []
    assert slots["phase_b"]["sfx_cues"] == []
    assert len(slots["intro"]["sfx_cues"]) == 1


def test_boundary_sfx_overlay_spans_dissolve_not_tail_only() -> None:
    clip_dur_ms = 38986
    pair_ms = 3800
    plan = se.boundary_sfx_overlay_plan(clip_dur_ms, pair_ms)
    assert plan["out_ms"] == 600
    assert plan["black_ms"] == 2600
    assert plan["in_ms"] == 600
    assert plan["total_span_ms"] == 500 + 600 + 2600 + 600 + 500
    # SFX seg1 starts 1100ms before clip end — then continues through black + incoming fade.
    assert plan["seg1_offset_ms"] == clip_dur_ms - (500 + 600)
    assert plan["seg1_offset_ms"] > clip_dur_ms - 3000  # not a 3s-only tail window
    assert plan["total_span_ms"] > 3000


def test_production_server_no_boundary_skip() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "stitch_boundary_sfx_baked_in_slot_cues" not in src
