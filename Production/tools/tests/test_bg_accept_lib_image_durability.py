"""Beat Gen library drop durability — short lock + update_beat_locked."""
from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
BG = TOOLS / "server_handlers" / "background.py"


def test_accept_lib_image_uses_update_beat_locked_not_whole_file_write() -> None:
    src = BG.read_text(encoding="utf-8")
    block = src.split("def handle_bg_accept_lib_image", 1)[1].split("\ndef handle_bg_groups", 1)[0]
    assert "update_beat_locked" in block
    assert "_migrate_sidecar" not in block
    assert "write_sidecar(sidecar)" not in block


def test_accept_lib_image_blocks_during_o3_job_and_lock_timeout() -> None:
    src = BG.read_text(encoding="utf-8")
    block = src.split("def handle_bg_accept_lib_image", 1)[1].split("\ndef handle_bg_groups", 1)[0]
    assert "_beat_o3_operator_lock_active" in block
    assert "INTENT_JOB_ACTIVE" in block
    assert "SIDECAR_IO_TRANSIENT" in block


def test_pose_copy_uses_copy_file_durable() -> None:
    reg = (TOOLS / "kling_character_registry.py").read_text(encoding="utf-8")
    assert "copy_file_durable" in reg
    assert "shutil.copy2(source, dest)" not in reg
