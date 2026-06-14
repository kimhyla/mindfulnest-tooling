"""Arlo intro canonical mirror hydration on sidecar migrate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def test_migrate_hydrates_arlo_canonical_mirror_beat(tmp_path: Path, monkeypatch):
    prod = tmp_path / "Production"
    tail = prod / "templates" / "arlo_teleport_intro" / "canonical" / "variant_0" / "intro_tail.mp4"
    tail.parent.mkdir(parents=True)
    tail.write_bytes(b"mp4")
    studio_bg = prod / "canonical_images" / "canonical_arlo_studio_bg_v1.png"
    studio_bg.parent.mkdir(parents=True)
    studio_bg.write_bytes(b"bg")
    manifest = {
        "guide": "Arlo",
        "assets": {
            "mirror_char": "Arlo/poses/arlo.png",
            "studio_bg": "Production/canonical_images/canonical_arlo_studio_bg_v1.png",
            "neutral_char": "Arlo/poses/arlo.png",
        },
        "intro_canonical_beats": {
            "canonical_mirror_video": {
                "speaker": "Arlo",
                "dialogue_text": "Ready?",
                "prompt": "@Image1 Arlo speaks",
                "char_ref_asset": "mirror_char",
                "bg_ref_asset": "studio_bg",
            },
            "semi_canonical_transition": {
                "speaker": "Arlo",
                "prompt_template": "Alright Kiddo. ENTER TEXT HERE.",
                "char_ref_asset": "neutral_char",
                "bg_ref_asset": "studio_bg",
            },
        },
    }
    manifest_path = prod / "templates" / "arlo_teleport_intro" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (prod / "Arlo" / "poses").mkdir(parents=True)
    (prod / "Arlo" / "poses" / "arlo.png").write_bytes(b"char")
    registry = {
        "single_canonical": True,
        "variant_count": 1,
        "variants": [{
            "slot": 0,
            "intro_tail_rel": "Production/templates/arlo_teleport_intro/canonical/variant_0/intro_tail.mp4",
        }],
    }
    (prod / "templates" / "arlo_teleport_intro" / "canonical_registry.json").write_text(
        json.dumps(registry), encoding="utf-8",
    )

    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))

    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_24",
                                "intro_beat_role": "semi_canonical_transition_prompt",
                                "speaker": "Arlo",
                                "dialogue_text": "Alright Kiddo. test.",
                            },
                            {
                                "beat_id": "bg_arc1_event2_pre_beat_25",
                                "intro_beat_role": "canonical_mirror_video",
                                "speaker": "Arlo",
                            },
                        ],
                    },
                },
            },
        },
    }
    bg._migrate_sidecar(sidecar)
    beats = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    semi = beats[0]
    mirror = beats[1]
    assert semi["bg_ref_image"]["abs_path"] == str(studio_bg.resolve())
    assert mirror["kling_o3_video_path"] == str(tail.resolve())
    assert mirror["kling_o3_status"] == "approved"
    assert mirror.get("canonical_intro_tail") is True
    assert "Arlo" in (mirror.get("kling_o3_prompt") or "")
