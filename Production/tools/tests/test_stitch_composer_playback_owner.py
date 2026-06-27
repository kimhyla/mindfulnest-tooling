"""STITCH_COMPOSER_PLAYBACK_OWNER_V1 — muxed composer video must not be paused by waveform bus."""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
STORYBOARD = TOOLS / "storyboard-v2" / "src"


def test_waveform_bus_skips_composer_playback_owner() -> None:
    src = (STORYBOARD / "utils" / "waveformPlaybackBus.ts").read_text(encoding="utf-8")
    assert "isStitchComposerPlaybackOwner" in src
    block = src.split("function pauseAppMediaElements", 1)[1].split("\n\n", 1)[0]
    assert "isStitchComposerPlaybackOwner(el)" in block


def test_waveform_timeline_keepalive_skips_composer_playback_owner() -> None:
    src = (STORYBOARD / "components" / "phase" / "WaveformTimeline.tsx").read_text(
        encoding="utf-8",
    )
    assert "isStitchComposerPlaybackOwner" in src
    block = src.split("const pauseIfHiddenAndStopMedia = () => {", 1)[1].split("\n    };", 1)[0]
    assert "isStitchComposerPlaybackOwner(el)" in block
    assert "STITCH_KEEPALIVE_PAUSE_WHEN_HIDDEN_V1" in block
    assert "if (!pane.hidden) return" in block


def test_stitcher_composer_video_marks_playback_owner() -> None:
    pool = (STORYBOARD / "components" / "StitchComposerVideoPool.tsx").read_text(encoding="utf-8")
    assert 'data-stitch-composer-playback-owner={STITCH_COMPOSER_PLAYBACK_OWNER_V1}' in pool
