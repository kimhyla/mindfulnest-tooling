"""FF-042 STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 durability gates."""

from __future__ import annotations

import tempfile
import unittest.mock as mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_dry_authority_export_upsert_source() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def stitch_upsert_event_slot", 1)[1].split("\ndef ", 1)[0]
    assert "bake_and_persist_slot_playback_mp4" in block
    assert "STITCH_FOUR_FILES_V1" in block
    assert "persist_dry_authority_slot_export" not in block


def test_dry_authority_playback_module_not_passthrough() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    block = src.split("def _stitch_build_pipeline", 1)[1].split("\n    def ", 1)[0]
    assert "playback_recipe_is_four_files" in block
    assert "playback_recipe_is_dry_authority_client_mix" not in block or (
        "playback_recipe_is_four_files(slot)" in block
    )


def test_client_mix_engine_marker() -> None:
    src = (TOOLS / "storyboard-v2/src/audio/StitchSlotAudioMixEngine.ts").read_text(encoding="utf-8")
    assert "STITCH_DRY_AUTHORITY_CLIENT_MIX_V1" in src
    assert "createMediaElementSource" in src
    assert "videoSpeechChains" in src
    assert "ctx.close()" not in src
    assert "stopAllStitchClientMix" in src
    assert "emergencyStop" in src
    tab = (TOOLS / "storyboard-v2/src/components/StitcherTab.tsx").read_text(encoding="utf-8")
    assert "StitchSlotAmbientBedAudio" in tab
    assert "stitchSlotUsesDryAuthorityClientMix(slotData)" in tab
    bus = (TOOLS / "storyboard-v2/src/utils/waveformPlaybackBus.ts").read_text(encoding="utf-8")
    assert "stopAllStitchClientMix" in bus


def test_stitcher_tab_client_mix_hook() -> None:
    src = (TOOLS / "storyboard-v2/src/components/StitcherTab.tsx").read_text(encoding="utf-8")
    assert "useStitchSlotClientMix" in src
    assert "stitchSlotUsesDryAuthorityClientMix" in src


def test_slot_ambient_loop_endpoint() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/stitch_editor/slot_ambient_loop" in src
    assert "build_stitch_slot_ambient_loop_response" in src
    editor = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    block = editor.split("def build_stitch_slot_ambient_loop_response", 1)[1].split("\ndef ", 1)[0]
    assert "stitch_state_store_for_job" in block
    assert "from server_handlers.stitch_scope import stitch_state_store_for_job" not in block


def test_migrate_four_files_on_load_job() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_load_job", 1)[1].split("\ndef ", 1)[0]
    assert "migrate_four_files_slot_to_dry_authority" not in block
    assert "migrate_stale_split_authority_slot_to_dry_authority" in block


def test_migrate_stale_split_authority_hydrated_resolution() -> None:
    """Disk-hydrated resolution with ambient_mix artifacts must clear split tiers."""
    from server_handlers.stitch_slot_playback import (
        STITCH_FOUR_FILES_PLAYBACK_RECIPE,
        migrate_stale_split_authority_slot_to_dry_authority,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dry_rel = "Production/Event_4/assembled/resolution_kling_o3_20260701T153750Z.mp4"
        dry_abs = Path(tmp) / dry_rel
        dry_abs.parent.mkdir(parents=True, exist_ok=True)
        dry_abs.write_bytes(b"\x00")

        class _H:
            def _stitch_resolve_path(self, raw: str) -> str:
                return str(Path(tmp) / raw)

            def _ffprobe_duration_ms(self, _path) -> int:
                return 47_397

        slot = {
            "video_path": dry_rel,
            "source": "STITCH_SLOT_ASSEMBLED_DISK_HYDRATE_V1",
            "ambient_mix_hash": "f524e2f2ffc1",
            "ambient_mix_video_path": dry_rel,
            "mux_preview_hash": "f46bea294a68",
            "mix_sig": "f24f3cc7424a5b42",
        }
        with mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ):
            changed = migrate_stale_split_authority_slot_to_dry_authority(_H(), slot, "resolution")

        assert changed is True
        assert slot["video_path"] == dry_rel
        assert slot["dry_export_path"] == dry_rel
        assert slot["playback_recipe_version"] == STITCH_FOUR_FILES_PLAYBACK_RECIPE
        assert "ambient_mix_hash" not in slot
        assert "mux_preview_hash" not in slot


def test_bake_slot_playback_mp4_normalizes_dry_concat_once() -> None:
    src = (TOOLS / "server_handlers" / "stitch_slot_playback.py").read_text(encoding="utf-8")
    bake = src.split("def bake_slot_playback_mp4", 1)[1].split("\ndef _assembled_playback_dest", 1)[0]
    assert "_prepare_dry_concat_for_slot_bake" in bake
    assert "apply_speech_loudnorm_to_mp4" in src.split("def _prepare_dry_concat_for_slot_bake", 1)[1].split("\ndef bake_slot_playback_mp4", 1)[0]


def test_playback_bake_timestamp_authority_final_heal() -> None:
    src = (TOOLS / "server_handlers" / "stitch_slot_playback.py").read_text(encoding="utf-8")
    bake = src.split("def bake_slot_playback_mp4", 1)[1].split("\ndef _assembled_playback_dest", 1)[0]
    assert "mp4_operator_playback_timestamps_safe(dest)" in bake
    assert "_remux_mp4_copy_safe" not in bake


def test_export_rejects_server_restart_gate() -> None:
    src = (TOOLS / "server_handlers" / "kling_o3.py").read_text(encoding="utf-8")
    block = src.split("def handle_bg_export_to_stitcher", 1)[1].split("\ndef handle_bg_poll", 1)[0]
    assert "server_mutation_gate_reason" in block
    assert "SERVER_NOT_READY" in block


def test_migrate_four_files_resolve_path_returns_str() -> None:
    """Regression: _stitch_resolve_path returns str; migration must Path-wrap before is_file."""
    from server_handlers.stitch_slot_playback import (
        STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE,
        STITCH_FOUR_FILES_PLAYBACK_RECIPE,
        migrate_four_files_slot_to_dry_authority,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dry_rel = "Production/Event_4/assembled/intro_kling_o3_test.mp4"
        dry_abs = Path(tmp) / dry_rel
        dry_abs.parent.mkdir(parents=True, exist_ok=True)
        dry_abs.write_bytes(b"\x00")

        class _H:
            def _stitch_resolve_path(self, raw: str) -> str:
                return str(Path(tmp) / raw)

            def _stitch_project_root(self) -> Path:
                return Path(tmp)

            def _ffprobe_duration_ms(self, _path) -> int:
                return 60_000

        slot = {
            "video_path": "Production/Event_4/assembled/intro_playback_20260702T143138Z.mp4",
            "dry_export_path": dry_rel,
            "playback_recipe_version": STITCH_FOUR_FILES_PLAYBACK_RECIPE,
        }
        h = _H()
        with mock.patch(
            "server_handlers.stitch_editor.sync_stitch_slot_video_dur_ms",
            return_value=False,
        ):
            changed = migrate_four_files_slot_to_dry_authority(h, slot, "intro")

        assert changed is True
        assert slot["video_path"] == dry_rel
        assert slot["playback_recipe_version"] == STITCH_DRY_AUTHORITY_PLAYBACK_RECIPE
        assert "dry_export_path" not in slot
