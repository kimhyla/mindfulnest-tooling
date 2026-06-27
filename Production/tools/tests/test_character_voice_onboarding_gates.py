"""Gates: both voice layers required before WaveSpeed Element registration."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from kling_element_voice import (  # noqa: E402
    ARC1_SAMPLE_SOURCES,
    ELEVENLABS_VOICE_ROSTER,
    ensure_voice_sample,
)
from kling_o3_prompt import _DELIVERY_BY_SPEAKER, delivery_for_speaker  # noqa: E402
from kling_voice_sample_lock import (  # noqa: E402
    has_voice_onboarding_waiver,
    is_first_voice_registration,
    sample_lines_have_emotion_tags,
    validate_emotion_tags_in_sample_lines,
    validate_o3_delivery_lock,
    validate_roster_voice_onboarding_contract,
    validate_voice_onboarding_before_spend,
)


def _pending_cfg(**extra) -> dict:
    base = {
        "status": "pending",
        "element_id": None,
        "element_sample_lines": [
            "[warm, gentle] Hello there.",
            "[curious, friendly] How are you doing today?",
        ],
        "voice_sample_lock": {
            "locked_speed": 1.0,
            "element_sample_lines": [
                "[warm, gentle] Hello there.",
                "[curious, friendly] How are you doing today?",
            ],
            "audition_line": "Hello there.",
            "sample_text_fingerprint": "abc123",
        },
    }
    base.update(extra)
    return base


def test_sample_lines_have_emotion_tags():
    assert sample_lines_have_emotion_tags(["[warm, gentle] Hi."])
    assert not sample_lines_have_emotion_tags(["Hello there.", "[pause] wait"])
    assert not sample_lines_have_emotion_tags(["[pause] only performance tag"])


def test_validate_o3_delivery_lock_blocks_missing():
    errs = validate_o3_delivery_lock("TotallyNewChar")
    assert len(errs) == 1
    assert "no O3 delivery lock" in errs[0]


def test_validate_o3_delivery_lock_passes_ember():
    assert validate_o3_delivery_lock("Ember") == []


def test_validate_emotion_tags_blocks_plain_lines():
    cfg = {"element_sample_lines": ["Plain line with no tags."]}
    errs = validate_emotion_tags_in_sample_lines("Ember", cfg)
    assert len(errs) == 1
    assert "eleven_v3 emotion tags" in errs[0]


def test_voice_onboarding_waiver_skips_emotion_tag_gate():
    cfg = {
        "voice_onboarding_waiver": "narrator-only; no Element dialogue",
        "element_sample_lines": ["Plain narrator line."],
    }
    assert has_voice_onboarding_waiver(cfg) is True
    assert validate_emotion_tags_in_sample_lines("Narrator", cfg) == []


def test_validate_voice_onboarding_blocks_pending_without_delivery():
    cfg = _pending_cfg()
    errs = validate_voice_onboarding_before_spend("TotallyNewChar", cfg)
    assert any("no O3 delivery lock" in e for e in errs)


def test_validate_voice_onboarding_passes_ember_pending_shape():
    cfg = _pending_cfg(
        voice_sample_lock={
            "locked_speed": 1.0,
            "element_sample_lines": [
                "[warm, gentle] Come here — you don't have to do this alone.",
                "[curious, friendly] Hello there.",
            ],
            "audition_line": "Come here — you don't have to do this alone.",
        },
    )
    errs = [e for e in validate_voice_onboarding_before_spend("Ember", cfg) if "fingerprint" not in e]
    assert errs == []


def test_active_refresh_grandfathers_emotion_tags():
    cfg = {
        "status": "active",
        "element_id": "123",
        "element_sample_lines": ["Plain legacy line without tags."],
        "voice_sample_lock": {
            "locked_speed": 1.15,
            "element_sample_lines": ["Plain legacy line without tags."],
            "audition_line": "Plain legacy line without tags.",
        },
    }
    assert is_first_voice_registration(cfg) is False
    tag_errs = validate_emotion_tags_in_sample_lines("Tessa", cfg)
    assert tag_errs
    errs = validate_voice_onboarding_before_spend("Tessa", cfg, require_emotion_tags=False)
    assert not any("eleven_v3 emotion tags" in e for e in errs)


def test_every_roster_character_has_delivery_lock_and_sample_lines():
    """CI contract: adding ELEVENLABS_VOICE_ROSTER entry requires both layers in code."""
    errors = validate_roster_voice_onboarding_contract()
    assert errors == [], "roster voice onboarding gaps:\n  " + "\n  ".join(errors)


def test_roster_delivery_keys_are_canonical_speakers():
    extras = set(_DELIVERY_BY_SPEAKER) - set(ELEVENLABS_VOICE_ROSTER) - {"Loral", "Laurel"}
    assert extras == set(), f"unexpected delivery keys (not roster + Lorelai aliases): {extras}"


def test_active_beat_gen_speakers_have_delivery_locks():
    for name in ("Chipper", "Arlo", "Tessa", "Lorelai", "Ember", "Oliver", "Bramble"):
        assert delivery_for_speaker(name), f"{name} missing O3 delivery lock"


def test_oliver_upgrade_element_bound_voice_uses_delivery_lock(monkeypatch):
    from tools import kling_o3_prompt as o3p
    import beat_generator as bg

    monkeypatch.setattr(
        "tools.kling_character_registry.is_speaker_voice_ready",
        lambda _s: True,
    )
    raw = 'Oliver speaks warmly to the camera: "Something wonderful is waiting for us."'
    upgraded, spoken, changed = o3p.upgrade_element_bound_voice_prompt(
        "Oliver",
        raw,
        extract_spoken=bg.extract_spoken_dialogue_from_kling_prompt,
    )
    assert changed is True
    assert spoken == "Something wonderful is waiting for us."
    assert "Oliver speaks in a warm gentle conversational pace" in upgraded
    assert "not robotic" in upgraded


def test_ensure_voice_sample_skips_arc_fallback_for_roster_char(tmp_path, monkeypatch):
    """Roster characters must not silently clone legacy arc MP3s."""
    char_name = "Ember"
    assert char_name in ELEVENLABS_VOICE_ROSTER
    assert char_name in ARC1_SAMPLE_SOURCES

    samples_dir = tmp_path / "kling_voice_samples"
    samples_dir.mkdir()
    arc_src = tmp_path / "legacy_ember.mp3"
    arc_src.write_bytes(b"\x00" * 5000)

    monkeypatch.setattr("kling_element_voice.voice_samples_dir", lambda: samples_dir)
    monkeypatch.setattr("kling_element_voice.dropbox_root", lambda: tmp_path)
    monkeypatch.setattr(
        "kling_element_voice.ARC1_SAMPLE_SOURCES",
        {char_name: "legacy_ember.mp3"},
    )
    monkeypatch.setattr("kling_element_voice.ffprobe_duration", lambda _p: 10.0)

    cfg = {"status": "pending", "element_id": None}
    with patch(
        "kling_element_voice.generate_elevenlabs_sample",
        side_effect=RuntimeError("expected ElevenLabs path"),
    ):
        try:
            ensure_voice_sample(char_name, cfg, elevenlabs_key=None)
        except RuntimeError as exc:
            assert "ELEVENLABS_API_KEY" in str(exc) or "expected ElevenLabs" in str(exc)
        else:
            raise AssertionError("ensure_voice_sample should require ElevenLabs for roster char")

    dest = samples_dir / "ember.mp3"
    assert not dest.is_file(), "arc MP3 must not be copied for roster character"
