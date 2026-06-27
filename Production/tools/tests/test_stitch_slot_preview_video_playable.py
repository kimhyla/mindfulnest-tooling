"""STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1 — corrupt preview cache + black video durability."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
POOL = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitchComposerVideoPool.tsx"
FFMPEG_STITCH = REPO / "tools" / "credentials_lib" / "ffmpeg_stitch.py"
SERVER = REPO / "tools" / "production_server.py"


def test_ffmpeg_stitch_exports_decode_validator() -> None:
    src = FFMPEG_STITCH.read_text(encoding="utf-8")
    assert "def mp4_decodes_cleanly" in src
    assert '"-loglevel", "fatal"' in src


def test_preview_cache_validation_requires_clean_decode() -> None:
    src = FFMPEG_STITCH.read_text(encoding="utf-8")
    assert "stitch_preview_decode_timeout_s" in src
    assert "mp4_decodes_cleanly(" in src


def test_stitch_build_pipeline_fingerprints_slot_finals() -> None:
    src = SERVER.read_text(encoding="utf-8")
    assert "st_mtime_ns" in src
    assert "STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1" in src
    assert "len(slot_finals) == 1" in src
    assert "_shutil.copy(slot_finals[0], tmp)" in src


def test_stitcher_client_falls_back_on_video_error() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    pool = POOL.read_text(encoding="utf-8")
    assert "STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1" in src
    assert "STITCH_UNIFIED_PLAYBACK_V1" in src
    assert "onPoolSlotError" in src
    assert "onSlotError" in pool
    assert "onPoolSlotCanPlay" in src
    assert "clearCachedStitcherPreview" in src
    assert "STITCH_MUX_SRC_IDENTITY_V1" in src
    assert "STITCH_COMPOSER_VIDEO_POOL_V1" in src
    assert "preload=\"auto\"" in pool
    assert "STITCH_COMPOSER_DRY_PLAYBACK_V1" in src
    assert "muxPreviewFailed" not in src
