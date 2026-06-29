"""STITCH_SLOT_ARTIFACT_FRESHNESS_V1 — session must not trust stale mux when server cleared artifacts."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchSlotSessionCache.ts"
HYDRATE = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchJobMediaHydrate.ts"
LINEAGE = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchSlotVideoLineage.ts"
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
TEST = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "__tests__" / "stitchSlotArtifactFreshness.test.ts"


def test_is_mux_session_fresh_requires_server_artifact() -> None:
    src = CACHE.read_text(encoding="utf-8")
    assert "stitchSlotServerArtifactReady" in src
    block = src.split("export function isMuxSessionFresh", 1)[1].split("export function isWaveformSessionFresh", 1)[0]
    assert "stitchSlotServerArtifactReady(slotData)" in block
    assert "return false" in block


def test_hydrate_purges_stale_playback_when_ambient_missing() -> None:
    src = HYDRATE.read_text(encoding="utf-8")
    assert "purgeStitchSlotPlaybackCache" in src
    ambient = src.split("} else if (requiresAmbientMix)", 1)[1].split("if (slot.waveform_peaks_hash", 1)[0]
    assert "purgeStitchSlotPlaybackCache(sessionKey, slotKey)" in ambient


def test_stitcher_strips_preview_urls_for_artifact_rebuild() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "stripPreviewUrlsForArtifactRebuild" in src
    assert "hydrated.slotsNeedingAmbientMix" in src


def test_artifact_freshness_node_test_exists() -> None:
    assert TEST.is_file()
    text = TEST.read_text(encoding="utf-8")
    assert "stitchSlotServerArtifactReady" in text
    assert "purgeStitchSlotPlaybackCache" in text or "slotsNeedingAmbientMix" in text
