"""STITCH_DRY_HOT_SERVE_PLAYBACK_V1 — dry/four-files composer never binds cold /files."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
HOT = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchDryHotServePlayback.ts"


def test_stitch_dry_hot_serve_marker_and_resolve_wire() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    util = HOT.read_text(encoding="utf-8")
    assert "STITCH_DRY_HOT_SERVE_PLAYBACK_V1" in src
    assert "STITCH_DRY_HOT_SERVE_PLAYBACK_V1" in util
    assert "resolveStitchDrySlotHotPlaybackUrl" in src
    assert "dryHotUrls" in src
    assert 'data-stitch-dry-hot-serve-playback={STITCH_DRY_HOT_SERVE_PLAYBACK_V1}' in src


def test_dry_composer_urls_never_bind_files_directly() -> None:
    """composerSlotUrls dry branch must use dryHotUrls, not resolveDrySlotSourceVideoUrl."""
    src = STITCHER.read_text(encoding="utf-8")
    block = src.split("const composerSlotUrls = useMemo(() => {", 1)[1].split(
        "\n  // Inline preview player state", 1
    )[0]
    assert "stitchSlotRequiresHotServeComposerUrl" in block
    assert "dryHotUrls" in block
    assert "resolveDrySlotSourceVideoUrl" not in block


def test_hot_serve_helper_never_returns_files_url() -> None:
    util = HOT.read_text(encoding="utf-8")
    assert "resolveClipPlaybackTruth" in util
    assert "/api/media/playback/" in util
    # Warm poke may fetch /files, but bind URL must not be /files.
    assert "isHotPlaybackApiUrl" in util
    assert "return null" in util
    # Guard: must not `return filesUrl` as the playback bind.
    assert "return filesUrl" not in util
    assert "return resolveDrySlotSourceVideoUrl" not in util


def test_pool_error_does_not_fallback_to_files_for_dry_slots() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    block = src.split("const onPoolSlotError = ", 1)[1].split(
        "const onPreviewSlot = ", 1
    )[0]
    assert "stitchSlotRequiresHotServeComposerUrl" in block
    assert "STITCH_DRY_HOT_SERVE_PLAYBACK_V1" in block
    # Dry branch returns before resolveDrySlotSourceVideoUrl fallback.
    dry_gate = block.index("stitchSlotRequiresHotServeComposerUrl")
    dry_return = block.index("return;", dry_gate)
    files_fallback = block.index("resolveDrySlotSourceVideoUrl", dry_return)
    assert dry_return < files_fallback
