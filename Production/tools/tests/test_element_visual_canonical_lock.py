"""ELEMENT_VISUAL_CANONICAL_LOCK_V1 — byte-stamped Element frontal identity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_png(path: Path, tag: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tag)


def _benson_registry(frontal_rel: str, *, sha: str | None = None) -> dict:
    cfg: dict = {
        "status": "active",
        "element_id": "el-old",
        "kling_voice_id": "voice123",
        "frontal_image": frontal_rel,
        "refer_images": [frontal_rel],
        "element_name": "Benson",
    }
    if sha:
        cfg["frontal_sha256"] = sha
    return {"characters": {"Benson": cfg}}


@pytest.fixture
def prod_root(tmp_path: Path, monkeypatch):
    from tools import kling_character_registry as reg

    reg.set_prod_root(tmp_path)
    monkeypatch.setattr(reg, "is_speaker_voice_ready", lambda _s: True)
    monkeypatch.setattr(
        "tools.kling_element_voice.register_kling_element",
        lambda *_a, **_k: ("el-new", "pred"),
    )
    return tmp_path


def test_verify_frontal_sha256_passes_when_bytes_match(prod_root: Path):
    from tools import kling_character_registry as reg

    rel = "Benson/poses/front.png"
    path = prod_root / rel
    _write_png(path, b"front-bytes")
    sha = reg.file_sha256(path)
    ok, detail = reg.verify_frontal_sha256({"frontal_image": rel, "frontal_sha256": sha})
    assert ok is True
    assert detail == ""


def test_verify_frontal_sha256_fails_on_mismatch(prod_root: Path):
    from tools import kling_character_registry as reg

    rel = "Benson/poses/front.png"
    _write_png(prod_root / rel, b"front-bytes")
    ok, detail = reg.verify_frontal_sha256(
        {"frontal_image": rel, "frontal_sha256": "deadbeef" * 8},
    )
    assert ok is False
    assert "mismatch" in detail


def test_add_element_pose_refer_only_preserves_frontal(prod_root: Path):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/benson_pose_neutral.png"
    _write_png(prod_root / frontal_rel, b"frontal")
    (prod_root / "character_subjects.json").write_text(
        json.dumps(_benson_registry(frontal_rel)), encoding="utf-8",
    )
    source = prod_root / "library" / "custom.png"
    _write_png(source, b"custom")

    out = reg.add_element_pose("Benson", source, "ws-key")
    saved = json.loads((prod_root / "character_subjects.json").read_text(encoding="utf-8"))
    assert saved["characters"]["Benson"]["frontal_image"] == frontal_rel
    assert out["pose_rel"] in saved["characters"]["Benson"]["refer_images"]


def test_set_element_identity_stamps_sha_and_updates_frontal(prod_root: Path):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/benson_pose_neutral.png"
    _write_png(prod_root / frontal_rel, b"old-front")
    (prod_root / "character_subjects.json").write_text(
        json.dumps(_benson_registry(frontal_rel)), encoding="utf-8",
    )
    source = prod_root / "library" / "baseline_char_rabbit_gardener.png"
    _write_png(source, b"tan-gardener-bytes")

    out = reg.set_element_identity("Benson", source, "ws-key")
    saved = json.loads((prod_root / "character_subjects.json").read_text(encoding="utf-8"))
    cfg = saved["characters"]["Benson"]
    assert cfg["frontal_image"] == out["pose_rel"]
    assert cfg["frontal_sha256"] == out["frontal_sha256"]
    assert cfg["visual_canonical_locked"] is True
    assert cfg["visual_canonical_lock_source"] == "set_element_identity"
    ok, _ = reg.verify_frontal_sha256(cfg)
    assert ok is True


def test_lazy_sha_migration_on_load(prod_root: Path):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/front.png"
    path = prod_root / frontal_rel
    _write_png(path, b"migrate-me")
    sha = reg.file_sha256(path)
    (prod_root / "character_subjects.json").write_text(
        json.dumps(_benson_registry(frontal_rel)), encoding="utf-8",
    )

    data = reg.load_character_subjects()
    cfg = data["characters"]["Benson"]
    assert cfg["frontal_sha256"] == sha
    assert cfg.get("visual_canonical_lock_source") == "auto_migrate_v1"


def test_resolve_frontal_strict_raises_on_mismatch(prod_root: Path):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/front.png"
    _write_png(prod_root / frontal_rel, b"bytes-on-disk")
    (prod_root / "character_subjects.json").write_text(
        json.dumps(_benson_registry(frontal_rel, sha="0" * 64)), encoding="utf-8",
    )

    with pytest.raises(reg.ElementVisualCanonicalError):
        reg.resolve_frontal_abs_path("Benson", strict=True)


def test_no_promote_frontal_in_registry_module():
    text = Path(__file__).resolve().parent.parent / "kling_character_registry.py"
    assert "promote_frontal" not in text.read_text(encoding="utf-8")


def test_char_ref_aligned_rejects_baseline_when_canonical_locked(prod_root: Path):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/chatgpt_front.png"
    baseline_rel = "assets/image_library/baseline/baseline_char_rabbit_gardener.png"
    _write_png(prod_root / frontal_rel, b"canonical-front")
    _write_png(prod_root / baseline_rel, b"legacy-baseline")
    frontal_sha = reg.file_sha256(prod_root / frontal_rel)
    registry = _benson_registry(frontal_rel, sha=frontal_sha)
    registry["characters"]["Benson"]["visual_canonical_locked"] = True
    registry["characters"]["Benson"]["refer_images"] = [frontal_rel, baseline_rel]
    (prod_root / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")

    ok, detail = reg.char_ref_aligned_for_intent_commit(str(prod_root / baseline_rel), "Benson")
    assert ok is False
    assert "canonical Element identity" in detail

    ok2, _ = reg.char_ref_aligned_for_intent_commit(str(prod_root / frontal_rel), "Benson")
    assert ok2 is True


def test_set_element_identity_pins_proven_o3_bind_and_scrubs_baseline(prod_root: Path):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/benson_pose_neutral.png"
    baseline_rel = "assets/image_library/baseline/baseline_char_rabbit_gardener.png"
    _write_png(prod_root / frontal_rel, b"old-front")
    _write_png(prod_root / baseline_rel, b"legacy-baseline")
    registry = _benson_registry(frontal_rel)
    registry["characters"]["Benson"]["refer_images"] = [frontal_rel, baseline_rel]
    (prod_root / "character_subjects.json").write_text(json.dumps(registry), encoding="utf-8")
    source = prod_root / "library" / "new_front.png"
    _write_png(source, b"tan-gardener-bytes")

    out = reg.set_element_identity("Benson", source, "ws-key")
    saved = json.loads((prod_root / "character_subjects.json").read_text(encoding="utf-8"))
    cfg = saved["characters"]["Benson"]
    proven = cfg.get("proven_o3_bind") or {}
    assert proven.get("lock_element_id") is True
    assert proven.get("element_id") == out["element_id"]
    assert not any("baseline_char_" in str(r) for r in (cfg.get("refer_images") or []))


def test_set_element_identity_persists_registry_once(prod_root: Path, monkeypatch):
    from tools import kling_character_registry as reg

    frontal_rel = "Benson/poses/benson_pose_neutral.png"
    front_path = prod_root / frontal_rel
    _write_png(front_path, b"old-front")
    frontal_sha = reg.file_sha256(front_path)
    (prod_root / "character_subjects.json").write_text(
        json.dumps(_benson_registry(frontal_rel, sha=frontal_sha)), encoding="utf-8",
    )
    source = prod_root / "library" / "new_front.png"
    _write_png(source, b"tan-gardener-bytes")
    saves: list[dict] = []
    monkeypatch.setattr(reg, "save_character_subjects", lambda data: saves.append(dict(data)))

    reg.set_element_identity("Benson", source, "ws-key")

    assert len(saves) == 1
    cfg = saves[0]["characters"]["Benson"]
    assert cfg.get("proven_o3_bind", {}).get("lock_element_id") is True
    assert cfg.get("frontal_sha256")


def test_heal_event_beats_to_canonical_frontal(prod_root: Path):
    from tools import beat_generator as bg
    from tools import kling_character_registry as reg

    reg.set_prod_root(prod_root)
    frontal = prod_root / "Benson/poses/front.png"
    baseline = prod_root / "library/baseline.png"
    _write_png(frontal, b"front")
    _write_png(baseline, b"base")
    sidecar = {
        "beats": [
            {
                "beat_id": "bg_arc1_event5_pre_beat_01",
                "speaker": "Benson",
                "reference_image": {"abs_path": str(baseline)},
            },
            {
                "beat_id": "bg_arc1_event5_pre_beat_03",
                "speaker": "Benson",
                "reference_image": {"abs_path": str(baseline)},
            },
            {
                "beat_id": "bg_arc1_event5_pre_beat_02",
                "speaker": "Arlo",
                "reference_image": {"abs_path": str(baseline)},
            },
        ],
    }
    healed = bg.heal_event_beats_to_canonical_frontal(
        sidecar,
        "Benson",
        str(frontal),
        pose_rel="Benson/poses/front.png",
    )
    assert healed == ["bg_arc1_event5_pre_beat_01", "bg_arc1_event5_pre_beat_03"]
    assert sidecar["beats"][0]["reference_image"]["abs_path"] == str(frontal)
    assert sidecar["beats"][0]["reference_image_locked"] is True
    assert sidecar["beats"][2]["reference_image"]["abs_path"] == str(baseline)
