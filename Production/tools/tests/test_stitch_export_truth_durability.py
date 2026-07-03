"""FF-037 STITCH_EXPORT_TRUTH — intro concat join fade + waveform speech + playback remux."""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def test_join_fade_constants_export_truth() -> None:
    from beat_generator import (  # noqa: PLC0415
        KLING_EXPORT_AUDIO_JOIN_FADE_MS,
        KLING_EXPORT_STILL_INSERT_EXIT_FADE_MS,
        STITCH_EXPORT_TRUTH_JOIN_FADE_V1,
    )

    assert STITCH_EXPORT_TRUTH_JOIN_FADE_V1
    assert KLING_EXPORT_AUDIO_JOIN_FADE_MS >= 80
    assert KLING_EXPORT_STILL_INSERT_EXIT_FADE_MS >= KLING_EXPORT_AUDIO_JOIN_FADE_MS


def test_still_insert_exit_fade_in_concat_loop() -> None:
    src = (TOOLS / "beat_generator.py").read_text(encoding="utf-8")
    block = src.split("def _ffmpeg_concat_kling_clips_reencode", 1)[1].split(
        "\ndef _TOOLS_DIR", 1,
    )[0]
    assert "_still_insert_exit_at_join" in block
    assert "KLING_EXPORT_STILL_INSERT_EXIT_FADE_MS" in block
    assert "fade_out_ms=exit_ms" in block


def test_playback_bake_timestamp_authority_final_heal() -> None:
    src = (TOOLS / "server_handlers" / "stitch_slot_playback.py").read_text(encoding="utf-8")
    bake = src.split("def bake_slot_playback_mp4", 1)[1].split("\ndef _assembled_playback_dest", 1)[0]
    assert "STITCH_EXPORT_TRUTH_PLAYBACK_REMUX_V1" in src
    assert "STITCH_PLAYBACK_LIPSYNC_TIMESTAMP_AUTHORITY_V1" in src
    assert "ensure_mp4_playback_timestamps(dest)" in bake
    assert "mp4_operator_playback_timestamps_safe(dest)" in bake
    assert "_remux_mp4_copy_safe" not in bake


def test_waveform_speech_path_resolver() -> None:
    from server_handlers.stitch_slot_playback import (  # noqa: PLC0415
        STITCH_FOUR_FILES_V1,
        resolve_four_files_waveform_video_path,
    )

    slot = {
        "playback_recipe_version": STITCH_FOUR_FILES_V1,
        "video_path": "Production/Event_4/assembled/intro_playback_x.mp4",
        "dry_export_path": "Production/Event_4/assembled/intro_kling_o3_x.mp4",
    }
    assert resolve_four_files_waveform_video_path(slot).endswith("intro_kling_o3_x.mp4")


def test_audio_extract_uses_dry_for_four_files_peaks() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    block = src.split("def handle_stitch_audio_extract", 1)[1].split("\ndef ", 1)[0]
    assert "STITCH_EXPORT_TRUTH_WAVEFORM_SPEECH_V1" in block
    assert "resolve_four_files_waveform_video_path" in block


def test_mix_slot_audio_faststart() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    block = src.split("def _stitch_mix_slot_audio", 1)[1].split("\n    def _stitch_build_pipeline", 1)[0]
    assert '"+faststart"' in block or "'+faststart'" in block


def test_client_waveform_path_helper() -> None:
    hydrate = (TOOLS / "storyboard-v2" / "src" / "utils" / "stitchJobMediaHydrate.ts").read_text(
        encoding="utf-8",
    )
    assert "resolveSlotWaveformVideoPath" in hydrate
    assert "STITCH_EXPORT_TRUTH_WAVEFORM_SPEECH_V1" in hydrate
    tab = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    assert "resolveSlotWaveformVideoPath" in tab
