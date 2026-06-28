"""STITCH_COMPOSER_DRY_PLAYBACK_V1 — subtractive composer playback durability."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
HYDRATE = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchJobMediaHydrate.ts"


def test_stitcher_tab_single_playback_path_without_mux_failure_gate() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "STITCH_COMPOSER_DRY_PLAYBACK_V1" in src
    assert "muxPreviewFailed" not in src
    assert "composerVideoUrl = composerSlotUrls[viewerSlot]" in src
    assert "resolveSlotPlaybackPreviewUrl" in src


def test_resolve_slot_playback_preview_url_has_dry_floor() -> None:
    src = HYDRATE.read_text(encoding="utf-8")
    block = src.split("export function resolveSlotPlaybackPreviewUrl", 1)[1].split(
        "\nexport ", 1
    )[0]
    assert "resolveDrySlotSourceVideoUrl" in block
    assert "if (!slot?.video_path) return undefined" in block
