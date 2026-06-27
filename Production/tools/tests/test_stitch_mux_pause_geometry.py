"""STITCH_MUX_PAUSE_ON_GEOMETRY_V1 — pause composer on geometry change; no defer-while-playing."""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_stitcher_tab_wires_pause_on_geometry() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    assert "STITCH_MUX_PAUSE_ON_GEOMETRY_V1" in src
    assert "Paused — updating SFX preview (video stays loaded)" in src
    assert "pauseAllExcept(null)" in src
    assert "STITCH_INSTANT_GEOMETRY_BASELINE_V1" in src
    assert "geometryBaseline" in src
    assert "pendingQuietMuxUrlRef" not in src


def test_build_slot_preview_no_dry_fallback_for_mux_slots() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    block = src.split("const mayBindDry = ", 1)[1].split("const dryUrl = mayBindDry", 1)[0]
    assert "stitchSlotRequiresMuxedPreview" in block
    assert "stitchSlotRequiresAmbientMix" in block
