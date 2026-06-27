"""Unit tests for Phase B eleven_v3 ffmpeg concat + stitching helpers."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_REPO_LIB) not in sys.path:
    sys.path.insert(0, str(_REPO_LIB))

from elevenlabs_tts import (  # noqa: E402
    CEDRIC_PHASE_B_V3_ACCENT_PREAMBLE,
    build_tts_payload,
    coalesce_segments_for_v3_regen,
    inline_v3_pause_tag,
    model_supports_request_stitching,
    prepend_accent_to_first_speech_chunk,
)


def test_coalesce_ffmpeg_only_for_timed_silence_two_seconds_plus():
    chunks = coalesce_segments_for_v3_regen(
        [
            ("text", "Before."),
            ("timed_silence", 1.0),
            ("text", "Middle."),
            ("timed_silence", 3.0),
            ("text", "After."),
        ],
        lambda t: t.strip(),
        ffmpeg_silence_min_s=2.0,
    )
    assert len(chunks) == 3
    assert chunks[0][0] == "speech"
    assert inline_v3_pause_tag(1.0) in chunks[0][1]
    assert "Middle." in chunks[0][1]
    assert chunks[1] == ("silence", 3.0)
    assert chunks[2] == ("speech", "After.")


def test_prepend_accent_to_first_speech_chunk_only():
    coalesced = [
        ("speech", "Hello."),
        ("silence", 3.0),
        ("speech", "World."),
    ]
    out = prepend_accent_to_first_speech_chunk(
        coalesced,
        CEDRIC_PHASE_B_V3_ACCENT_PREAMBLE,
    )
    assert out[0][1].startswith("[British accent throughout]")
    assert out[2][1] == "World."


def test_build_tts_payload_omits_stitching_for_eleven_v3():
    payload = build_tts_payload(
        text="Hi.",
        model_id="eleven_v3",
        voice_settings={"stability": 0.7},
        previous_request_ids=["req-1"],
        next_text="Next.",
    )
    assert "previous_request_ids" not in payload
    assert "next_text" not in payload


def test_model_supports_request_stitching():
    assert model_supports_request_stitching("eleven_multilingual_v2") is True
    assert model_supports_request_stitching("eleven_v3") is False
