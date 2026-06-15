"""Regression: authored Transition-to-Spell beats must survive canonical tail cleanup."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import beat_generator as bg  # noqa: E402


def _authored_transition_beat(beat_id: str, dialogue: str) -> dict:
    return {
        "beat_id": beat_id,
        "speaker": "Tessa",
        "dialogue_text": dialogue,
        "scene_notes": "Transition to Spell",
        "kling_o3_status": "approved",
        "kling_o3_video_path": f"/tmp/{beat_id}.mp4",
    }


def _populated_mirror_beat() -> dict:
    return {
        "beat_id": "bg_arc1_event1_pre_beat_11",
        "intro_beat_role": bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR,
        "scene_notes": "Teleport mirror",
        "dialogue_text": "Ready? Teleport Glass…",
        "kling_o3_status": "approved",
        "kling_o3_video_path": "/tmp/canonical_mirror.mp4",
    }


def test_authored_transition_beats_not_superseded() -> None:
    for bid, dlg in (
        ("bg_arc1_event1_pre_beat_08", "Do you think she can really do it?"),
        ("bg_arc1_event1_pre_beat_09", "Well, I know some super smart people…"),
        ("bg_arc1_event1_pre_beat_10", "Alright Kiddo. I bet the Great Wizard…"),
    ):
        beat = _authored_transition_beat(bid, dlg)
        assert not bg.is_superseded_intro_tail_beat(beat)


def test_legacy_placeholder_transition_still_superseded() -> None:
    legacy = {
        "beat_id": "bg_arc1_event1_pre_beat_99",
        "dialogue_text": bg.INTRO_DIALOGUE_PLACEHOLDER,
        "scene_notes": "Transition to Spell",
    }
    assert bg.is_superseded_intro_tail_beat(legacy)


def test_append_intro_canonical_tail_keeps_authored_transition_beats(
    monkeypatch,
) -> None:
    """When mirror tail exists, beats 08–10 must not be dropped from sidecar list."""
    beats = [
        {"beat_id": "bg_arc1_event1_pre_beat_07", "scene_notes": "Introduction",
         "dialogue_text": "Want us to use magic to fix your shell?"},
        _authored_transition_beat("bg_arc1_event1_pre_beat_08", "Do you think…"),
        _authored_transition_beat("bg_arc1_event1_pre_beat_09", "Well, I know…"),
        _authored_transition_beat("bg_arc1_event1_pre_beat_10", "Alright Kiddo…"),
        copy.deepcopy(_populated_mirror_beat()),
    ]
    before_ids = [b["beat_id"] for b in beats]

    monkeypatch.setattr(
        bg,
        "_load_intro_canonical_beats_manifest",
        lambda: {"canonical_mirror_video": {"prompt": "mirror prompt"}},
    )
    monkeypatch.setattr(
        bg,
        "_has_populated_intro_mirror_beat",
        lambda b: b.get("intro_beat_role") == bg.INTRO_BEAT_ROLE_CANONICAL_MIRROR
        and bool(b.get("kling_o3_video_path")),
    )

    bg.append_intro_canonical_tail_beats(beats, "arc1_event1_pre", "pre")
    after_ids = [b["beat_id"] for b in beats]
    assert after_ids == before_ids
