"""STITCH_MUX_SRC_IDENTITY_V1 — composer src bound to mux hash, not quiet rebuild events."""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_stitcher_tab_wires_mux_src_identity() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    assert "STITCH_MUX_SRC_IDENTITY_V1" in src
    assert "quiet_rebuild" in src
    assert "explicit_preview" in src
    assert "STITCH_MUX_DEFER_DURING_PLAYBACK_V1" not in src


def test_stitch_mux_preview_identity_module_exists() -> None:
    path = TOOLS / "storyboard-v2" / "src" / "utils" / "stitchMuxPreviewIdentity.ts"
    text = path.read_text(encoding="utf-8")
    assert "shouldUpdateComposerMuxSrc" in text
    assert "quiet_rebuild" in text
