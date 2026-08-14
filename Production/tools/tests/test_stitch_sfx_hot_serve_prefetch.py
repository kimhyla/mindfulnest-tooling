"""STITCH_SFX_HOT_SERVE_PREFETCH_V1 — client-mix SFX must prefetch + retry /files."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ENGINE = (
    REPO
    / "Production"
    / "tools"
    / "storyboard-v2"
    / "src"
    / "audio"
    / "StitchSlotAudioMixEngine.ts"
)
FETCH = (
    REPO
    / "Production"
    / "tools"
    / "storyboard-v2"
    / "src"
    / "utils"
    / "stitchSfxFetch.ts"
)
DURABILITY = (
    REPO
    / "Production"
    / "scripts"
    / "verify_stitch_sfx_playback_truth_durability.sh"
)


def test_sfx_engine_prefetches_before_play_schedule():
    text = ENGINE.read_text(encoding="utf-8")
    assert "STITCH_SFX_HOT_SERVE_PREFETCH_V1" in text
    assert "prefetchAllSfx" in text
    assert "prefetchPromise" in text
    assert "SFX_PREFETCH" in text
    assert "SFX_LOAD_FAILED" in text
    assert "fetchStitchSfxArrayBuffer" in text
    # Must not load only inside schedule without attach prefetch.
    assert "this.prefetchPromise = this.prefetchAllSfx()" in text


def test_sfx_fetch_retries_hot_serve_503():
    text = FETCH.read_text(encoding="utf-8")
    assert "STITCH_SFX_FETCH_MAX_ATTEMPTS" in text
    assert "stitchSfxFetchIsRetryableStatus" in text
    assert "503" in text


def test_sfx_durability_gate_locks_prefetch_marker():
    text = DURABILITY.read_text(encoding="utf-8")
    assert "STITCH_SFX_HOT_SERVE_PREFETCH_V1" in text
    assert "stitchSfxFetch.test.ts" in text
