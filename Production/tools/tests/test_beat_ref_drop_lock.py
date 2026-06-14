"""User-dropped Beat Gen refs must survive sidecar migration / auto-align."""
from __future__ import annotations

import json
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
    assert beat["reference_image"]["abs_path"] == str(canonical.resolve())
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
    assert bg.sync_element_char_ref_status(beat, heal_mismatch=False) is False
    assert beat["element_char_ref_ok"] is False
    assert "does not match Element images" in beat["element_char_ref_error"]


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
    assert "does not match Element images" in beat["element_char_ref_error"]


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


def test_bg_align_element_ref_handler_registered():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "def handle_bg_align_element_ref" in text
    assert "align_beat_reference_to_element(beat)" in text
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

    def fake_refresh(char_name, cfg, wavespeed_key, elevenlabs_key=None):
        captured["char_name"] = char_name
        captured["refer_images"] = list(cfg.get("refer_images") or [])
        updated = dict(cfg)
        updated["kling_voice_id"] = "voice_new_456"
        updated["element_id"] = "new_element_999"
        return updated

    monkeypatch.setattr(
        "tools.kling_element_voice.refresh_voice_and_register_element",
        fake_refresh,
    )

    result = reg.add_element_pose("Arlo", source, "ws-key-test")
    assert result["ok"] is True
    assert result["element_id"] == "new_element_999"
    assert result["kling_voice_id"] == "voice_new_456"
    assert result.get("voice_rebound") is True
    assert captured["char_name"] == "Arlo"
    assert any("custom_pose" in r for r in captured["refer_images"])
    saved = json.loads((tmp_path / "character_subjects.json").read_text(encoding="utf-8"))
    assert saved["characters"]["Arlo"]["element_id"] == "new_element_999"
    assert saved["characters"]["Arlo"]["kling_voice_id"] == "voice_new_456"
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

    def fake_refresh(char_name, cfg, wavespeed_key, elevenlabs_key=None):
        captured["refer_images"] = list(cfg.get("refer_images") or [])
        updated = dict(cfg)
        updated["kling_voice_id"] = "voice_new"
        updated["element_id"] = "new_element"
        return updated

    monkeypatch.setattr(
        "tools.kling_element_voice.refresh_voice_and_register_element",
        fake_refresh,
    )

    result = reg.add_element_pose("Tessa", source, "ws-key")
    assert result["ok"] is True
    refs = captured["refer_images"]
    assert len(refs) == 3
    assert any("new_pose" in r for r in refs)
    assert "Tessa/poses/tessa_happy_ref.png" not in refs


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


def test_bg_add_element_pose_handler_registered():
    text = (TOOLS / "server_handlers" / "background.py").read_text(encoding="utf-8")
    assert "def handle_bg_add_element_pose" in text
    assert "add_element_pose" in text
    server = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "/api/bg/add-element-pose" in server
    endpoints = (TOOLS / "storyboard-v2" / "src" / "api" / "endpoints.ts").read_text(encoding="utf-8")
    assert "bg_add_element_pose" in endpoints
