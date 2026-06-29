"""Stale Chipper intro tail must re-hydrate to Arlo single-canonical."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

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


def test_restore_untrimmed_still_insert(tmp_path: Path):
    src = tmp_path / "bg_arc1_event4_pre_beat_05_still_insert_1782751303.mp4"
    trimmed = tmp_path / "bg_arc1_event4_pre_beat_05_still_insert_1782751303_tts_trimmed_1782754163.mp4"
    src.write_bytes(b"x" * 100)
    trimmed.write_bytes(b"y" * 50)
    beat = {
        "beat_id": "bg_arc1_event4_pre_beat_05",
        "kling_o3_video_path": str(trimmed),
        "kling_o3_options": [{
            "slot_index": 0,
            "active": True,
            "video_path": str(trimmed),
            "trim_start_s": 2.33,
            "key": "bg_arc1_event4_pre_beat_05_still_insert_1782751303",
        }],
    }
    out = bg.restore_o3_option_untrimmed_video(beat, slot_index=0, video_path=str(trimmed))
    assert out["video_path"] == str(src.resolve())
    assert beat["kling_o3_video_path"] == str(src.resolve())
    assert "trim_start_s" not in beat["kling_o3_options"][0]


def test_bake_still_insert_preserves_untrimmed_lineage(tmp_path: Path):
    src = tmp_path / "beat_still_insert_1.mp4"
    src.write_bytes(b"x" * 100)
    beat = {
        "beat_id": "beat",
        "source": "still_insert_ken_burns",
        "kling_o3_video_path": str(src),
        "kling_o3_trim_start": 1.0,
        "kling_o3_trim_back": 0.5,
        "kling_o3_options": [{"video_path": str(src), "slot_index": 0}],
    }
    with patch.object(bg, "materialize_kling_o3_trimmed_clip") as mat:
        mat.side_effect = lambda _beat, dest, **_: dest.write_bytes(b"z" * 50) or dest
        with patch.object(bg, "_ffprobe_duration", return_value=6.0):
            bake = bg.bake_still_insert_trim_into_clip(beat)
    assert bake["baked"] is True
    opt = beat["kling_o3_options"][0]
    assert opt["o3_untrimmed_video_path"] == str(src.resolve())
    assert opt["video_path"] != str(src.resolve())
