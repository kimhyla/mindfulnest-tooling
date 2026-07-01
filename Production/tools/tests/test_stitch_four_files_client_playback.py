#!/usr/bin/env python3
"""FF-036 — client four-files playback authority (static contract)."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
SB = TOOLS / "storyboard-v2" / "src"


def test_resolve_slot_playback_short_circuits_four_files() -> None:
    src = (SB / "utils" / "stitchJobMediaHydrate.ts").read_text(encoding="utf-8")
    fn_idx = src.index("export function resolveSlotPlaybackPreviewUrl")
    block = src[fn_idx:fn_idx + 2800]
    assert "reconcileFourFilesSlotArtifacts(slot)" in block
    assert "stitchSlotUsesFourFilesPlayback(reconciled)" in block
    four_idx = block.index("if (stitchSlotUsesFourFilesPlayback(reconciled))")
    from_state = block.index("const fromState = previewUrls[slotKey]")
    assert four_idx < from_state, "four-files gate must precede previewUrls cache"


def test_build_slot_preview_skips_remux_for_four_files() -> None:
    src = (SB / "components" / "StitcherTab.tsx").read_text(encoding="utf-8")
    fn = src.split("const buildSlotPreview = async", 1)[1].split("\n  const seekComposerTo", 1)[0]
    assert "stitchSlotUsesFourFilesPlayback(slotData)" in fn
    assert "singleFlightMuxPreview" not in fn.split("stitchSlotUsesFourFilesPlayback", 1)[0]


def test_hydrate_purges_and_binds_four_files_playback() -> None:
    src = (SB / "utils" / "stitchJobMediaHydrate.ts").read_text(encoding="utf-8")
    assert "reconcileFourFilesSlotArtifacts(rawSlot)" in src
    assert "if (stitchSlotUsesFourFilesPlayback(slot))" in src
    assert "purgeStitchSlotPlaybackCache(sessionKey, slotKey)" in src


def test_local_storage_tracks_playback_recipe_version() -> None:
    src = (SB / "utils" / "stitchSlotSessionCache.ts").read_text(encoding="utf-8")
    assert "playback_recipe_version?: string" in src
    assert "playback_recipe_version" in src.split("readCachedStitcherPreviewLs", 1)[1].split("writeCachedStitcherPreviewLs", 1)[0]


def test_server_preview_passthrough_four_files() -> None:
    editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    block = editor.split("def handle_stitch_preview", 1)[1].split("\ndef ", 1)[0]
    assert "playback_recipe_is_four_files(slot)" in block
    assert "four_files_passthrough" in block
