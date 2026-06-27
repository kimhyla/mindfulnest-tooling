import json
from pathlib import Path
import beat_generator as bg

def test_migrate_sets_gate_ok_when_pose_hash_matches(tmp_path, monkeypatch):
    library = tmp_path / "Event_2" / "library" / "sources" / "operator_still.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_bytes(b"operator-still")
    pose = tmp_path / "Lorelai" / "poses" / "operator_still.png"
    pose.parent.mkdir(parents=True, exist_ok=True)
    pose.write_bytes(b"operator-still")
    (tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png").write_bytes(b"frontal")
    (tmp_path / "character_subjects.json").write_text(json.dumps({"characters": {"Lorelai": {"status": "active", "element_id": "el1", "kling_voice_id": "v1", "frontal_image": "Lorelai/poses/lorelai_canonical_neutral.png", "refer_images": ["Lorelai/poses/lorelai_canonical_neutral.png"], "element_name": "Lorelai"}}}), encoding="utf-8")
    from tools import kling_character_registry as reg
    reg.set_prod_root(tmp_path)
    sidecar = {"arcs": {"arc_1": {"segments": {"event_2_pre": {"beats": [{"beat_id": "bg_arc1_event2_pre_beat_30", "speaker": "Lorelai", "reference_image": {"abs_path": str(library)}, "reference_image_locked": True, "element_char_ref_ok": False, "element_char_ref_error": "stale"}]}}}}}
    beat = bg._migrate_sidecar(sidecar)["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat.get("element_char_ref_ok") is True
