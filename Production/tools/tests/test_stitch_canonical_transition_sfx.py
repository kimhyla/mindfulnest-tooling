"""STITCH_CANONICAL_TRANSITIONS_V1 + STITCH_CANONICAL_TRANSITION_SFX_V1 durability."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_editor as se  # noqa: E402


def test_canonical_transitions_for_pipeline_ignores_drift() -> None:
    drift = [{"after_slot": 0, "kind": "cut", "fade_ms": 500, "audio_xfade_ms": 500}]
    out = se.canonical_stitch_transitions_for_pipeline(drift)
    assert out == se.default_stitch_transitions()
    assert [t["fade_ms"] for t in out] == list(se.STITCH_MODULE_BOUNDARY_PAIR_FADE_MS)
    for t in out:
        assert t["kind"] == "dissolve"
        assert t["audio_xfade_ms"] == 0


def test_boundary_sfx_map() -> None:
    assert se.STITCH_CANONICAL_BOUNDARY_SFX[0] == "magic_sound.mp3"
    assert se.STITCH_CANONICAL_BOUNDARY_SFX[1] == "windy_magic.mp3"
    assert se.STITCH_CANONICAL_BOUNDARY_SFX[2] == "magic_sound.mp3"
    assert se.STITCH_TRANSITION_SFX_PRE_ROLL_MS == 500
    assert se.STITCH_TRANSITION_SFX_POST_ROLL_MS == 500


def test_pipeline_applies_boundary_sfx_overlay() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "_stitch_apply_canonical_boundary_sfx" in src
    assert "stitch_boundary_sfx_baked_in_slot_cues" not in src
    assert "STITCH_CANONICAL_TRANSITION_SFX_V1" in (TOOLS / "server_handlers" / "stitch_editor.py").read_text(
        encoding="utf-8",
    )
    assert "STITCH_BOUNDARY_SFX_PIPELINE_ONLY_V1" in (
        TOOLS / "server_handlers" / "stitch_editor.py"
    ).read_text(encoding="utf-8")


def test_resolution_finale_constants() -> None:
    assert se.STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME == "outtro3.mp3"
    assert se.STITCH_RESOLUTION_FINALE_FADE_OUT_MS == 500
    assert se.STITCH_RESOLUTION_FINALE_OUTTRO_START_BEFORE_END_MS == 750
    assert se.STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS == 3250
    assert se.resolution_finale_black_hold_ms() == 2500


def test_milestone_finale_constants() -> None:
    assert se.STITCH_MILESTONE_FINALE_OUTTRO_FILENAME == "outtro3.mp3"
    assert se.STITCH_MILESTONE_FINALE_OUTTRO_FILENAME == se.STITCH_RESOLUTION_FINALE_OUTTRO_FILENAME
    assert se.STITCH_MILESTONE_FINALE_OUTTRO_PLAY_MS == se.STITCH_RESOLUTION_FINALE_OUTTRO_PLAY_MS
    assert se.milestone_finale_black_hold_ms() == se.resolution_finale_black_hold_ms()


def test_pipeline_applies_resolution_finale() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "_stitch_apply_resolution_finale" in src
    assert "_stitch_apply_milestone_finale" in src
    assert "stitch_pipeline_should_apply_resolution_finale" in src
    assert "stitch_pipeline_should_apply_milestone_finale" in src
    assert "STITCH_RESOLUTION_FINALE_V1" in (
        TOOLS / "server_handlers" / "stitch_editor.py"
    ).read_text(encoding="utf-8")
    assert "STITCH_MILESTONE_FINALE_V1" in (
        TOOLS / "server_handlers" / "stitch_editor.py"
    ).read_text(encoding="utf-8")
