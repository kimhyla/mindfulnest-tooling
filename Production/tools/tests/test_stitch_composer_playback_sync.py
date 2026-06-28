"""Stitcher composer — unified muxed playback (STITCH_UNIFIED_PLAYBACK_V1)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
SLOT_WF = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherSlotWaveform.tsx"
WAVEFORM = REPO / "tools" / "storyboard-v2" / "src" / "components" / "phase" / "WaveformTimeline.tsx"


def test_composer_prefers_muxed_preview_with_raw_fallback() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "STITCH_UNIFIED_PLAYBACK_V1" in src
    assert "STITCH_COMPOSER_MUX_FALLBACK_V1" in src
    assert "composerSlotUrls" in src
    assert "resolveSlotPlaybackPreviewUrl" in src


def test_composer_video_is_unmuted_single_clock() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    pool_src = (REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitchComposerVideoPool.tsx").read_text(encoding="utf-8")
    assert "muted" not in pool_src
    assert "linkedVideo=" not in src.split("StitcherSlotWaveform")[1].split("onSfxDrop")[0]
    assert "linkedVideoScrubOnly" not in src.split("displayOnly")[1].split("onSfxDrop")[0]
    assert "playbackControl=" not in src.split("displayOnly")[1].split("onSfxDrop")[0]


def test_stitcher_slot_waveform_display_only_peaks_path() -> None:
    src = SLOT_WF.read_text(encoding="utf-8")
    assert "displayOnly" in src
    assert "peaks_url" in src
    assert "STITCH_UNIFIED_PLAYBACK_V1" in src
    assert "displayPeaks" in src


def test_waveform_timeline_display_only_mode() -> None:
    src = WAVEFORM.read_text(encoding="utf-8")
    assert "displayOnly" in src
    assert "onMasterSeek" in src
    assert "masterVideo" in src
    assert "masterVideoSrc" in src
    assert "STITCH_COMPOSER_MASTER_VIDEO_SYNC_V1" in src
    assert "requestAnimationFrame" in src.split("masterVideoSrc", 1)[1]
    assert "data-display-only-waveform" in src
    assert "waveform-display-only-label" in src


def test_composer_passes_master_video_src_for_playhead_rebind() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "masterVideoSrc: composerVideoUrl" in src
