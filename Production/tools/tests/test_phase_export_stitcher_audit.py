"""PHASE_EXPORT_STITCHER_AUDIT_V1 — Phase A/B Send to Stitcher must be auditable + scope-safe."""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_phase_export_allows_missing_video_role() -> None:
    src = (TOOLS / "server_handlers" / "phases.py").read_text(encoding="utf-8")
    block = src.split("def handle_phase_export_stitcher", 1)[1].split(
        "\ndef ensure_phase_b_stitch_slot_for_bake", 1,
    )[0]
    assert "allow_missing_video_role=True" in block
    assert "_phase_export_stitcher_audit" in block
    assert "SLOT_VERIFY_FAILED" in block


def test_effective_scope_video_role_sanitizes_phase_tabs() -> None:
    scope = (TOOLS / "storyboard-v2" / "src" / "state" / "scope.ts").read_text(encoding="utf-8")
    assert "MUTATION_SCOPE_VIDEO_ROLES" in scope
    assert "phase_a|phase_b" in scope or "phase_a" in scope
    assert "return 'intro'" in scope.split("effectiveScopeVideoRole", 1)[1][:400]


def test_composer_slot_urls_use_dry_export_for_four_files() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    block = src.split("const composerSlotUrls = useMemo", 1)[1].split("}, [", 1)[0]
    assert "resolveSlotWaveformVideoPath" in block
    assert "resolveDrySlotSourceVideoUrl(slotData.video_path)" not in block


def test_stitch_slot_lineage_tracks_dry_export_path() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "utils" / "stitchSlotVideoLineage.ts").read_text(
        encoding="utf-8",
    )
    assert "slotExportLineagePath" in src
    assert "dry_export_path" in src


def test_viewer_video_path_invalidation_is_per_slot() -> None:
    """Phase switch must not compare video_path across slots (STITCH_SLOT_SESSION_CACHE_V1)."""
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    assert "lastViewerVideoPathBySlotRef" in src
    assert "prevPath = lastViewerVideoPathBySlotRef.current[sessionSlot]" in src
    effect_block = src.split("lastViewerVideoPathBySlotRef.current[sessionSlot] = path", 1)[0]
    assert "if (prevPath)" in effect_block
    assert "lastViewerVideoPathRef" not in src
