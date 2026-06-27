"""STITCH_SLOT_SESSION_CACHE_V1 — multiphase slot preview persists within event session."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "tools" / "storyboard-v2" / "src" / "utils" / "stitchSlotSessionCache.ts"
STITCHER = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx"
WAVEFORM = REPO / "tools" / "storyboard-v2" / "src" / "components" / "StitcherSlotWaveform.tsx"


def test_session_cache_module_exists() -> None:
    src = CACHE.read_text(encoding="utf-8")
    assert "STITCH_SLOT_SESSION_CACHE_V1" in src
    assert "STITCH_PREVIEW_LS_HYDRATE_V1" in src
    assert "hydrateMuxFromLocalStorage" in src
    assert "isMuxSessionFresh" in src
    assert "isWaveformSessionFresh" in src
    assert "reconcileStitchSlotSession" in src


def test_stitcher_hydrates_mux_from_server_job_on_load() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "hydrateAllSlotMediaFromJob" in src
    load = src.split("if (!cancelled && Object.keys(canonicalSlots).length > 0)", 1)[1]
    assert "hydrateAllSlotMediaFromJob" in load.split("Bootstrap:", 1)[0]
    assert "pendingMuxBuildsRef" in src
    assert "void buildSlotPreview(sd.key, { quiet: true })" not in src


def test_stitcher_uses_session_cache_on_phase_switch() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "stitchSlotSessionCache" in src
    assert "isMuxSessionFresh" in src
    assert "commitMuxSession" in src
    assert "clearStitchSlotSessionEvent" in src
    click = src.split("const onMultiPhaseSegmentClick = ", 1)[1].split("\n  const viewerMuxAudioSig", 1)[0]
    assert "isMuxSessionFresh" in click
    assert "STITCH_SLOT_SESSION_CACHE_V1" in src


def test_build_slot_preview_checks_session_before_server() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    block = src.split("const buildSlotPreview = async", 1)[1].split("const seekComposerTo", 1)[0]
    assert "isMuxSessionFresh" in block
    assert "commitMuxSession" in block


def test_waveform_uses_session_cache() -> None:
    src = WAVEFORM.read_text(encoding="utf-8")
    assert "isWaveformSessionFresh" in src
    assert "commitWaveformSession" in src


def test_display_only_waveform_peaks_stable_on_sfx_edit() -> None:
    """STITCH_WAVEFORM_PEAKS_STABLE_ON_SFX_V1 — SFX cue edits must not re-trigger speech peak extract."""
    src = WAVEFORM.read_text(encoding="utf-8")
    assert "STITCH_WAVEFORM_PEAKS_STABLE_ON_SFX_V1" in src
    effect = src.split("useEffect(() => {", 1)[1].split("const timelineCues = useMemo", 1)[0]
    assert "displayOnly" in effect
    assert "displayOnly\n    ? [" in effect or "displayOnly\n    ?[" in effect.replace(" ", "")
    assert "sfx_cues: cues" not in effect.split("displayOnly\n        ? { video_path: videoPath }", 1)[0]


def test_save_job_slots_optimistic_before_refresh() -> None:
    src = STITCHER.read_text(encoding="utf-8")
    assert "STITCH_SAVE_OPTIMISTIC_SLOTS_V1" in src
    save = src.split("const saveJobSlots = async", 1)[1].split("const saveJobTransitions", 1)[0]
    before_refresh = save.split("void (async () => {", 1)[0]
    assert "setJob(" in before_refresh
    assert "mergedSlots" in before_refresh
