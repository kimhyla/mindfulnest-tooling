"""Stale Chipper intro tail must re-hydrate to Arlo single-canonical."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


@pytest.fixture()
def arlo_canonical_prod(tmp_path: Path, monkeypatch):
    prod = tmp_path / "Production"
    tail = prod / "templates" / "arlo_teleport_intro" / "canonical" / "variant_0" / "intro_tail.mp4"
    tail.parent.mkdir(parents=True)
    tail.write_bytes(b"arlo-tail")
    stale = prod / "templates" / "chipper_teleport_intro" / "canonical" / "variant_0" / "intro_tail.mp4"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"chipper-stale")
    for reg in ("arlo_teleport_intro", "chipper_teleport_intro"):
        (prod / "templates" / reg / "canonical_registry.json").write_text(
            json.dumps({"single_canonical": True, "variant_count": 1, "variants": [{
                "slot": 0,
                "intro_tail_rel": f"Production/templates/{reg}/canonical/variant_0/intro_tail.mp4",
            }]}),
            encoding="utf-8",
        )
    manifest = {
        "intro_canonical_beats": {
            "canonical_mirror_video": {
                "speaker": "Arlo",
                "prompt": "@Image1 (Arlo) Teleport glass finale.",
                "dialogue_text": "Ready?",
                "char_ref_asset": "mirror_char",
            },
        },
    }
    (prod / "templates" / "arlo_teleport_intro" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    return prod, tail, stale


def test_stale_chipper_tail_replaced_with_arlo(arlo_canonical_prod):
    _prod, arlo_tail, chipper_tail = arlo_canonical_prod
    beat = {
        "beat_id": "bg_arc1_event4_pre_beat_14",
        "intro_beat_role": "canonical_mirror_video",
        "speaker": "Arlo",
        "canonical_intro_tail": True,
        "kling_o3_video_path": str(chipper_tail.resolve()),
        "kling_o3_options": [{
            "slot_index": 0,
            "source": "canonical_intro_tail",
            "video_path": str(chipper_tail.resolve()),
        }],
    }
    assert bg.hydrate_intro_canonical_mirror_beat(beat, "4", "pre")
    assert str(arlo_tail.resolve()) in beat["kling_o3_video_path"]
    assert "chipper_teleport_intro" not in beat["kling_o3_video_path"]


def test_promote_baked_trim_clears_metadata(tmp_path: Path):
    src = tmp_path / "delivery.mp4"
    baked = tmp_path / "baked.mp4"
    src.write_bytes(b"x" * 100)
    baked.write_bytes(b"y" * 50)
    beat = {
        "beat_id": "bg_arc1_event4_pre_beat_10",
        "kling_o3_video_path": str(src),
        "kling_o3_trim_start": 0.0,
        "kling_o3_trim_back": 7.0,
        "kling_o3_options": [{
            "slot_index": 0,
            "video_path": str(src),
            "trim_start_s": 0.0,
            "trim_back_s": 7.0,
        }],
    }
    out = bg.promote_o3_baked_trim_to_active_clip(
        beat, baked_path=baked, slot_index=0,
    )
    assert out["video_path"] == str(baked.resolve())
    assert beat["kling_o3_video_path"] == str(baked.resolve())
    assert "kling_o3_trim_back" not in beat
    assert beat["kling_o3_options"][0]["video_path"] == str(baked.resolve())
    assert "trim_back_s" not in beat["kling_o3_options"][0]
