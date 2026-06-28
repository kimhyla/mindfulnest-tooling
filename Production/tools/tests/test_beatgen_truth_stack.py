"""Beat Gen Truth Stack — scope gates, single writer, import API contract."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import beat_generator as bg
from lib.beatgen_store import BeatgenStore
from beatgen_scope import (
    BeatGenScopeError,
    BeatGenSingleWriterError,
    assert_db_path_matches_beat,
    build_event_production_scope,
    event_id_from_beat_id,
    http_import_delivery_clip,
    port_from_event_id,
    scope_from_env_json,
    scope_to_env_json,
    storyboard_url_for_beat,
)


def test_event_id_from_beat_id_production() -> None:
    assert event_id_from_beat_id("bg_arc1_event3_pre_beat_10") == "Event_3"
    assert event_id_from_beat_id("bg_arc1_event3b_full_beat_12") is None


def test_port_from_event_id_dedicated_rule() -> None:
    assert port_from_event_id("Event_3") == 5113


def test_event_dir_for_beat_id_raises_without_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bg, "_PROD_DIR", tmp_path)
    with pytest.raises(BeatGenScopeError):
        bg.event_dir_for_beat_id("bg_no_event_token")


def test_direct_write_blocked_for_production_beat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE", raising=False)
    monkeypatch.delenv("MN_BEATGEN_SERVER_WRITER", raising=False)
    monkeypatch.delenv("MN_BEATGEN_ALLOW_DIRECT_WRITE", raising=False)
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    db = tmp_path / "beatgen_event3.db"
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    BeatgenStore.reset_singleton_for_tests()
    bg.reset_bg_paths_activation_for_tests()
    bg.init_bg_paths(str(event_dir), clear_milestone_scope=True)
    beat_id = "bg_arc1_event3_pre_beat_10"

    def mutator(b: dict, _s: dict) -> None:
        b["status"] = "draft"

    with pytest.raises(BeatGenSingleWriterError):
        bg.update_beat_locked(beat_id, mutator)


def test_wrong_db_path_raises_for_event3_beat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MN_BEATGEN_TEST_ALLOW_DIRECT_WRITE", raising=False)
    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(tmp_path / "beatgen.db"))
    with pytest.raises(BeatGenScopeError):
        assert_db_path_matches_beat("bg_arc1_event3_pre_beat_10")


def test_import_delivery_clip_to_beat_still_insert_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_dir = tmp_path / "Event_3"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    db = tmp_path / "beatgen_event3.db"
    sidecar = event_dir / "beat_generator_sidecar.json"
    beat_id = "bg_arc1_event3_pre_beat_10"
    sidecar.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beats": [
                                    {
                                        "beat_id": beat_id,
                                        "pipeline": "still_insert",
                                        "beat_render_mode": "still_insert",
                                        "kling_o3_options": [],
                                    }
                                ],
                            },
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    delivery = tmp_path / "delivery.mp4"
    delivery.write_bytes(b"fake-mp4")

    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    monkeypatch.setenv("MN_BEATGEN_SERVER_WRITER", "1")
    BeatgenStore.reset_singleton_for_tests()
    bg.reset_bg_paths_activation_for_tests()
    bg.init_bg_paths(str(event_dir), clear_milestone_scope=True)
    sidecar_data = json.loads(sidecar.read_text())
    bg._beatgen_store().import_from_dict(sidecar_data, replace=True)
    scope = build_event_production_scope(event_dir)

    ok, beat = bg.import_delivery_clip_to_beat(
        beat_id=beat_id,
        delivery_mp4=delivery,
        slot_index=0,
        label="hand seeds motion",
        make_active=True,
        event_dir=event_dir,
        scope=scope,
    )
    assert ok and beat
    assert beat["kling_o3_status"] == "still_rendered"
    active_path = str(beat.get("kling_o3_video_path") or "")
    active_opt = next(
        (o for o in (beat.get("kling_o3_options") or []) if o.get("video_path") == active_path),
        None,
    )
    assert active_opt and active_opt.get("source") == "still_insert_kling_idle"
    assert "still_insert" in Path(active_path).name


def test_http_import_delivery_clip_posts_to_dedicated_port(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeResp:
        def read(self) -> bytes:
            return json.dumps({"ok": True, "beat_id": "bg_arc1_event3_pre_beat_10"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    http_import_delivery_clip(
        beat_id="bg_arc1_event3_pre_beat_10",
        delivery_mp4="/tmp/x.mp4",
        slot_index=0,
        label="test",
    )
    assert captured["url"] == "http://localhost:5113/api/bg/import-delivery-clip"
    assert captured["data"]["scope_event_id"] == "Event_3"


def test_handle_bg_import_delivery_clip_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from server_handlers.background import handle_bg_import_delivery_clip

    event_dir = tmp_path / "Event_3"
    clips = event_dir / "kling_o3_clips"
    clips.mkdir(parents=True)
    db = tmp_path / "beatgen_event3.db"
    sidecar = event_dir / "beat_generator_sidecar.json"
    beat_id = "bg_arc1_event3_pre_beat_10"
    sidecar.write_text(
        json.dumps(
            {
                "arcs": {
                    "arc_1": {
                        "segments": {
                            "event_3_pre": {
                                "beats": [
                                    {
                                        "beat_id": beat_id,
                                        "pipeline": "still_insert",
                                        "beat_render_mode": "still_insert",
                                        "kling_o3_options": [],
                                    }
                                ],
                            },
                        },
                    },
                },
            },
        ),
        encoding="utf-8",
    )
    delivery = tmp_path / "delivery.mp4"
    delivery.write_bytes(b"fake-mp4")

    monkeypatch.setenv("MN_BEATGEN_DB_PATH", str(db))
    monkeypatch.setenv("MN_SIDECAR_SQLITE_AUTHORITY", "1")
    monkeypatch.setenv("MN_BEATGEN_SERVER_WRITER", "1")
    BeatgenStore.reset_singleton_for_tests()
    bg.reset_bg_paths_activation_for_tests()
    bg.init_bg_paths(str(event_dir), clear_milestone_scope=True)

    sent: list = []

    h = MagicMock()
    h._assert_event_scope.return_value = True
    h._scope_body.return_value = {"scope_event_id": "Event_3"}
    h.app.event_dir = str(event_dir)
    h.app.scope_type = "event"
    h._o3_job_event_dir = lambda _bid: event_dir
    h._send_json = lambda status, payload: sent.append((status, payload))
    h._send_error_v59 = lambda *a, **k: sent.append(("error", a, k))

    monkeypatch.setattr(
        "server_handlers.background._o3_job_event_dir",
        lambda _h, _bid: event_dir,
    )

    handle_bg_import_delivery_clip(
        h,
        {
            "beat_id": beat_id,
            "delivery_mp4_path": str(delivery),
            "slot_index": 0,
            "label": "import test",
            "make_active": True,
            "scope_event_id": "Event_3",
        },
    )
    assert sent and sent[0][0] == 200
    assert sent[0][1]["ok"] is True
    assert sent[0][1]["beat"]["kling_o3_video_path"]


def test_storyboard_url_for_beat() -> None:
    assert storyboard_url_for_beat("bg_arc1_event3_pre_beat_10") == (
        "http://localhost:5113/?event=Event_3"
    )


def test_scope_env_json_roundtrip(tmp_path: Path) -> None:
    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()
    scope = build_event_production_scope(event_dir)
    restored = scope_from_env_json(scope_to_env_json(scope))
    assert restored is not None
    assert restored.kind == "event_production"
    assert restored.event_id == "Event_3"
    assert restored.db_path and restored.db_path.name == "beatgen_event3.db"


def test_scope_from_app_event_production(tmp_path: Path) -> None:
    from beatgen_scope import scope_from_app

    event_dir = tmp_path / "Event_3"
    event_dir.mkdir()

    root = event_dir

    class App:
        scope_type = "event"
        event_dir = root

    scope = scope_from_app(App())
    assert scope.kind == "event_production"
    assert scope.event_id == "Event_3"
    assert scope.db_path and scope.db_path.name == "beatgen_event3.db"
