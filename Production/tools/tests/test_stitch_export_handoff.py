"""BG export → Stitcher handoff must not rely on Stitcher remount alone."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
BG = REPO / "tools" / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
COORD = REPO / "tools" / "storyboard-v2" / "src" / "components" / "ProducerSessionCoordinator.tsx"


def test_stitcher_subscribes_to_psl_stitch_cache() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "stitchCachedJob.value" in src
    assert "effect(() => {" in src
    assert "invalidateStitchSlotPlaybackCaches" in src
    assert "stitcherRefreshTick.value" in src
    assert "refreshTick" not in src.split("useState")[0]  # no stale local tick state


def test_bg_export_bumps_stitch_and_rehydrate_ticks() -> None:
    src = BG.read_text(encoding="utf-8")
    block = src.split("const finishExportTerminal = useCallback", 1)[1].split(
        "}, [exportScopeKey, stitchSlotForSegment]", 1,
    )[0]
    assert "stitcherRefreshTick.value += 1" in block
    assert "notifyStitchSlotExportApplied" in block


def test_coordinator_force_refreshes_stitch_on_tick() -> None:
    src = COORD.read_text(encoding="utf-8")
    assert "stitcherRefreshTick.value" in src
    assert "ensureStitchJobSession" in src
    assert "force: true" in src.split("stitcherRefreshTick", 1)[1]
