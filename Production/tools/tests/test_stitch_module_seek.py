"""Stitcher module preview seek — LD-828 durability contracts."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
MOD = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchModulePreview.ts"
STITCH_EDITOR = REPO / "tools" / "server_handlers" / "stitch_editor.py"


def test_stitcher_gates_module_seek_on_module_preview_url() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "if (!modulePreviewUrl)" in src
    assert "video.currentTime = 0" in src
    assert "LD-827 fallback" in src


def test_stitcher_stable_video_key_for_module_preview() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "stitcher-module-preview" in src
    assert "key={modulePreviewUrl ? 'stitcher-module-preview'" in src


def test_preview_api_returns_slot_start_offsets_ms() -> None:
    src = STITCH_EDITOR.read_text(encoding="utf-8")
    assert "slot_start_offsets_ms" in src
    assert '"slot_start_offsets_ms": slot_start_offsets_ms' in src


def test_module_preview_seek_helper_prefers_start_offsets() -> None:
    src = MOD.read_text(encoding="utf-8")
    assert "export function modulePreviewSeekOffsetMs" in src
    assert "slotStartOffsetsMs[idx]" in src
