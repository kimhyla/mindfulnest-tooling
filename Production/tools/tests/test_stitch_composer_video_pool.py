"""STITCH_COMPOSER_VIDEO_POOL_V1 — four persistent slot videos for instant phase switch."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
POOL = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitchComposerVideoPool.tsx"
CSS = REPO / "tools" / "storyboard-v2" / "src" / "app.css"


def test_stitch_composer_video_pool_component() -> None:
    src = POOL.read_text(encoding="utf-8")
    assert "STITCH_COMPOSER_VIDEO_POOL_V1" in src
    assert "data-stitch-slot" in src
    assert "is-pool-hidden" in src
    assert "is-pool-active" in src
    assert "preload=\"auto\"" in src
    for slot in ("intro", "phase_a", "phase_b", "resolution"):
        assert slot in src


def test_stitcher_tab_wires_video_pool() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "StitchComposerVideoPool" in src
    assert "STITCH_COMPOSER_VIDEO_POOL_V1" in src
    assert "composerSlotUrls" in src
    assert "composerPoolRef" in src
    assert "data-stitch-composer-video-pool={STITCH_COMPOSER_VIDEO_POOL_V1}" in src


def test_pool_hidden_styles_present() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "mn-stitcher-composer-video-pool" in css
    assert "is-pool-hidden" in css
    assert "is-pool-active" in css
