"""STITCH_FOUR_FILES_LEGACY_PURGE_V1 — never re-enter se_slot / mux artifact tiers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from server_handlers.stitch_media_artifacts import (
    attach_stitch_slot_derived_media_urls,
    stitch_slot_needs_playback_artifact_bake,
)
from server_handlers.stitch_slot_edit_dispatch import slot_needs_ambient_rebuild
from server_handlers.stitch_slot_playback import (
    STITCH_FOUR_FILES_LEGACY_PURGE_V1,
    STITCH_FOUR_FILES_V1,
    reconcile_four_files_slot_authority,
    slot_skips_legacy_playback_artifact_tiers,
)


def test_reconcile_four_files_slot_authority_clears_legacy() -> None:
    slot = {
        "video_path": "Production/Event_4/assembled/intro_playback_x.mp4",
        "playback_recipe_version": STITCH_FOUR_FILES_V1,
        "ambient_mix_hash": "deadbeef1234",
        "mux_preview_hash": "cafebabe5678",
        "_ambient_mix_url": "/api/stitch_editor/slot_mix_file/deadbeef1234",
    }
    assert reconcile_four_files_slot_authority(slot) is True
    assert "ambient_mix_hash" not in slot
    assert "mux_preview_hash" not in slot
    assert "_ambient_mix_url" not in slot


def test_slot_skips_legacy_playback_artifact_tiers() -> None:
    assert slot_skips_legacy_playback_artifact_tiers(
        {"playback_recipe_version": STITCH_FOUR_FILES_V1},
    )
    assert not slot_skips_legacy_playback_artifact_tiers({"playback_recipe_version": "legacy"})


def test_slot_needs_ambient_rebuild_false_for_four_files() -> None:
    h = MagicMock()
    nxt = {
        "video_path": "x.mp4",
        "ambient_bed": "Intro video ambient bed",
        "playback_recipe_version": STITCH_FOUR_FILES_V1,
    }
    assert slot_needs_ambient_rebuild(h, {}, nxt) is False


def test_stitch_slot_needs_playback_artifact_bake_false_for_four_files() -> None:
    h = MagicMock()
    slot = {
        "video_path": "x.mp4",
        "ambient_bed": "Intro video ambient bed",
        "playback_recipe_version": STITCH_FOUR_FILES_V1,
    }
    assert stitch_slot_needs_playback_artifact_bake(h, slot) is False


def test_attach_derived_urls_skips_legacy_mix_for_four_files() -> None:
    h = MagicMock()
    h._stitch_media_public_url = lambda _h, path: path
    slot = {
        "video_path": "x.mp4",
        "playback_recipe_version": STITCH_FOUR_FILES_V1,
        "ambient_mix_hash": "abc123",
        "waveform_peaks_hash": "peaks1",
    }
    attach_stitch_slot_derived_media_urls(h, slot)
    assert "ambient_mix_hash" not in slot
    assert "_ambient_mix_url" not in slot
    assert "_mux_preview_url" not in slot
    assert slot.get("_waveform_peaks_url")


def test_rebuild_ambient_mixes_skips_four_files() -> None:
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "stitch_editor.py"
    block = src.read_text(encoding="utf-8")
    rebuild = block.split("def rebuild_stitch_ambient_mixes_for_job", 1)[1].split(
        "\ndef handle_stitch_save_job", 1,
    )[0]
    assert STITCH_FOUR_FILES_LEGACY_PURGE_V1 in rebuild
    assert "slot_skips_legacy_playback_artifact_tiers(slot)" in rebuild


def test_load_job_purges_four_files_legacy_fields() -> None:
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "stitch_editor.py"
    block = src.read_text(encoding="utf-8").split("def handle_stitch_load_job", 1)[1].split(
        "\ndef handle_stitch_save_job", 1,
    )[0]
    assert "reconcile_four_files_slot_authority(slot)" in block
    assert "four_files_purged_on_load" in block


def test_plan_playback_ladder_warm_skips_four_files() -> None:
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "stitch_artifact_build.py"
    block = src.read_text(encoding="utf-8").split("def plan_playback_ladder_warm", 1)[1].split(
        "\ndef submit_stitch_ambient_rebuild", 1,
    )[0]
    assert "slot_skips_legacy_playback_artifact_tiers(slot)" in block
