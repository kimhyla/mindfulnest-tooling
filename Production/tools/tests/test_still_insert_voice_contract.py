"""Still+TTS voice contract — registry profile + canonical Lorelai delivery."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import beat_generator as bg


EVENT3_BEAT6_PROMPT = (
    'Loral speaks as if reading, she says:  "Let .... the.... flowers... bloom"'
)


def test_lorelai_still_profile_uses_character_subjects_speed_not_directus_luna():
    profile = bg.resolve_still_insert_elevenlabs_profile("Loral")
    assert profile is not None
    assert profile["voice_id"] == "PoHUWWWMHFrA8z7Q88pu"
    assert profile["source"] == "character_subjects"
    assert profile.get("speed") == 0.93


def test_event3_flowers_prompt_uses_canonical_delivery_not_she_says():
    beat = {
        "kling_o3_prompt_still": EVENT3_BEAT6_PROMPT,
        "kling_o3_prompt": EVENT3_BEAT6_PROMPT,
        "dialogue_text": "Let . the. flowers. bloom",
        "speaker": "Character",
        "pipeline": "still_insert",
    }
    parsed = bg.extract_still_insert_tts(beat)
    assert parsed is not None
    assert parsed["speaker"] == "Lorelai"
    assert "she says" not in parsed["tts_text"].lower()
    assert "warm excited conversational pace" in parsed["tts_text"]
    assert "scholarly" in parsed["tts_text"]


def test_prose_delivery_untrusted_detects_she_says_and_whisper():
    assert bg._still_insert_prose_delivery_is_untrusted(["speaks as if reading", "she says"])
    assert bg._still_insert_prose_delivery_is_untrusted(["in an awed whisper"])
    assert not bg._still_insert_prose_delivery_is_untrusted(["muttering", "lost"])


def test_ensure_still_insert_tts_passes_registry_voice_profile(monkeypatch) -> None:
    import server_handlers.background as bg_handler

    beat = {
        "beat_id": "bg_arc1_event3_pre_beat_06",
        "kling_o3_prompt_still": EVENT3_BEAT6_PROMPT,
        "speaker": "Character",
        "pipeline": "still_insert",
    }
    tts_info = bg.extract_still_insert_tts(beat)
    assert tts_info

    captured: dict = {}

    def _fake_regen(_app, _beat_id, text, _key, **kwargs):
        captured["text"] = text
        captured["voice_profile"] = kwargs.get("voice_profile_override")
        return {"ok": True, "audio_file": "line_06_lorelai.mp3"}

    monkeypatch.setattr("tools.production_server._tts_regenerate_for_beat", _fake_regen)
    monkeypatch.setattr(bg_handler, "_load_elevenlabs_key", lambda: "test-key")
    monkeypatch.setattr(
        bg,
        "storyboard_beat_id_for_bg_beat",
        lambda *a, **k: "beat_06",
    )
    monkeypatch.setattr(bg, "resolve_bg_beat_tts_audio_path", lambda *a, **k: None)

    h = MagicMock()
    h.app.event_dir = "/tmp/Event_3"
    result = bg_handler._ensure_still_insert_tts(h, beat, {}, {}, "intro")
    assert result["ok"] is True
    assert beat["speaker"] == "Lorelai"
    assert captured["voice_profile"]["speed"] == 0.93
    assert captured["voice_profile"]["voice_id"] == "PoHUWWWMHFrA8z7Q88pu"
    assert "scholarly" in captured["text"]
