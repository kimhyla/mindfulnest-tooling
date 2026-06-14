"""User-dropped Beat Gen refs must survive sidecar migration / auto-align."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def test_apply_user_beat_ref_update_locks_on_drop_and_unlocks_on_clear(tmp_path: Path):
    library = tmp_path / "ChatGPT_Image_Jun_14.png"
    library.write_bytes(b"library")
    beat: dict = {"speaker": "Lorelai"}

    bg.apply_user_beat_ref_update(
        beat,
        "reference_image",
        {"abs_path": str(library), "key": library.stem},
    )
    assert beat["reference_image"]["abs_path"] == str(library)
    assert beat["reference_image_locked"] is True

    bg.apply_user_beat_ref_update(beat, "reference_image", None)
    assert beat["reference_image"] is None
    assert beat["reference_image_locked"] is False


def test_apply_user_beat_ref_update_bg_ref_lock(tmp_path: Path):
    bg_still = tmp_path / "custom_bg.webp"
    bg_still.write_bytes(b"bg")
    beat: dict = {}

    bg.apply_user_beat_ref_update(
        beat,
        "bg_ref_image",
        {"abs_path": str(bg_still), "key": bg_still.stem},
    )
    assert beat["bg_ref_image_locked"] is True

    bg.apply_user_beat_ref_update(beat, "bg_ref_image", None)
    assert beat["bg_ref_image"] is None
    assert beat["bg_ref_image_locked"] is False


def test_migrate_sidecar_preserves_locked_library_char_ref(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical.png"
    library = tmp_path / "ChatGPT_Image_Jun_14.png"
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
    )

    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_event2_beat_03",
                            "speaker": "Lorelai",
                            "reference_image": {"abs_path": str(library)},
                            "reference_image_locked": True,
                            "pipeline": "kling_o3_omni",
                        }],
                    },
                },
            },
        },
    }
    bg._migrate_sidecar(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["reference_image"]["abs_path"] == str(library)


def test_migrate_sidecar_realigns_unlocked_char_ref(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical.png"
    library = tmp_path / "library_still.png"
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
    )

    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_event2_beat_03",
                            "speaker": "Lorelai",
                            "reference_image": {"abs_path": str(library)},
                            "reference_image_locked": False,
                            "pipeline": "kling_o3_omni",
                        }],
                    },
                },
            },
        },
    }
    bg._migrate_sidecar(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["reference_image"]["abs_path"] == str(canonical.resolve())


def test_reference_image_locked_skips_auto_heal(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical.png"
    library = tmp_path / "library_still.png"
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
    }
    assert bg.align_beat_reference_to_element(beat) is False
    assert beat["reference_image"]["abs_path"] == str(library)


def test_apply_kling_o3_defaults_respects_bg_ref_locked(tmp_path: Path, monkeypatch):
    default_bg = tmp_path / "segment_default.png"
    custom_bg = tmp_path / "custom_bg.png"
    default_bg.write_bytes(b"default")
    custom_bg.write_bytes(b"custom")

    monkeypatch.setattr(
        bg,
        "resolve_segment_bg_path",
        lambda _e, _p: str(default_bg),
    )
    monkeypatch.setattr(
        bg,
        "align_beat_reference_to_element",
        lambda _b: False,
    )
    monkeypatch.setattr(
        bg,
        "build_kling_o3_prompt",
        lambda _b: "prompt",
    )

    beat = {
        "speaker": "",
        "bg_ref_image": None,
        "bg_ref_image_locked": True,
    }
    bg.apply_kling_o3_defaults_to_beat(beat, "2", "pre")
    assert beat.get("bg_ref_image") is None


def test_element_char_ref_gate_rejects_locked_library_still(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical_neutral.png"
    library = tmp_path / "ChatGPT_Image_Jun_14.png"
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )

    def fake_hash(path):
        p = str(path)
        if "ChatGPT" in p or "library" in p.lower():
            return "hash_library"
        return "hash_canonical"

    monkeypatch.setattr("tools.kling_character_registry.file_sha256", fake_hash)

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
    }
    ok, detail = bg.element_char_ref_gate(beat)
    assert ok is False
    assert "does not match Element images" in detail


def test_element_char_ref_gate_accepts_element_pose(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical_neutral.png"
    canonical.write_bytes(b"canonical")

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
        lambda _p: "hash_canonical",
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(canonical)},
        "reference_image_locked": True,
    }
    ok, detail = bg.element_char_ref_gate(beat)
    assert ok is True
    assert detail == ""


def test_sync_element_char_ref_status_persists_mismatch_on_beat(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical_neutral.png"
    library = tmp_path / "ChatGPT_Image_Jun_14.png"
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

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
        lambda p: "hash_library"
        if "ChatGPT" in str(p) and Path(p).read_bytes() == b"library"
        else "hash_canonical",
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
    }
    assert bg.sync_element_char_ref_status(beat) is False
    assert beat["element_char_ref_ok"] is False
    assert "does not match Element images" in beat["element_char_ref_error"]


def test_migrate_sidecar_heals_locked_library_ref_to_element_pose(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "ChatGPT_Image_Jun_14.png"
    canonical.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.file_sha256",
        lambda p: "hash_library"
        if "ChatGPT" in str(p) and Path(p).read_bytes() == b"library"
        else "hash_canonical",
    )

    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_event2_beat_03",
                            "speaker": "Lorelai",
                            "reference_image": {"abs_path": str(library)},
                            "reference_image_locked": True,
                            "pipeline": "kling_o3_omni",
                        }],
                    },
                },
            },
        },
    }
    bg._migrate_sidecar(sidecar)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert library.read_bytes() == b"canonical"
    assert beat["element_char_ref_ok"] is True


def test_sync_clears_stale_element_char_ref_error_when_hashes_match(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical_neutral.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "ChatGPT_Image.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"canonical")

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
        lambda _p: "hash_canonical",
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
        "element_char_ref_ok": False,
        "element_char_ref_error": "stale mismatch from pre-sync library upload",
    }
    assert bg.sync_element_char_ref_status(beat) is True
    assert beat["element_char_ref_ok"] is True
    assert "element_char_ref_error" not in beat


def test_apply_user_beat_ref_heals_library_drop_to_element_pose(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "ChatGPT_Image.png"
    canonical.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    canonical.write_bytes(b"canonical")
    library.write_bytes(b"library")

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
        lambda p: "hash_library"
        if "ChatGPT" in str(p) and Path(p).read_bytes() == b"library"
        else "hash_canonical",
    )

    beat: dict = {"speaker": "Lorelai"}
    bg.apply_user_beat_ref_update(
        beat,
        "reference_image",
        {"abs_path": str(library), "key": "ChatGPT_Image"},
    )
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert library.read_bytes() == b"canonical"
    assert beat["reference_image_locked"] is True
    assert beat["element_char_ref_ok"] is True


def test_require_element_char_ref_for_o3_raises_before_api(tmp_path: Path, monkeypatch):
    library = tmp_path / "ChatGPT_Image_Jun_14.png"
    library.write_bytes(b"library")
    canonical = tmp_path / "lorelai_canonical.png"
    canonical.write_bytes(b"canonical")

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
        lambda p: "hash_library"
        if "ChatGPT" in str(p) and Path(p).read_bytes() == b"library"
        else "hash_canonical",
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
    }
    try:
        bg.require_element_char_ref_for_o3(beat)
        assert False, "expected ELEMENT_VISUAL_MISMATCH"
    except RuntimeError as exc:
        assert "ELEMENT_VISUAL_MISMATCH" in str(exc)
