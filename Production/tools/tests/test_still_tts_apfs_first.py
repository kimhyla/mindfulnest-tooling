"""Still+TTS must write APFS first and not stack ElevenLabs on one beat."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import beat_generator as bg
import kling_startend_pipeline as ksp
import media_hot_root as mhr


def test_robust_https_wall_clock_timeout_closes_hung_handshake(monkeypatch) -> None:
    class HangConn:
        def __init__(self, *a, **k):
            pass

        def request(self, *a, **k):
            time.sleep(30)

        def getresponse(self):
            raise AssertionError("should not read after hang")

        def close(self):
            pass

    monkeypatch.setattr("http.client.HTTPSConnection", HangConn)
    t0 = time.time()
    try:
        ksp.robust_https_request("api.elevenlabs.io", "/v1/hang", timeout=1, max_retries=1)
        raise AssertionError("expected TimeoutError")
    except TimeoutError as exc:
        assert "wall-clock" in str(exc)
    assert time.time() - t0 < 6


def test_tts_regen_writes_hot_dir_skips_dropbox_state(tmp_path: Path, monkeypatch) -> None:
    import tools.production_server as ps

    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event_dir = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "Production" / "Event_6"
    )
    event_dir.mkdir(parents=True)
    assert mhr.event_dir_is_cloud_backed(event_dir)

    called = {"get_beats": 0, "mutate": 0}

    class _State:
        def get_beats(self, _role):
            called["get_beats"] += 1
            raise AssertionError("still-insert TTS must not read production_state")

        def mutate_video_state(self, _role, _fn):
            called["mutate"] += 1
            raise AssertionError("still-insert TTS must not mutate production_state")

    app = MagicMock()
    app.event_dir = event_dir
    app.storyboard_stem = "storyboard_v59_prod"
    app.state = _State()

    def _fake_https(*_a, **_k):
        return 200, b"ID3fake-mp3"

    monkeypatch.setattr("kling_startend_pipeline.robust_https_request", _fake_https)
    monkeypatch.setattr(ps, "_ffprobe_duration", lambda _p: 2.5)

    result = ps._tts_regenerate_for_beat(
        app,
        "bg_arc1_event6_post_beat_01",
        "[warm] hello nest",
        "test-key",
        video_role="resolution",
        speaker_override="Tessa",
        storyboard_beat_id="beat_01",
        voice_profile_override={"voice_id": "cgSgspJ2msm6clMCkdW9", "speed": 1.15},
        persist_production_state=False,
    )
    assert result["ok"] is True
    assert result["audio_file"] == "line_01_tessa.mp3"
    assert called["get_beats"] == 0
    assert called["mutate"] == 0
    hot_mp3 = (
        hot / "Event_6" / "story_scene_tts_v2" / "storyboard_v59_prod" / "line_01_tessa.mp3"
    )
    assert hot_mp3.is_file()
    assert hot_mp3.read_bytes() == b"ID3fake-mp3"
    dropbox_mp3 = event_dir / "story_scene_tts_v2" / "storyboard_v59_prod" / "line_01_tessa.mp3"
    # Dropbox copy is best-effort background — must not be required for ok.
    assert result["ok"] is True
    beat = {"beat_id": "bg_arc1_event6_post_beat_01", "audio_file": "line_01_tessa.mp3"}
    found = bg.resolve_bg_beat_tts_audio_path(
        event_dir, beat, sidecar={}, production_state={}, video_role="resolution",
    )
    assert found is not None
    assert found.resolve() == hot_mp3.resolve()


def test_tts_regen_invalid_api_key_is_logged_and_friendly(tmp_path: Path, monkeypatch) -> None:
    import tools.production_server as ps

    app = MagicMock()
    app.event_dir = tmp_path / "Event_6"
    app.event_dir.mkdir()
    app.storyboard_stem = ""
    app.state = MagicMock()

    body = (
        b'{"detail":{"type":"authentication_error","code":"invalid_api_key",'
        b'"message":"API key ID used as API key - only valid API keys can be used."}}'
    )
    monkeypatch.setattr(
        "kling_startend_pipeline.robust_https_request",
        lambda **_k: (400, body),
    )
    result = ps._tts_regenerate_for_beat(
        app,
        "bg_arc1_event6_post_beat_01",
        "hello",
        "not-a-real-key",
        video_role="resolution",
        speaker_override="Tessa",
        storyboard_beat_id="beat_01",
        voice_profile_override={"voice_id": "cgSgspJ2msm6clMCkdW9"},
        persist_production_state=False,
    )
    assert result["ok"] is False
    assert "sk_" in result["error"]
    assert "key ID" in result["error"]


def test_resolve_still_tts_prefers_hot_over_missing_dropbox(tmp_path: Path, monkeypatch) -> None:
    hot = tmp_path / "hot"
    monkeypatch.setenv("MN_MEDIA_HOT_ROOT", str(hot))
    event_dir = (
        tmp_path / "Library" / "CloudStorage" / "Dropbox" / "Production" / "Event_6"
    )
    event_dir.mkdir(parents=True)
    dest = mhr.still_tts_hot_dir(event_dir, "storyboard_v59_prod")
    mp3 = dest / "line_01_tessa.mp3"
    mp3.write_bytes(b"hot")
    beat = {
        "beat_id": "bg_arc1_event6_post_beat_01",
        "storyboard_beat_id": "beat_01",
        "audio_file": "line_01_tessa.mp3",
    }
    found = bg.resolve_bg_beat_tts_audio_path(event_dir, beat)
    assert found == mp3.resolve()
