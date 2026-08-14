"""STITCH_FOUR_FILES_V1 — playback authority tests."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    with patch(
        "server_handlers.stitch_slot_playback._prepare_dry_concat_for_slot_bake",
        return_value=dry,
    ):
        dur_s = bake_slot_playback_mp4(h, {}, dry_video_path=dry, dest=dest)
    assert dest.is_file()
    assert dur_s == pytest.approx(1.0, abs=0.05)


def test_bake_playback_never_shutil_copy2_onto_dest() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "server_handlers"
        / "stitch_slot_playback.py"
    ).read_text(encoding="utf-8")
    block = text.split("def bake_slot_playback_mp4", 1)[1].split(
        "\ndef _assembled_playback_dest", 1,
    )[0]
    assert "shutil.copy2" not in block
    assert "copy_file_durable" in text
    assert "STITCH_PLAYBACK_BAKE_LOCAL_COMMIT_V1" in text


def test_assembled_media_commits_never_use_shutil_copy2() -> None:
    """Send-to-Stitcher + canonical pin: Dropbox assembled writes must retry errno 11."""
    tools = Path(__file__).resolve().parents[1]
    files = (
        tools / "server_handlers" / "stitch_slot_playback.py",
        tools / "stitch_bake_finalize.py",
        tools / "pin_event_canonical_module.py",
        tools / "credentials_lib" / "ffmpeg_stitch.py",
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        if path.name == "ffmpeg_stitch.py":
            block = text.split("def remux_mp4_video_timeline_authority", 1)[1].split(
                "\ndef ", 1,
            )[0]
            assert "shutil.copy2" not in block, path.name
            assert "copy_file_durable" in block, path.name
            continue
        assert "shutil.copy2(" not in text, path.name
        assert "copy_file_durable" in text, path.name


def test_bake_scratch_dir_leaves_dropbox_cache() -> None:
    from server_handlers.stitch_slot_playback import _bake_scratch_dir

    h = MagicMock()
    h._stitch_cache_dir.return_value = Path(
        "/Users/me/Library/CloudStorage/Dropbox/Production/stitch_editor_cache",
    )
    d = _bake_scratch_dir(h)
    assert "CloudStorage" not in str(d)
    assert "mn_ffmpeg_scratch" in str(d)


def test_bake_slot_playback_commits_cloud_dest(tmp_path: Path) -> None:
    """Event_6 job 58c02a2d: concat ok, shutil.copy2 onto Dropbox assembled → EDEADLK."""
    dry = tmp_path / "dry.mp4"
    dest = tmp_path / "CloudStorage" / "Dropbox" / "assembled" / "resolution_playback.mp4"
    dest.parent.mkdir(parents=True)
    _make_dry_mp4(dry)
    h = MagicMock()
    h._ffprobe_duration_ms.return_value = 1000
    with patch(
        "server_handlers.stitch_slot_playback._prepare_dry_concat_for_slot_bake",
        return_value=dry,
    ):
        bake_slot_playback_mp4(h, {}, dry_video_path=dry, dest=dest)
    assert dest.is_file()
    assert dest.stat().st_size > 1000


def test_stitch_upsert_event_slot_uses_dry_authority_branch() -> None:
    src = Path(__file__).resolve().parents[1] / "server_handlers" / "stitch_editor.py"
    text = src.read_text(encoding="utf-8")
    block = text.split("def stitch_upsert_event_slot", 1)[1].split("\ndef ", 1)[0]
    assert "STITCH_DRY_AUTHORITY_CLIENT_MIX_V1" in block
    assert "persist_dry_authority_slot_export" in block
    assert "bake_and_persist_slot_playback_mp4" not in block


def test_module_bake_passthrough_branch() -> None:
    src = Path(__file__).resolve().parents[1] / "production_server.py"
    text = src.read_text(encoding="utf-8")
    assert "playback_recipe_is_four_files" in text
