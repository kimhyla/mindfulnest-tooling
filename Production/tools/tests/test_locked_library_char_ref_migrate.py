"""Locked Event_N/library char refs: path preserved; gate stays false until frontal match."""
from __future__ import annotations

import json
from pathlib import Path

import beat_generator as bg


def test_migrate_preserves_locked_library_path_and_keeps_gate_false_until_frontal(
    tmp_path, monkeypatch,
):
    """Pose-dir byte match is not Element frontal match — gate must stay False.

    Locked library drops under Event_N/library/ survive migrate. Gate flips True
    only when library bytes equal canonical frontal (SUBMIT_PARITY).
    """
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "operator_still.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_bytes(b"operator-still")
    pose = tmp_path / "Lorelai" / "poses" / "operator_still.png"
    pose.parent.mkdir(parents=True, exist_ok=True)
    pose.write_bytes(b"operator-still")
    frontal = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    frontal.write_bytes(b"frontal")
    (tmp_path / "character_subjects.json").write_text(
        json.dumps({
            "characters": {
                "Lorelai": {
                    "status": "active",
                    "element_id": "el1",
                    "kling_voice_id": "v1",
                    "frontal_image": "Lorelai/poses/lorelai_canonical_neutral.png",
                    "frontal_sha256": "deadbeef",
                    "refer_images": ["Lorelai/poses/lorelai_canonical_neutral.png"],
                    "element_name": "Lorelai",
                },
            },
        }),
        encoding="utf-8",
    )
    from tools import kling_character_registry as reg

    reg.set_prod_root(tmp_path)
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_30",
                            "speaker": "Lorelai",
                            "reference_image": {"abs_path": str(library)},
                            "reference_image_locked": True,
                            "element_char_ref_ok": False,
                            "element_char_ref_error": "stale",
                            "pipeline": "kling_o3_omni",
                        }],
                    },
                },
            },
        },
    }
    beat = bg._migrate_sidecar(sidecar)["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert beat.get("reference_image_locked") is True
    assert beat.get("element_char_ref_ok") is False


def test_migrate_sets_gate_ok_when_library_bytes_match_frontal(tmp_path, monkeypatch):
    library = tmp_path / "Event_2" / "library" / "images" / "sources" / "operator_still.png"
    library.parent.mkdir(parents=True, exist_ok=True)
    library.write_bytes(b"same-as-frontal")
    frontal = tmp_path / "Lorelai" / "poses" / "lorelai_canonical_neutral.png"
    frontal.parent.mkdir(parents=True, exist_ok=True)
    frontal.write_bytes(b"same-as-frontal")
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
    # Clear sha cache so frontal/library content hashes are computed fresh.
    monkeypatch.setattr(reg, "_SHA_CACHE", None)
    monkeypatch.setattr(reg, "_SHA_CACHE_PATH", tmp_path / "cache" / "sha.json")
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_30",
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
    beat = bg._migrate_sidecar(sidecar)["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert beat["reference_image"]["abs_path"] == str(library.resolve())
    assert beat.get("element_char_ref_ok") is True
