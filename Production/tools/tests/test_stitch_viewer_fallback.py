"""LD-827 — Stitcher slot composer falls back to direct slot /files URLs."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCH_MODULE_PREVIEW = (
    REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchModulePreview.ts"
)
STITCHER_TAB = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
BG_TAB = REPO / "tools" / "storyboard-v2" / "src" / "components" / "BgTab.tsx"


def test_resolve_module_viewer_video_url_falls_back_to_source() -> None:
    src = STITCH_MODULE_PREVIEW.read_text(encoding="utf-8")
    assert "export function resolveModuleViewerVideoUrl" in src
    assert "return opts.modulePreviewUrl ?? opts.viewerSourceUrl" in src


def test_stitcher_tab_uses_single_composer_with_processed_fallback() -> None:
    src = STITCHER_TAB.read_text(encoding="utf-8")
    assert "STITCHER_SINGLE_COMPOSER_V1" in src
    assert "composerVideoUrl" in src
    assert "previewUrls[viewerSlot]" in src
    assert "viewerSourceUrl" in src
    assert "buildSlotPreview" in src


def test_beat_gen_preview_trim_is_browser_side_not_server_src_swap() -> None:
    src = BG_TAB.read_text(encoding="utf-8")
    assert "attachTrimStopListener" in src
    assert "draft — Apply Trim to save" in src
    assert "preview_only: true" not in src
