"""VIDEO_ROLE_BG_SWITCH_V1 — preserve outgoing segment + sync sidecar on video set_active."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def bg_sidecar(tmp_path: Path, monkeypatch):
    """Minimal sidecar with intro (pre) and resolution (post) segments."""
    prod = tmp_path / "Production"
    prod.mkdir()
    event_dir = tmp_path / "Production" / "Event_1"
    event_dir.mkdir()
    clips = event_dir / "kling_o3_clips"
    clips.mkdir()

    sidecar = {
        "active_context": {"arc_number": 1, "event_id": "1", "phase": "pre"},
        "arcs": {
            "arc_1": {
                "segments": {
                    "event_1_pre": {
                        "beats": [
                            {
                                "beat_id": "bg_arc1_event1_pre_beat_01",
                                "pipeline": "kling_o3_omni",
                                "kling_o3_video_path": str(clips / "bg_arc1_event1_pre_beat_01.mp4"),
                                "kling_o3_status": "approved",
                            },
                        ],
                    },
                    "event_1_post": {
                        "beats": [
                            {"beat_id": "bg_arc1_event1_post_beat_01", "pipeline": "kling_o3_omni"},
                        ],
                    },
                },
            },
        },
    }
    clip = clips / "bg_arc1_event1_pre_beat_01.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00" + b"\x00" * 64)

    sidecar_path = prod / "beat_generator_state.json"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

    import beat_generator as bg

    monkeypatch.setattr(bg, "BG_SIDECAR_PATH", str(sidecar_path))
    monkeypatch.setattr(bg, "_PROD_DIR", str(prod))

    app = SimpleNamespace(event_id="Event_1", event_dir=str(event_dir))
    state = MagicMock()
    state.read_state.return_value = {"active_video": "intro", "videos": {"intro": {}, "resolution": {}}}
    state.validate_video_role.return_value = True
    state.mutate_state = MagicMock(side_effect=lambda fn: fn({"active_video": "intro"}))

    h = SimpleNamespace(
        app=SimpleNamespace(state=state, event_id="Event_1", event_dir=str(event_dir)),
    )
    h._scope_body = lambda body: {"scope_event_id": "Event_1", **(body or {})}
    h._assert_event_scope = lambda *_a, **_k: True
    h._send_json = MagicMock()

    return h, sidecar_path, event_dir


def test_switch_bg_context_preserves_outgoing_and_syncs_target(bg_sidecar):
    h, sidecar_path, event_dir = bg_sidecar
    from server_handlers.background import switch_bg_context_for_video_role

    result = switch_bg_context_for_video_role(h, "Event_1", "intro", "resolution")

    assert result["scope_active_context"]["phase"] == "post"
    assert result["had_saved"] is True
    assert result["outgoing"]["beat_count"] == 1
    assert result["outgoing"]["preserved_clip_count"] == 1

    preserve_dir = (
        event_dir
        / "kling_o3_clips"
        / "_preserved"
        / "segments"
        / "arc1_event1_pre"
    )
    assert (preserve_dir / "manifest.json").is_file()
    manifest = json.loads((preserve_dir / "manifest.json").read_text())
    assert manifest["beat_count"] == 1

    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar["active_context"]["phase"] == "post"


def test_intro_switch_invokes_canonical_tail_seed(bg_sidecar, monkeypatch):
    h, _sidecar_path, _event_dir = bg_sidecar
    import beat_generator as bg_mod
    from server_handlers.background import switch_bg_context_for_video_role

    calls: list[tuple[str, str]] = []
    orig = bg_mod.append_intro_canonical_tail_beats

    def _spy(beats, beat_label, phase):
        calls.append((beat_label, phase))
        return orig(beats, beat_label, phase)

    monkeypatch.setattr(bg_mod, "append_intro_canonical_tail_beats", _spy)

    switch_bg_context_for_video_role(h, "Event_1", "intro", "resolution")
    result = switch_bg_context_for_video_role(h, "Event_1", "resolution", "intro")

    assert result["scope_active_context"]["phase"] == "pre"
    assert any(label.startswith("arc1_event1_pre") and phase == "pre" for label, phase in calls)
