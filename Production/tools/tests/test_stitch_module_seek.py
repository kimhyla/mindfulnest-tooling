"""Stitcher single slot composer — LD-828 durability contracts."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
MOD = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchModulePreview.ts"
STITCH_EDITOR = REPO / "tools" / "server_handlers" / "stitch_editor.py"


def test_stitcher_builds_per_slot_preview_for_composer() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "buildSlotPreview" in src
    assert "seekComposerTo" in src
    assert "stitcher-composer-video" in src


def test_stitcher_multiphase_click_switches_slot_not_module_offset() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "onMultiPhaseSegmentClick" in src
    assert "seekComposerTo(0" in src
    assert "STITCHER_SINGLE_COMPOSER_V1" in src


def test_preview_api_returns_slot_start_offsets_ms() -> None:
    src = STITCH_EDITOR.read_text(encoding="utf-8")
    assert "slot_start_offsets_ms" in src
    assert '"slot_start_offsets_ms": slot_start_offsets_ms' in src


def test_module_preview_seek_helper_prefers_start_offsets() -> None:
    src = MOD.read_text(encoding="utf-8")
    assert "export function modulePreviewSeekOffsetMs" in src
    assert "slotStartOffsetsMs[idx]" in src
