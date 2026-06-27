"""Still-insert TTS delivery → ElevenLabs v3 tag contract."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import beat_generator as bg


def test_ensure_still_insert_tts_sends_delivery_payload(monkeypatch) -> None:
    import server_handlers.background as bg_handler

    beat = {
        "beat_id": "bg_arc1_event2_post_beat_02",
        "kling_o3_prompt": (
            'Loral whispers, in an awed whisper, disbelieving, awed, incredulous, whispering:  '
            '"No way ... Is it happening again?"'
        ),
        "speaker": "Lorelai",
        "still_tts_source_text": '"No way . is it happening again?',
    }
    tts_info = bg.extract_still_insert_tts(beat)
    assert tts_info
    assert tts_info["tts_text"].startswith("[")

    captured: dict = {}

    def _fake_regen(_app, _beat_id, text, _key, **kwargs):
        captured["text"] = text
        return {"ok": True, "audio_file": "line_02_lorelai.mp3"}

    monkeypatch.setattr("tools.production_server._tts_regenerate_for_beat", _fake_regen)
    monkeypatch.setattr(bg_handler, "_load_elevenlabs_key", lambda: "test-key")
    monkeypatch.setattr(
        bg,
        "storyboard_beat_id_for_bg_beat",
        lambda *a, **k: "beat_02",
    )
    monkeypatch.setattr(
        bg,
        "resolve_bg_beat_tts_audio_path",
        lambda *a, **k: None,
    )

    h = MagicMock()
    h.app.event_dir = "/tmp/Event_2"
    result = bg_handler._ensure_still_insert_tts(h, beat, {}, {}, "resolution")
    assert result["ok"] is True
    assert captured["text"] == tts_info["tts_text"]
    assert beat["still_tts_source_text"] == tts_info["fingerprint"]


def test_ensure_still_insert_tts_skips_when_fingerprint_unchanged(monkeypatch, tmp_path) -> None:
    import server_handlers.background as bg_handler

    beat = {
        "beat_id": "bg_arc1_event2_post_beat_02",
        "kling_o3_prompt": '[whispering]: "Hello there"',
        "speaker": "Lorelai",
    }
    tts_info = bg.extract_still_insert_tts(beat)
    assert tts_info
    beat["still_tts_source_text"] = tts_info["fingerprint"]
    mp3 = tmp_path / "line_02_lorelai.mp3"
    mp3.write_bytes(b"mp3")

    monkeypatch.setattr(bg, "resolve_bg_beat_tts_audio_path", lambda *a, **k: mp3)
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not call ElevenLabs when fingerprint unchanged")

    monkeypatch.setattr("tools.production_server._tts_regenerate_for_beat", _boom)

    h = MagicMock()
    h.app.event_dir = str(tmp_path)
    result = bg_handler._ensure_still_insert_tts(h, beat, {}, {}, "resolution")
    assert result.get("unchanged") is True
    assert called["n"] == 0
