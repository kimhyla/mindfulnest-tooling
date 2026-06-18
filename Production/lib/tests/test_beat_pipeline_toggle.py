"""Per-beat Still+TTS ↔ O3 Kling pipeline toggle — classification + mode switch."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def _dialogue_beat(**overrides) -> dict:
    beat = {
        "beat_id": "bg_arc1_event2_pre_beat_01",
        "speaker": "Arlo",
        "dialogue_text": 'Arlo [warm]: "Hello there."',
        "scene_notes": "Chipper waves from the porch.",
        "emotion": "warm",
        "status": "draft",
        "pipeline": "kling_o3_omni",
        "beat_type": "dialogue",
    }
    beat.update(overrides)
    return beat


def test_classify_legacy_still_beat_sets_both_pipeline_fields():
    beat = _dialogue_beat(beat_render_mode="still_insert", pipeline=None)
    assert bg.classify_beat_pipeline_fields(beat) is True
    assert beat["pipeline"] == bg.PIPELINE_MODE_STILL
    assert beat["beat_render_mode"] == bg.PIPELINE_MODE_STILL
    assert beat["beat_type"] == "stage_still"


def test_classify_dialogue_beat_defaults_to_o3():
    beat = _dialogue_beat(pipeline=None)
    beat.pop("beat_render_mode", None)
    assert bg.classify_beat_pipeline_fields(beat) is True
    assert beat["pipeline"] == bg.PIPELINE_MODE_O3
    assert "beat_render_mode" not in beat
    assert beat["beat_type"] == "dialogue"


def test_classify_all_sidecar_pipeline_fields():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [
                            _dialogue_beat(pipeline=None),
                            _dialogue_beat(
                                beat_id="bg_arc1_event2_pre_beat_02",
                                speaker="[Stage Direction]",
                                beat_type="stage_direction",
                                pipeline="still_insert",
                            ),
                        ],
                    },
                },
            },
        },
    }
    assert bg.classify_all_sidecar_pipeline_fields(sidecar) is True
    beats = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
    assert beats[0]["pipeline"] == bg.PIPELINE_MODE_O3
    assert beats[1].get("pipeline") != bg.PIPELINE_MODE_STILL


def test_set_beat_pipeline_still_to_o3_rebuilds_prompt():
    beat = _dialogue_beat(beat_render_mode="still_insert", pipeline="still_insert", beat_type="stage_still")
    changed = bg.set_beat_pipeline_mode(
        beat, bg.PIPELINE_MODE_O3, event_id="2", phase="pre",
    )
    assert changed is True
    assert beat["pipeline"] == bg.PIPELINE_MODE_O3
    assert "beat_render_mode" not in beat
    assert (beat.get("kling_o3_prompt") or "").strip()
    assert "STILL INSERT" not in (beat.get("kling_o3_prompt") or "")


def test_set_beat_pipeline_o3_to_still_builds_still_prompt():
    beat = _dialogue_beat()
    changed = bg.set_beat_pipeline_mode(
        beat, bg.PIPELINE_MODE_STILL, event_id="2", phase="pre",
    )
    assert changed is True
    assert beat["pipeline"] == bg.PIPELINE_MODE_STILL
    assert beat["beat_render_mode"] == bg.PIPELINE_MODE_STILL
    assert (beat.get("kling_o3_prompt") or "").startswith("STILL INSERT")


def test_set_beat_pipeline_blocks_stage_direction():
    beat = _dialogue_beat(speaker="[Stage Direction]", beat_type="stage_direction")
    try:
        bg.set_beat_pipeline_mode(
            beat, bg.PIPELINE_MODE_STILL, event_id="2", phase="pre",
        )
    except bg.PipelineToggleError as exc:
        assert exc.code == "STAGE_DIRECTION_BEAT"
    else:
        raise AssertionError("expected PipelineToggleError")


def test_set_beat_pipeline_blocks_canonical_mirror():
    beat = _dialogue_beat(intro_beat_role=bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR)
    try:
        bg.set_beat_pipeline_mode(
            beat, bg.PIPELINE_MODE_STILL, event_id="2", phase="pre",
        )
    except bg.PipelineToggleError as exc:
        assert exc.code == "CANONICAL_BEAT_PROTECTED"
    else:
        raise AssertionError("expected PipelineToggleError")


def test_production_server_registers_set_pipeline_route():
    server_path = TOOLS / "production_server.py"
    text = server_path.read_text(encoding="utf-8")
    assert "/api/bg/set-pipeline" in text
    assert "_handle_bg_set_pipeline" in text


def test_endpoints_catalog_includes_bg_set_pipeline():
    endpoints_path = TOOLS / "storyboard-v2" / "src" / "api" / "endpoints.ts"
    text = endpoints_path.read_text(encoding="utf-8")
    assert "bg_set_pipeline" in text
    assert "/api/bg/set-pipeline" in text


def test_bgtab_wires_pipeline_toggle():
    bgtab_path = TOOLS / "storyboard-v2" / "src" / "components" / "BgTab.tsx"
    text = bgtab_path.read_text(encoding="utf-8")
    assert "bg_set_pipeline" in text
    assert "bg-pipeline-toggle-" in text
    assert "Still + TTS" in text
    assert "Voice-first" in text
    assert "Element native" in text
    assert "generation_mode" in text


def test_set_beat_generation_mode_voice_first_persists_o3_mode():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [_dialogue_beat()],
                    },
                },
            },
        },
    }
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    changed = bg.set_beat_generation_mode(
        beat,
        bg.O3_GENERATE_MODE_ELEMENT_NATIVE,
        event_id="2",
        phase="pre",
        sidecar=sidecar,
    )
    assert changed is True
    assert beat["pipeline"] == bg.PIPELINE_MODE_O3
    assert beat["o3_generate_mode"] == bg.O3_GENERATE_MODE_ELEMENT_NATIVE
    assert bg.resolve_beat_generation_mode(beat, sidecar) == bg.O3_GENERATE_MODE_ELEMENT_NATIVE


def test_set_beat_generation_mode_still_clears_render_path():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [_dialogue_beat(o3_generate_mode="voice_first")],
                    },
                },
            },
        },
    }
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    changed = bg.set_beat_generation_mode(
        beat,
        bg.PIPELINE_MODE_STILL,
        event_id="2",
        phase="pre",
        sidecar=sidecar,
    )
    assert changed is True
    assert beat["pipeline"] == bg.PIPELINE_MODE_STILL
    assert bg.resolve_beat_generation_mode(beat, sidecar) == bg.PIPELINE_MODE_STILL


def test_resolve_beat_generation_mode_event2_default_voice_first():
    sidecar = {
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_2_pre": {
                        "beats": [_dialogue_beat()],
                    },
                },
            },
        },
    }
    beat = sidecar["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"][0]
    assert bg.resolve_beat_generation_mode(beat, sidecar) == bg.O3_GENERATE_MODE_VOICE_FIRST


def test_handle_bg_set_pipeline_accepts_generation_mode():
    bg_src = TOOLS / "server_handlers" / "background.py"
    text = bg_src.read_text(encoding="utf-8")
    assert "generation_mode" in text
    assert "set_beat_generation_mode" in text
    assert "o3_generate_mode" in text.split("handle_bg_set_pipeline", 1)[1].split("def handle_bg_render_still_clip", 1)[0]


def test_session_state_enriches_generation_mode():
    bg_src = TOOLS / "server_handlers" / "background.py"
    text = bg_src.read_text(encoding="utf-8")
    assert "enrich_beats_generation_mode" in text


def test_o3_generate_mode_in_sidecar_merge_preserve():
    assert "o3_generate_mode" in bg.SIDECAR_MERGE_PRESERVE_FIELDS
