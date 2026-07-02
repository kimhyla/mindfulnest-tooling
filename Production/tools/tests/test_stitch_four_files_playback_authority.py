"""STITCH_FOUR_FILES_V1 — playback authority tests."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from server_handlers.stitch_slot_playback import (
    STITCH_FOUR_FILES_V1,
    bake_slot_playback_mp4,
    clear_legacy_playback_artifact_fields,
    playback_recipe_is_four_files,
    slot_has_playback_mix_layers,
)


def _make_dry_mp4(path: Path, duration_s: float = 1.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={duration_s:.3f}",
            "-f", "lavfi", "-i", f"sine=f=440:duration={duration_s:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
        timeout=60,
    )


def test_playback_recipe_is_four_files() -> None:
    assert playback_recipe_is_four_files({"playback_recipe_version": STITCH_FOUR_FILES_V1})
    assert not playback_recipe_is_four_files({"playback_recipe_version": "legacy"})
    assert not playback_recipe_is_four_files(None)


def test_clear_legacy_playback_artifact_fields() -> None:
    slot = {
        "video_path": "x.mp4",
        "ambient_mix_hash": "abc",
        "mux_preview_hash": "def",
        "mix_sig": "ghi",
    }
    clear_legacy_playback_artifact_fields(slot)
    assert "ambient_mix_hash" not in slot
    assert "mux_preview_hash" not in slot
    assert slot["video_path"] == "x.mp4"


def test_slot_has_playback_mix_layers_speech_only() -> None:
    assert not slot_has_playback_mix_layers({})


def test_bake_slot_playback_mp4_copy_when_no_mix_layers(tmp_path: Path) -> None:
    dry = tmp_path / "dry.mp4"
    dest = tmp_path / "playback.mp4"
    _make_dry_mp4(dry)
    h = MagicMock()
    h._ffprobe_duration_ms.return_value = 1000
    dur_s = bake_slot_playback_mp4(h, {}, dry_video_path=dry, dest=dest)
    assert dest.is_file()
    assert dur_s == pytest.approx(1.0, abs=0.05)


def test_stitch_upsert_event_slot_uses_dry_authority_branch() -> None:
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "stitch_editor.py"
    text = src.read_text(encoding="utf-8")
    assert "STITCH_DRY_AUTHORITY_CLIENT_MIX_V1" in text
    assert "persist_dry_authority_slot_export" in text


def test_module_bake_passthrough_branch() -> None:
    src = Path(__file__).resolve().parents[1] / "production_server.py"
    text = src.read_text(encoding="utf-8")
    assert "playback_recipe_is_four_files" in text
