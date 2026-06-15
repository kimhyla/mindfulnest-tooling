"""Regression — Event library sources/ bytes must never be overwritten by heal/sync.

2026-06-14: heal_locked_char_ref_to_element used shutil.copy2 onto library/sources/
tiles when @Image1 hash mismatched Element poses — neutral uploads became map poses.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import beat_generator as bg

TOOLS = Path(__file__).resolve().parent.parent
BEAT_GEN = TOOLS / "beat_generator.py"


def _heal_function_source() -> str:
    tree = ast.parse(BEAT_GEN.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "heal_locked_char_ref_to_element":
            return ast.get_source_segment(
                BEAT_GEN.read_text(encoding="utf-8"), node,
            ) or ""
    raise AssertionError("heal_locked_char_ref_to_element not found")


def test_heal_locked_char_ref_never_uses_shutil_copy2():
    src = _heal_function_source()
    assert "shutil.copy2" not in src, (
        "heal_locked_char_ref_to_element must not copy Element bytes onto library paths"
    )
    assert "shutil.copy" not in src


def test_apply_user_beat_ref_update_skips_heal_mismatch_on_reference_image():
    text = BEAT_GEN.read_text(encoding="utf-8")
    assert "sync_element_char_ref_status(beat, heal_mismatch=False)" in text
    assert re.search(
        r'if field == "reference_image":\s*\n\s*# User explicitly chose.*?'
        r"sync_element_char_ref_status\(beat, heal_mismatch=False\)",
        text,
        re.DOTALL,
    ), "reference_image user drops must validate gate without redirect/heal overwrite"


def test_require_element_char_ref_for_o3_does_not_heal_before_gate():
    text = BEAT_GEN.read_text(encoding="utf-8")
    assert re.search(
        r"def require_element_char_ref_for_o3\(beat: dict\).*?"
        r"sync_element_char_ref_status\(beat, heal_mismatch=False\)",
        text,
        re.DOTALL,
    ), "O3 submit must not silently redirect char ref before API work"


def test_heal_locked_char_ref_never_redirects_existing_library_upload(tmp_path, monkeypatch):
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "neutral_upload.png"
    canonical.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    canonical.write_bytes(b"element-pose-with-map")
    library.write_bytes(b"user-neutral-upload")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.file_sha256",
        lambda p: "hash_user"
        if Path(p).read_bytes() == b"user-neutral-upload"
        else "hash_element",
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
    }
    assert bg.heal_locked_char_ref_to_element(beat) is False
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert library.read_bytes() == b"user-neutral-upload"


def test_apply_user_beat_ref_then_update_sync_keeps_library_path(tmp_path, monkeypatch):
    """Simulates bg_update_beat: apply_user_beat_ref_update + sync without heal redirect."""
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "neutral_upload.png"
    canonical.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    canonical.write_bytes(b"element-pose-with-map")
    library.write_bytes(b"user-neutral-upload")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.file_sha256",
        lambda p: "hash_user"
        if Path(p).read_bytes() == b"user-neutral-upload"
        else "hash_element",
    )

    beat: dict = {"speaker": "Lorelai"}
    bg.apply_user_beat_ref_update(
        beat,
        "reference_image",
        {"abs_path": str(library), "key": "neutral_upload"},
    )
    bg.sync_element_char_ref_status(beat, heal_mismatch=False)
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert library.read_bytes() == b"user-neutral-upload"
    assert beat["element_char_ref_ok"] is False


def test_user_drop_preserves_library_bytes_on_mismatch(tmp_path, monkeypatch):
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "neutral_upload.png"
    canonical.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    canonical.write_bytes(b"element-pose-with-map")
    library.write_bytes(b"user-neutral-upload")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.file_sha256",
        lambda p: "hash_user"
        if Path(p).read_bytes() == b"user-neutral-upload"
        else "hash_element",
    )

    beat: dict = {"speaker": "Lorelai"}
    bg.apply_user_beat_ref_update(
        beat,
        "reference_image",
        {"abs_path": str(library), "key": "neutral_upload"},
    )
    assert library.read_bytes() == b"user-neutral-upload"
    assert beat["element_char_ref_ok"] is False
