"""STITCH_MODULE_PIPELINE_V1 + STITCH_SLOT_PREVIEW_V1 — scope gate durability."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from server_handlers import stitch_editor as se  # noqa: E402


def test_scope_constants_in_stitch_editor() -> None:
    assert se.STITCH_MODULE_PIPELINE_V1
    assert se.STITCH_SLOT_PREVIEW_V1
    assert se.STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1


def test_tag_stitch_pipeline_scope_single_slot_is_preview() -> None:
    body = {"slots": [{"video_path": "Production/Event_1/a.mp4"}]}
    se.tag_stitch_pipeline_scope(body)
    assert body["slot_preview"] is True
    assert body["module_pipeline"] is False


def test_tag_stitch_pipeline_scope_multi_slot_is_module() -> None:
    body = {
        "slots": [
            {"video_path": "Production/Event_1/intro.mp4"},
            {"video_path": "Production/Event_1/phase_a.mp4"},
        ],
    }
    se.tag_stitch_pipeline_scope(body)
    assert body["slot_preview"] is False
    assert body["module_pipeline"] is True


def test_resolution_finale_gated_off_for_slot_preview() -> None:
    body = {"slot_preview": True, "module_pipeline": False, "slots": [{}]}
    assert se.stitch_pipeline_should_apply_resolution_finale(body) is False


def test_resolution_finale_on_for_full_module() -> None:
    body = {
        "slot_preview": False,
        "module_pipeline": True,
        "slots": [{}, {}, {}, {}],
    }
    assert se.stitch_pipeline_should_apply_resolution_finale(body) is True


def test_milestone_finale_gated_off_for_slot_preview() -> None:
    body = {
        "slot_preview": True,
        "module_pipeline": False,
        "name": "milestone_milestone1_arc1_stitch",
        "slots": [{}],
    }
    assert se.stitch_pipeline_should_apply_milestone_finale(body) is False


def test_milestone_finale_on_for_standalone_bake() -> None:
    body = {
        "slot_preview": False,
        "module_pipeline": True,
        "name": "milestone_milestone1_arc1_stitch",
        "slots": [{}],
    }
    assert se.stitch_pipeline_should_apply_milestone_finale(body) is True


def test_milestone_finale_off_for_event_single_slot_bake() -> None:
    body = {
        "slot_preview": False,
        "module_pipeline": True,
        "name": "Event_2_stitch",
        "slots": [{}],
    }
    assert se.stitch_pipeline_should_apply_milestone_finale(body) is False


def test_resolution_finale_off_for_milestone_even_with_four_slots() -> None:
    body = {
        "slot_preview": False,
        "module_pipeline": True,
        "name": "milestone_milestone1_arc1_stitch",
        "slots": [{}, {}, {}, {}],
    }
    assert se.stitch_pipeline_should_apply_resolution_finale(body) is False
    assert se.stitch_pipeline_should_apply_milestone_finale(body) is False


def test_module_boundaries_gated_off_for_slot_preview() -> None:
    body = {"slot_preview": True, "module_pipeline": False, "slots": [{}, {}]}
    assert se.stitch_pipeline_apply_module_boundaries(body) is False


def test_module_boundaries_on_for_two_slot_module() -> None:
    body = {
        "slot_preview": False,
        "module_pipeline": True,
        "slots": [{}, {}],
    }
    assert se.stitch_pipeline_apply_module_boundaries(body) is True


def test_coerce_dict_slots_to_list_for_slot_preview() -> None:
    slot = {"video_path": "Production/Event_2/x.mp4", "sfx_cues": []}
    body = {
        "name": "milestone_milestone1_arc1_stitch",
        "slot": "standalone",
        "slot_preview": True,
        "slots": {"standalone": slot},
    }
    se._coerce_stitch_pipeline_slots_to_list(body)
    assert body["slots"] == [slot]


def test_coerce_dict_slots_to_ordered_list_for_module_pipeline() -> None:
    intro = {"video_path": "Production/Event_1/intro.mp4"}
    phase_a = {"video_path": "Production/Event_1/phase_a.mp4"}
    body = {
        "name": "module1_stitch",
        "slot_preview": False,
        "module_pipeline": True,
        "slots": {"phase_a": phase_a, "intro": intro},
    }
    se._coerce_stitch_pipeline_slots_to_list(body)
    assert body["slots"] == [intro, phase_a]


def test_pipeline_source_gates_resolution_finale() -> None:
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    assert "stitch_pipeline_should_apply_resolution_finale" in src
    assert "stitch_pipeline_should_apply_milestone_finale" in src
    assert "stitch_pipeline_apply_module_boundaries" in src
    block = src.split("def _stitch_build_pipeline", 1)[1].split("\n    def ", 1)[0]
    assert "if stitch_pipeline_should_apply_resolution_finale(body):" in block
    assert "elif stitch_pipeline_should_apply_milestone_finale(body):" in block
    assert "if stitch_pipeline_apply_module_boundaries(body):" in block


def test_preview_handler_tags_scope_and_validates_playable() -> None:
    src = (TOOLS / "server_handlers" / "stitch_editor.py").read_text(encoding="utf-8")
    preview = src.split("def handle_stitch_preview", 1)[1].split("\ndef ", 1)[0]
    assert "tag_stitch_pipeline_scope(hydrated)" in preview
    assert "stitch_cached_mp4_playable(out_path" in preview
    assert "video_playable" in preview


def test_stitch_cached_mp4_playable_rejects_missing_video_stream(tmp_path: Path) -> None:
    """Audio-only or corrupt cache must fail stitch_cached_mp4_playable."""
    import subprocess

    audio_only = tmp_path / "audio_only.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", "1",
            "-c:a", "aac",
            str(audio_only),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert se.stitch_cached_mp4_playable(audio_only) is False


def test_stitcher_composer_loading_and_error_ui() -> None:
    src = (TOOLS / "storyboard-v2" / "src" / "components" / "StitcherTab.tsx").read_text(
        encoding="utf-8",
    )
    assert "stitcher-composer-video-loading" in src
    assert "stitcher-composer-video-error" in src
    assert "composerVideoLoading" in src
    assert "onPoolSlotCanPlay" in src
    assert "slot_preview: true" in src
    assert "STITCH_COMPOSER_DRY_PLAYBACK_V1" in src
    assert "muxPreviewFailed" not in src


def test_stitch_mix_slot_audio_computes_duration_before_cache_validation() -> None:
    """slot_dur_s must exist before stitch_cached_mp4_playable cache hit check."""
    src = (TOOLS / "production_server.py").read_text(encoding="utf-8")
    block = src.split("def _stitch_mix_slot_audio", 1)[1].split("\n    def ", 1)[0]
    dur_idx = block.index("slot_dur_s = slot_dur_ms / 1000.0")
    playable_idx = block.index("stitch_cached_mp4_playable(out_path, expected_s=slot_dur_s)")
    assert dur_idx < playable_idx, "slot_dur_s must be assigned before cache decode validation"
