"""Canonical intro mirror export trim — WYSIWYG baked tail (hold in compose, not export)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def _fixture_prod(tmp_path: Path, *, export_trim: float = 0.0) -> Path:
    prod = tmp_path / "Production"
    tail = prod / "templates" / "arlo_teleport_intro" / "canonical" / "variant_0" / "intro_tail.mp4"
    tail.parent.mkdir(parents=True)
    tail.write_bytes(b"mp4")
    manifest = {
        "guide": "Arlo",
        "intro_canonical_beats": {
            "canonical_tail_export_trim_back_s": export_trim,
            "canonical_mirror_video": {"speaker": "Arlo", "dialogue_text": "Ready?"},
        },
    }
    (prod / "templates" / "arlo_teleport_intro" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    return prod


def test_wysiwyg_tail_does_not_seed_export_trim(tmp_path: Path, monkeypatch) -> None:
    prod = _fixture_prod(tmp_path, export_trim=0.0)
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_25",
        "intro_beat_role": bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR,
        "canonical_intro_tail": True,
        "kling_o3_video_path": str(
            (prod / "templates/arlo_teleport_intro/canonical/variant_0/intro_tail.mp4").resolve(),
        ),
        "kling_o3_status": "approved",
    }
    assert bg.seed_canonical_intro_tail_export_trim(beat) is False
    assert "kling_o3_trim_back" not in beat


def test_wysiwyg_clears_legacy_export_trim(tmp_path: Path, monkeypatch) -> None:
    prod = _fixture_prod(tmp_path, export_trim=0.0)
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    beat = {
        "intro_beat_role": bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR,
        "canonical_intro_tail": True,
        "kling_o3_trim_back": 4.0,
        "kling_o3_video_path": str(
            (prod / "templates/arlo_teleport_intro/canonical/variant_0/intro_tail.mp4").resolve(),
        ),
    }
    assert bg.seed_canonical_intro_tail_export_trim(beat) is True
    assert "kling_o3_trim_back" not in beat


def test_legacy_manifest_still_seeds_export_trim(tmp_path: Path, monkeypatch) -> None:
    prod = _fixture_prod(tmp_path, export_trim=4.0)
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    beat = {
        "intro_beat_role": bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR,
        "canonical_intro_tail": True,
        "kling_o3_video_path": str(
            (prod / "templates/arlo_teleport_intro/canonical/variant_0/intro_tail.mp4").resolve(),
        ),
    }
    assert bg.seed_canonical_intro_tail_export_trim(beat) is True
    assert beat["kling_o3_trim_back"] == 4.0


def test_migrate_clears_legacy_trim_when_wysiwyg(tmp_path: Path, monkeypatch) -> None:
    prod = _fixture_prod(tmp_path, export_trim=0.0)
    monkeypatch.setenv("MN_DROPBOX_ROOT", str(tmp_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))
    tail = str(
        (prod / "templates/arlo_teleport_intro/canonical/variant_0/intro_tail.mp4").resolve(),
    )
    sidecar = {
        "schema_version": 3,
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [{
                            "beat_id": "bg_arc1_event2_pre_beat_25",
                            "intro_beat_role": bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR,
                            "canonical_intro_tail": True,
                            "kling_o3_video_path": tail,
                            "kling_o3_trim_back": 4.0,
                            "kling_o3_prompt": "locked prompt with voice line",
                            "kling_o3_status": "approved",
                        }],
                    },
                },
            },
        },
    }
    bg._migrate_sidecar(sidecar, heal_trim=True, heavy_heal=True)
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert "kling_o3_trim_back" not in beat
