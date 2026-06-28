"""Intro canonical mirror must hydrate on write paths — not migrate-only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def _fixture_prod(tmp_path: Path) -> Path:
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
        },
        "intro_canonical_beats": {
            "canonical_mirror_video": {
                "speaker": "Arlo",
                "dialogue_text": "Ready?",
                "prompt": "@Image1 Arlo speaks",
                "char_ref_asset": "mirror_char",
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
    return prod


def test_apply_approved_extract_plan_hydrates_mirror_tail(tmp_path: Path, monkeypatch):
    prod = _fixture_prod(tmp_path)
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))

    sidecar: dict = {"arcs": {}}
    beats_plan = [{
        "beat_index": 1,
        "beat_type": "dialogue",
        "speaker": "Tessa",
        "dialogue_text": "Hello",
        "emotion": "neutral",
        "scene_notes": "",
    }]
    prompts = {1: "@Image1 (Tessa) test prompt with voice line"}

    merged = bg.apply_approved_extract_plan(
        sidecar, 1, "4", "pre", "summary", beats_plan, prompts,
    )
    mirror = next(b for b in merged if b.get("intro_beat_role") == "canonical_mirror_video")
    assert mirror["kling_o3_video_path"] == str(
        (prod / "templates" / "arlo_teleport_intro" / "canonical" / "variant_0" / "intro_tail.mp4").resolve()
    )
    assert mirror["kling_o3_status"] == "approved"
    opts = mirror.get("kling_o3_options") or []
    assert any(o.get("source") == "canonical_intro_tail" for o in opts)


def test_hydrate_repairs_video_without_option_slot(tmp_path: Path, monkeypatch):
    prod = _fixture_prod(tmp_path)
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    tail = prod / "templates" / "arlo_teleport_intro" / "canonical" / "variant_0" / "intro_tail.mp4"
    beat = {
        "beat_id": "bg_arc1_event4_pre_beat_16",
        "intro_beat_role": "canonical_mirror_video",
        "speaker": "Arlo",
        "kling_o3_video_path": str(tail.resolve()),
        "kling_o3_status": "approved",
        "kling_o3_options": [],
    }
    assert bg.hydrate_intro_canonical_mirror_beat(beat, "4", "pre") is True
    assert any(o.get("source") == "canonical_intro_tail" for o in (beat.get("kling_o3_options") or []))
