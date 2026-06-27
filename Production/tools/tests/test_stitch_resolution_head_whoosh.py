"""Resolution head whoosh + phase B boundary outgoing fade — category fixes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from credentials_lib import ffmpeg_stitch as fs  # noqa: E402


def test_resolution_head_is_whoosh_not_after_win() -> None:
    from server_handlers import stitch_editor as se

    assert se.STITCH_RESOLUTION_HEAD_WHOOSH_V1
    assert se.STITCH_RESOLUTION_HEAD_SFX_FILENAME == se.STITCH_INTRO_DEFAULT_WHOOSH_FILENAME
    assert se.STITCH_RESOLUTION_HEAD_SFX_PLAY_MS == se.STITCH_INTRO_DEFAULT_WHOOSH_PLAY_MS


def test_strip_stale_after_win_head_cue() -> None:
    from server_handlers.stitch_editor import strip_stale_resolution_head_sfx_cues

    slots = {
        "resolution": {
            "video_path": "Production/Event_1/resolution.mp4",
            "sfx_cues": [
                {
                    "name": "after_win_return_to_map_music.mp3",
                    "auto_default": True,
                    "offset_ms": 0,
                },
                {
                    "name": "exit resolution video sfx.mp3",
                    "auto_default": True,
                    "offset_ms": 9000,
                },
            ],
        },
    }
    assert strip_stale_resolution_head_sfx_cues(slots) is True
    assert len(slots["resolution"]["sfx_cues"]) == 1
    assert "exit resolution" in slots["resolution"]["sfx_cues"][0]["name"].lower()


def test_resolution_head_whoosh_cue_materialized() -> None:
    from server_handlers.stitch_editor import ensure_stitch_slot_canonical_default_sfx_cues

    h = MagicMock()
    h._ffprobe_duration_ms.side_effect = lambda p: {
        "whoosh sound.mp3": 3104,
        "exit resolution video sfx.mp3": 5180,
    }.get(Path(p).name, 49700)
    slot = {"video_path": "Production/Event_1/resolution.mp4", "video_dur_ms": 49700}
    whoosh = "/proj/whoosh sound.mp3"
    tail = "/proj/Production/assets/sound_library/sfx/exit resolution video sfx.mp3"

    def _resolve(_h, _slot_key, filename):
        if "whoosh" in filename:
            return whoosh
        if "exit resolution" in filename:
            return tail
        return None

    with __import__("unittest").mock.patch(
        "server_handlers.stitch_editor._resolve_stitch_slot_tail_sfx_path",
        side_effect=_resolve,
    ):
        assert ensure_stitch_slot_canonical_default_sfx_cues(h, "resolution", slot)

    head = next(c for c in slot["sfx_cues"] if "whoosh" in c["name"].lower())
    assert head["offset_ms"] == 0
    assert head["duration_ms"] == 3104
    assert head.get("auto_default")


def test_phase_b_boundary_zero_outgoing_visual_fade() -> None:
    from server_handlers.stitch_editor import (
        STITCH_PHASE_B_TO_RESOLUTION_PAIR_INDEX,
        module_boundary_visual_out_ms_by_pair,
    )

    by_pair = module_boundary_visual_out_ms_by_pair(3, 600)
    assert by_pair[STITCH_PHASE_B_TO_RESOLUTION_PAIR_INDEX] == 0
    assert by_pair[0] == 600
    assert by_pair[1] == 600

    out_ms, in_ms, black_ms = fs.allocate_pair_fade_budget(2800, visual_out_ms=0, visual_in_ms=600)
    assert out_ms == 0
    assert in_ms == 600
    assert black_ms == 2200


def test_expand_clips_honors_per_pair_visual_out(tmp_path: Path) -> None:
    clips = []
    for i in range(2):
        p = tmp_path / f"clip_{i}.mp4"
        fs.render_black_pause_clip(2.0, p)
        clips.append(p)
    out = fs.expand_clips_with_black_pause_boundaries(
        clips,
        [2800],
        tmp_path / "scratch",
        visual_out_ms=600,
        visual_in_ms=600,
        visual_out_ms_by_pair=[0],
        fade_audio=False,
    )
    assert len(out) == 3
    assert out[0].name == "clip_0.mp4"
    assert any(p.name.startswith("black_pause_body_") and "fo0.000" in p.name for p in out)
