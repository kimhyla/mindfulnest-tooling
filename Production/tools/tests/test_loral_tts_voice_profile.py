"""Loral display name must resolve ElevenLabs voice (registry → Lorelai → Luna cache)."""
from __future__ import annotations

import production_server as ps


def test_loral_resolves_voice_profile_via_registry(monkeypatch):
    monkeypatch.setattr(
        ps,
        "_load_voice_profiles_from_directus",
        lambda force_refresh=False: {
            "Luna": {"voice_id": "test-luna-voice", "model": "eleven_v3"},
        },
    )
    profile = ps._resolve_voice_profile("Loral")
    assert profile is not None
    assert profile["voice_id"] == "test-luna-voice"
