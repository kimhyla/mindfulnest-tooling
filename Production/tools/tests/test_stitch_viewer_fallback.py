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


def test_stitcher_tab_uses_single_composer_with_muxed_preview() -> None:
    src = STITCHER_TAB.read_text(encoding="utf-8")
    assert "STITCHER_SINGLE_COMPOSER_V1" in src
    assert "composerVideoUrl" in src
    assert "STITCH_UNIFIED_PLAYBACK_V1" in src
    assert "STITCH_COMPOSER_MUX_FALLBACK_V1" in src
    assert "composerSlotUrls" in src
    assert "STITCH_COMPOSER_DRY_PLAYBACK_V1" in src
    assert "buildSlotPreview" in src


def test_stitch_track_focus_skips_empty_persisted_slot() -> None:
    focus = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchTrackFocus.ts"
    src = focus.read_text(encoding="utf-8")
    assert "STITCH_TRACK_FOCUS_V1" in src
    assert "pickTrackSlotForJob" in src
    assert "resolveTrackSlotForInteraction" in src
    assert "STITCH_EMPTY_SEGMENT_MS" in src
    assert "never stay on an empty persisted slot" in src
    stitcher = STITCHER_TAB.read_text(encoding="utf-8")
    assert "pickTrackSlotForJob" in stitcher
    assert "resolveTrackSlotForInteraction" in stitcher
    assert "STITCH_EMPTY_SEGMENT_MS" in stitcher
    assert "stitcherRefreshTick.value" in stitcher
    bg = BG_TAB.read_text(encoding="utf-8")
    assert "writePersistedTrackSlot" in bg
    assert "isStitchTrackSlotKey" in bg


def test_resolve_stitch_slot_source_video_url_handles_absolute_paths() -> None:
    ts = (
        REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchSlotVideo.ts"
    ).read_text(encoding="utf-8")
    assert "normalizeProductionRelativePath" in ts
    assert "indexOf(marker)" in ts or "indexOf('/Production/')" in ts


def test_beat_gen_preview_trim_is_browser_side_not_server_src_swap() -> None:
    src = BG_TAB.read_text(encoding="utf-8")
    assert "attachTrimStopListener" in src
    assert "draft — Apply Trim to save" in src
    assert "preview_only: true" not in src
