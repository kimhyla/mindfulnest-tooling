"""Beat Gen ↑/↓ reorder controls — UI contract + stitcher keep-alive."""
from __future__ import annotations

from pathlib import Path


def test_bg_beat_reorder_buttons_wired():
    src = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "BgTab.tsx"
    ).read_text(encoding="utf-8")
    assert "bg_reorder_beats" in src
    assert "bg-beat-move-up-" in src
    assert "bg-beat-move-down-" in src
    assert "scope_video_role: activeTargetVideo.value" in src


def test_stitcher_keepalive_mounted():
    app = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "app.tsx"
    ).read_text(encoding="utf-8")
    assert "StitcherKeepAlive" in app
    assert "pane-stitcher-keepalive" in app


def test_stitcher_canonical_only_legacy_fill_empty():
    tab = (
        Path(__file__).resolve().parent.parent
        / "storyboard-v2"
        / "src"
        / "components"
        / "StitcherTab.tsx"
    ).read_text(encoding="utf-8")
    assert "onlyEmpty" in tab or "onlyEmpty = true" in tab
    assert "jobLoadedForEventRef" in tab
    assert "lastViewerVideoPathRef" in tab
