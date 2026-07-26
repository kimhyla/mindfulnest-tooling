"""User-dropped Beat Gen refs must survive sidecar migration / auto-align."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402
import operator_workbench_contract as owc  # noqa: E402


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
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.file_sha256",
        lambda p: "hash_library"
        if Path(p).read_bytes() == b"library"
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
    # Locked library drops must survive migrate — do not rewrite to Element frontal.
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert beat.get("reference_image_locked") is True
    assert library.read_bytes() == b"library"


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
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
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
    assert "canonical Element identity" in detail or "does not match Element" in detail


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
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
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
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
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
    assert bg.sync_element_char_ref_status(beat, heal_mismatch=False) is False
    assert beat["element_char_ref_ok"] is False
    assert "canonical Element identity" in beat["element_char_ref_error"] or "does not match Element" in beat["element_char_ref_error"]


def test_migrate_sidecar_preserves_locked_library_ref_when_file_exists(tmp_path: Path, monkeypatch):
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
    assert library.read_bytes() == b"library"
    assert beat["element_char_ref_ok"] is False


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
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
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


def test_apply_user_beat_ref_keeps_library_bytes_on_mismatch(tmp_path: Path, monkeypatch):
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
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
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
    assert library.read_bytes() == b"library"
    assert beat["reference_image_locked"] is True
    assert beat["element_char_ref_ok"] is False
    assert "canonical Element identity" in beat["element_char_ref_error"] or "does not match Element" in beat["element_char_ref_error"]


def test_reconcile_char_ref_with_element_readds_on_disk_pose(tmp_path: Path, monkeypatch):
    from tools import kling_character_registry as reg

    poses = tmp_path / "Lorelai" / "poses"
    poses.mkdir(parents=True)
    library = tmp_path / "Event_2" / "library" / "sources" / "ChatGPT_Image.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    payload = b"same-bytes-pose"
    library.write_bytes(payload)
    pose_rel = "Lorelai/poses/chatgpt_image.png"
    (tmp_path / pose_rel).write_bytes(payload)
    (poses / "lorelai_explaining.png").write_bytes(b"explaining")
    (poses / "lorelai_shocked.png").write_bytes(b"shocked")
    (tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png").write_bytes(b"frontal")

    registry = {
        "characters": {
            "Lorelai": {
                "status": "active",
                "element_id": "old_element",
                "kling_voice_id": "voice123",
                "frontal_image": "Lorelai/poses/lorelai_canonical_neutral.png",
                "refer_images": [
                    "Lorelai/poses/lorelai_explaining.png",
                    "Lorelai/poses/lorelai_shocked.png",
                ],
                "refer_pins": [
                    "Lorelai/poses/lorelai_explaining.png",
                    "Lorelai/poses/lorelai_shocked.png",
                ],
                "element_name": "Lorelai",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    reg.set_prod_root(tmp_path)

    captured: dict = {}

    def fake_register(char_name, cfg, voice_id, wavespeed_key):
        captured["refer_images"] = list(cfg.get("refer_images") or [])
        return "new_element", "pred-1"

    monkeypatch.setattr("tools.kling_element_voice.register_kling_element", fake_register)

    result = reg.reconcile_char_ref_with_element("Lorelai", str(library), "ws-key")
    assert result["ok"] is True
    assert result["reconciled"] is True
    assert result["element_id"] == "new_element"
    assert pose_rel in captured["refer_images"]
    ok, _ = reg.char_ref_matches_element_images(str(library), "Lorelai")
    assert ok is True


def test_ensure_beat_element_char_ref_for_o3_accepts_canonical_frontal(
    tmp_path: Path, monkeypatch,
):
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"canonical-front")

    registry = {
        "characters": {
            "Lorelai": {
                "status": "active",
                "element_id": "old",
                "kling_voice_id": "v1",
                "frontal_image": "Lorelai/poses/lorelai_canonical_neutral.png",
                "frontal_sha256": __import__("hashlib").sha256(b"canonical-front").hexdigest(),
                "refer_images": ["Lorelai/poses/lorelai_canonical_neutral.png"],
                "element_name": "Lorelai",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")

    from tools import kling_character_registry as reg

    reg.set_prod_root(tmp_path)
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(canonical)},
        "reference_image_locked": True,
        "element_char_ref_ok": False,
    }
    assert bg.ensure_beat_element_char_ref_for_o3(beat, "ws-key") is True
    assert beat["element_char_ref_ok"] is True


def test_ensure_beat_element_char_ref_blocked_when_library_not_canonical_frontal(
    tmp_path: Path, monkeypatch,
):
    """SUBMIT_PARITY_V1: refer reconcile cannot bypass canonical frontal bytes."""
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "ChatGPT_Image.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_bytes(b"same-bytes")
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"frontal-bytes")

    registry = {
        "characters": {
            "Lorelai": {
                "status": "active",
                "element_id": "old",
                "kling_voice_id": "v1",
                "frontal_image": "Lorelai/poses/lorelai_canonical_neutral.png",
                "frontal_sha256": __import__("hashlib").sha256(b"frontal-bytes").hexdigest(),
                "refer_images": ["Lorelai/poses/lorelai_canonical_neutral.png"],
                "element_name": "Lorelai",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")

    from tools import kling_character_registry as reg

    reg.set_prod_root(tmp_path)
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_element_voice.register_kling_element",
        lambda *a, **k: ("elem_new", "pred"),
    )

    beat = {
        "speaker": "Lorelai",
        "reference_image": {"abs_path": str(library)},
        "reference_image_locked": True,
        "element_char_ref_ok": False,
    }
    assert bg.ensure_beat_element_char_ref_for_o3(beat, "ws-key") is False
    assert beat["element_char_ref_ok"] is False
    assert "canonical Element identity" in (beat.get("element_char_ref_error") or "")


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


def test_heal_locked_char_ref_redirects_missing_library_path_without_overwrite(
    tmp_path: Path, monkeypatch,
):
    canonical = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "ChatGPT_Image.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(b"canonical")
    assert not library.is_file()

    monkeypatch.setattr(
        "tools.kling_character_registry.element_image_paths",
        lambda _s: [canonical],
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    monkeypatch.setattr(
        "tools.kling_character_registry.get_character_entry",
        lambda _s: {"status": "active", "element_id": "123"},
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
        "element_char_ref_error": "Missing character reference image for 'Lorelai'",
    }
    assert bg.heal_locked_char_ref_to_element(beat) is True
    assert not library.is_file()
    assert beat["reference_image"]["abs_path"] == str(canonical.resolve())
    assert bg.sync_element_char_ref_status(beat) is True
    assert beat["element_char_ref_ok"] is True
    assert "element_char_ref_error" not in beat


def test_align_beat_reference_on_speaker_change_when_unlocked(tmp_path: Path, monkeypatch):
    canonical = tmp_path / "lorelai_canonical_neutral.png"
    canonical.write_bytes(b"canonical")

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
        lambda _p: "hash_canonical",
    )

    beat: dict = {"speaker": "Lorelai", "reference_image": None}
    assert bg.align_beat_reference_to_element(beat) is True
    assert beat["reference_image"]["abs_path"] == str(canonical.resolve())
    assert bg.sync_element_char_ref_status(beat, heal_mismatch=False) is True


def test_realign_char_ref_when_speaker_changes_from_old_character(tmp_path: Path, monkeypatch):
    oliver_pose = tmp_path / "Oliver" / "poses" / "oliver_neutral.png"
    ember_pose = tmp_path / "Ember" / "poses" / "ember_neutral.png"
    oliver_pose.parent.mkdir(parents=True)
    ember_pose.parent.mkdir(parents=True)
    oliver_pose.write_bytes(b"oliver-bytes")
    ember_pose.write_bytes(b"ember-bytes")

    def _paths(speaker: str):
        if speaker == "Oliver":
            return [oliver_pose]
        if speaker == "Ember":
            return [ember_pose]
        return []

    def _hash(path):
        p = Path(path)
        if "oliver" in p.name:
            return "hash_oliver"
        if "ember" in p.name:
            return "hash_ember"
        return "hash_other"

    monkeypatch.setattr("tools.kling_character_registry.element_image_paths", _paths)
    monkeypatch.setattr("tools.kling_character_registry.get_character_entry", lambda _s: {"status": "active", "element_id": "1"})
    monkeypatch.setattr("tools.kling_character_registry.is_speaker_voice_ready", lambda _s: True)
    monkeypatch.setattr("tools.kling_character_registry.file_sha256", _hash)
    monkeypatch.setattr("tools.kling_character_registry.find_pose_rel_by_hash", lambda *_a: None)
    monkeypatch.setattr(
        "tools.kling_character_registry.load_character_subjects",
        lambda: {"characters": {"Oliver": {}, "Ember": {}}},
    )
    monkeypatch.setattr("tools.kling_character_registry.resolve_registry_key", lambda s: s)

    beat = {
        "speaker": "Ember",
        "reference_image": {"abs_path": str(oliver_pose.resolve())},
        "reference_image_locked": True,
    }
    assert bg.realign_beat_char_ref_for_speaker_change(beat, old_speaker="Oliver") is True
    assert beat["reference_image"]["abs_path"] == str(ember_pose.resolve())
    assert beat.get("reference_image_locked") is not True


def test_heal_speaker_char_ref_mismatch_on_migrate(tmp_path: Path, monkeypatch):
    oliver_pose = tmp_path / "Oliver" / "poses" / "oliver_neutral.png"
    ember_pose = tmp_path / "Ember" / "poses" / "ember_neutral.png"
    oliver_pose.parent.mkdir(parents=True)
    ember_pose.parent.mkdir(parents=True)
    oliver_pose.write_bytes(b"oliver-bytes")
    ember_pose.write_bytes(b"ember-bytes")

    def _paths(speaker: str):
        if speaker == "Oliver":
            return [oliver_pose]
        if speaker == "Ember":
            return [ember_pose]
        return []

    def _hash(path):
        p = Path(path)
        if "oliver" in p.name:
            return "hash_oliver"
        if "ember" in p.name:
            return "hash_ember"
        return "hash_other"

    monkeypatch.setattr("tools.kling_character_registry.element_image_paths", _paths)
    monkeypatch.setattr("tools.kling_character_registry.get_character_entry", lambda _s: {"status": "active", "element_id": "1"})
    monkeypatch.setattr("tools.kling_character_registry.is_speaker_voice_ready", lambda _s: True)
    monkeypatch.setattr("tools.kling_character_registry.file_sha256", _hash)
    monkeypatch.setattr("tools.kling_character_registry.find_pose_rel_by_hash", lambda *_a: None)
    monkeypatch.setattr(
        "tools.kling_character_registry.load_character_subjects",
        lambda: {"characters": {"Oliver": {}, "Ember": {}}},
    )
    monkeypatch.setattr("tools.kling_character_registry.resolve_registry_key", lambda s: s)
    monkeypatch.setattr(bg, "element_char_ref_required_for_beat", lambda _b, _s=None: True)

    beat = {
        "speaker": "Ember",
        "reference_image": {"abs_path": str(oliver_pose.resolve())},
        "reference_image_locked": True,
        "pipeline": "kling_o3_omni",
    }
    assert owc.migrate_operator_workbench_beat(beat) is True
    assert beat["reference_image"]["abs_path"] == str(ember_pose.resolve())


def test_char_ref_display_prefers_persisted_sidecar_path(tmp_path: Path):
    stored = tmp_path / "library_still.png"
    fallback = tmp_path / "implicit.png"
    stored.write_bytes(b"stored")
    fallback.write_bytes(b"fallback")
    beat = {
        "speaker": "Ember",
        "reference_image": {"abs_path": str(stored), "key": "ember_custom"},
    }
    monkeypatch_paths = None

    def fake_resolve(b):
        return str(fallback)

    import beat_generator as bg_mod
    original = bg_mod.resolve_beat_char_ref_path
    bg_mod.resolve_beat_char_ref_path = fake_resolve
    try:
        display = owc.resolve_beat_char_ref_display(beat, approved_roots=[str(tmp_path)])
    finally:
        bg_mod.resolve_beat_char_ref_path = original
    assert display is not None
    assert display["abs_path"] == str(stored)


def test_bg_update_beat_uses_speaker_realign_not_unlocked_align_only():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "realign_beat_char_ref_for_speaker_change" in text
    assert "if field == \"speaker\" and not b.get(\"reference_image_locked\"):" not in text


def test_bg_align_element_ref_handler_registered():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "def handle_bg_align_element_ref" in text
    assert "align_beat_reference_to_element(b)" in text
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/bg/align-element-ref" in server


def test_add_element_pose_appends_refer_and_reregisters(tmp_path: Path, monkeypatch):
    from tools import kling_character_registry as reg

    poses = tmp_path / "Arlo" / "poses"
    poses.mkdir(parents=True)
    (poses / "arlo_canonical_neutral_vest.png").write_bytes(b"frontal")
    source = tmp_path / "Event_2" / "library" / "sources" / "custom_pose.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"library-pose")

    registry = {
        "characters": {
            "Arlo": {
                "status": "active",
                "element_id": "old_element",
                "kling_voice_id": "voice123",
                "frontal_image": "Arlo/poses/arlo_canonical_neutral_vest.png",
                "refer_images": ["Arlo/poses/arlo_happy_vest.png"],
                "element_name": "Arlo",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    reg.set_prod_root(tmp_path)

    captured: dict = {}

    def fake_register(char_name, cfg, voice_id, wavespeed_key):
        captured["char_name"] = char_name
        captured["voice_id"] = voice_id
        captured["refer_images"] = list(cfg.get("refer_images") or [])
        return "new_element_999", "pred-1"

    monkeypatch.setattr("tools.kling_element_voice.register_kling_element", fake_register)

    result = reg.add_element_pose("Arlo", source, "ws-key-test")
    assert result["ok"] is True
    assert result["element_id"] == "new_element_999"
    assert captured["voice_id"] == "voice123"
    assert any("custom_pose" in r for r in captured["refer_images"])
    saved = json.loads((tmp_path / "character_subjects.json").read_text(encoding="utf-8"))
    assert saved["characters"]["Arlo"]["element_id"] == "new_element_999"
    assert Path(result["pose_abs_path"]).is_file()


def test_add_element_pose_trims_refer_images_at_kling_cap(tmp_path: Path, monkeypatch):
    from tools import kling_character_registry as reg

    poses = tmp_path / "Tessa" / "poses"
    poses.mkdir(parents=True)
    (poses / "tessa_happy_ref.png").write_bytes(b"happy")
    (poses / "tessa_sad_ref.png").write_bytes(b"sad")
    (poses / "tessa_extra_ref.png").write_bytes(b"extra")
    source = tmp_path / "library" / "new_pose.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"new")

    registry = {
        "characters": {
            "Tessa": {
                "status": "active",
                "element_id": "old_element",
                "kling_voice_id": "voice123",
                "frontal_image": "Tessa/poses/tessa_happy_ref.png",
                "refer_images": [
                    "Tessa/poses/tessa_happy_ref.png",
                    "Tessa/poses/tessa_sad_ref.png",
                    "Tessa/poses/tessa_extra_ref.png",
                ],
                "element_name": "Tessa",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    reg.set_prod_root(tmp_path)

    captured: dict = {}

    def fake_register(char_name, cfg, voice_id, wavespeed_key):
        captured["refer_images"] = list(cfg.get("refer_images") or [])
        return "new_element", "pred-1"

    monkeypatch.setattr("tools.kling_element_voice.register_kling_element", fake_register)

    result = reg.add_element_pose("Tessa", source, "ws-key")
    assert result["ok"] is True
    refs = captured["refer_images"]
    assert len(refs) == 3
    assert any("new_pose" in r for r in refs)
    assert "Tessa/poses/tessa_happy_ref.png" in refs  # frontal_image pinned
    assert "Tessa/poses/tessa_sad_ref.png" not in refs


def test_register_kling_element_uses_registry_prod_root(tmp_path: Path, monkeypatch):
    """Pose copy + Element re-register must share runtime Production/ (not __file__ parent)."""
    from tools import kling_character_registry as reg
    from tools.kling_element_voice import register_kling_element

    poses = tmp_path / "Tessa" / "poses"
    poses.mkdir(parents=True)
    (poses / "tessa_front.png").write_bytes(b"front")
    (poses / "tessa_pose.png").write_bytes(b"pose")
    reg.set_prod_root(tmp_path)

    cfg = {
        "frontal_image": "Tessa/poses/tessa_front.png",
        "refer_images": ["Tessa/poses/tessa_pose.png"],
        "element_name": "Tessa",
    }
    uploaded: list[str] = []

    monkeypatch.setattr(
        "tools.kling_element_voice.upload_catbox",
        lambda p: uploaded.append(str(p.resolve())) or "http://catbox/fake",
    )
    monkeypatch.setattr(
        "tools.kling_element_voice.curl_json",
        lambda *a, **k: {"data": {"id": "pred-1"}},
    )
    monkeypatch.setattr(
        "tools.kling_element_voice.poll_wavespeed",
        lambda *a, **k: {"element_id": "el-new", "outputs": []},
    )

    element_id, _ = register_kling_element("Tessa", cfg, "voice1", "ws-key")
    assert element_id == "el-new"
    assert uploaded
    assert all(str(tmp_path) in path for path in uploaded)


def test_char_ref_matches_on_disk_pose_before_refer_images_catch_up(
    tmp_path: Path, monkeypatch,
):
    """Library still bytes copied to poses/ must pass gate even when refer_images lag."""
    library = tmp_path / "Event_2" / "library" / "sources" / "ChatGPT_Jun_15.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_bytes(b"operator-still")
    pose = tmp_path / "Lorelai" / "poses" / "chatgpt_jun_15.png"
    pose.parent.mkdir(parents=True, exist_ok=True)
    pose.write_bytes(b"operator-still")
    (tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png").write_bytes(b"frontal")
    (tmp_path / "character_subjects.json").write_text(
        json.dumps({
            "characters": {
                "Lorelai": {
                    "status": "active",
                    "element_id": "el1",
                    "kling_voice_id": "v1",
                    "frontal_image": "Lorelai/poses/lorelai_canonical_neutral.png",
                    "refer_images": ["Lorelai/poses/lorelai_canonical_neutral.png"],
                    "element_name": "Lorelai",
                },
            },
        }),
            encoding="utf-8",
        )
    from tools import kling_character_registry as reg

    reg.set_prod_root(tmp_path)
    ok, detail = reg.char_ref_matches_element_images(str(library), "Lorelai")
    assert ok is True, detail


def test_sync_element_char_ref_ok_while_o3_job_running():
    beat = {
        "speaker": "Lorelai",
        "reference_image_locked": True,
        "element_char_ref_ok": False,
        "element_char_ref_error": "stale mismatch",
        "kling_o3_voice_fix_status": "o3_running",
        "kling_o3_voice_fix_ui_job_id": "abc123",
    }
    assert bg.sync_element_char_ref_status(beat, heal_mismatch=False) is True
    assert beat["element_char_ref_ok"] is True
    assert "element_char_ref_error" not in beat


def test_bg_add_element_pose_handler_registered():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "def handle_bg_add_element_pose" in text
    assert "add_element_pose" in text
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/bg/add-element-pose" in server
    endpoints = (TOOLS / "storyboard-v2" / "src" / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "bg_add_element_pose" in endpoints


def test_humanoid_benson_refs_use_production_poses_dir():
    from beat_generator import _HUMANOID_CHAR_REFS

    benson = _HUMANOID_CHAR_REFS["Benson"]
    assert benson["default"].startswith("Production/Benson/poses/")
    assert benson["neutral"].startswith("Production/Benson/poses/")
    assert "benson_neutral_ref.png" not in benson["default"]


def test_materialize_char_ref_abs_path_prefers_body_then_sidecar(tmp_path: Path):
    sidecar_path = tmp_path / "stored.png"
    body_path = tmp_path / "body.png"
    sidecar_path.write_bytes(b"s")
    body_path.write_bytes(b"b")
    beat = {"reference_image": {"abs_path": str(sidecar_path)}}
    assert owc.materialize_char_ref_abs_path(beat, str(body_path)) == str(body_path.resolve())
    assert owc.materialize_char_ref_abs_path(beat, "") == str(sidecar_path.resolve())


def test_try_register_locked_drop_adds_pose_without_changing_frontal(
    tmp_path: Path, monkeypatch,
):
    from tools import kling_character_registry as reg

    poses = tmp_path / "Benson" / "poses"
    poses.mkdir(parents=True)
    (poses / "benson_pose_neutral.png").write_bytes(b"frontal-bytes")
    drop = tmp_path / "library" / "new_pose.png"
    drop.parent.mkdir(parents=True)
    drop.write_bytes(b"new-drop-bytes")

    registry = {
        "characters": {
            "Benson": {
                "status": "active",
                "element_id": "el1",
                "kling_voice_id": "voice123",
                "frontal_image": "Benson/poses/benson_pose_neutral.png",
                "refer_images": ["Benson/poses/benson_pose_neutral.png"],
                "element_name": "Benson",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    reg.set_prod_root(tmp_path)

    calls: list[dict] = []

    def fake_add(speaker, path, key):
        calls.append({"speaker": speaker, "path": path})
        return {"ok": True, "pose_rel": "Benson/poses/new_pose.png", "action": "added"}

    monkeypatch.setattr(reg, "add_element_pose", fake_add)
    monkeypatch.setattr(
        reg,
        "char_ref_matches_element_images",
        lambda *_a, **_k: (False, "no match"),
    )
    monkeypatch.setattr(reg, "is_speaker_voice_ready", lambda _s: True)
    monkeypatch.setattr(
        reg,
        "reconcile_char_ref_with_element",
        lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError("no pose")),
    )

    beat = {
        "speaker": "Benson",
        "reference_image": {"abs_path": str(drop)},
        "reference_image_locked": True,
    }
    monkeypatch.setattr(bg, "resolve_beat_char_ref_path", lambda _b: str(drop))
    out = bg.try_register_dropped_char_ref_on_element(beat, "ws-key")
    assert out["ok"] is True
    assert calls[0]["speaker"] == "Benson"
    assert calls[0]["path"] == str(drop)
    saved = json.loads((tmp_path / "character_subjects.json").read_text(encoding="utf-8"))
    assert saved["characters"]["Benson"]["frontal_image"] == "Benson/poses/benson_pose_neutral.png"


def test_add_element_pose_does_not_change_frontal(tmp_path: Path, monkeypatch):
    from tools import kling_character_registry as reg

    poses = tmp_path / "Benson" / "poses"
    poses.mkdir(parents=True)
    (poses / "benson_pose_neutral.png").write_bytes(b"frontal")
    source = tmp_path / "library" / "custom.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"custom")

    registry = {
        "characters": {
            "Benson": {
                "status": "active",
                "element_id": "old",
                "kling_voice_id": "voice123",
                "frontal_image": "Benson/poses/benson_pose_neutral.png",
                "refer_images": ["Benson/poses/benson_pose_neutral.png"],
                "element_name": "Benson",
            },
        },
    }
    (tmp_path / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    reg.set_prod_root(tmp_path)

    monkeypatch.setattr(
        "tools.kling_element_voice.register_kling_element",
        lambda *_a, **_k: ("new_el", "pred"),
    )

    reg.add_element_pose("Benson", source, "ws-key")
    saved = json.loads((tmp_path / "character_subjects.json").read_text(encoding="utf-8"))
    assert saved["characters"]["Benson"]["frontal_image"] == "Benson/poses/benson_pose_neutral.png"
