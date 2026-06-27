"""Unit tests for ElevenLabs request stitching (Phase B voice stem regen)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_REPO_LIB) not in sys.path:
    sys.path.insert(0, str(_REPO_LIB))

from elevenlabs_tts import (  # noqa: E402
    build_tts_payload,
    continuity_context_head,
    continuity_context_tail,
    extract_request_id,
    synthesize_stitched_speech_segments,
)


def test_build_tts_payload_includes_stitching_fields():
    payload = build_tts_payload(
        text="Hello world.",
        model_id="eleven_v3",
        voice_settings={"stability": 0.7},
        previous_request_ids=["req-a", "req-b", "req-c", "req-d"],
        next_text="Next segment starts here.",
    )
    assert payload["text"] == "Hello world."
    assert payload["previous_request_ids"] == ["req-b", "req-c", "req-d"]
    assert payload["next_text"] == "Next segment starts here."


def test_build_tts_payload_omits_stitching_when_absent():
    payload = build_tts_payload(
        text="Single call.",
        model_id="eleven_v3",
        voice_settings={"stability": 0.5},
    )
    assert "previous_request_ids" not in payload
    assert "next_text" not in payload


def test_continuity_context_truncates_long_text():
    long_text = "word " * 200
    tail = continuity_context_tail(long_text, max_chars=50)
    head = continuity_context_head(long_text, max_chars=50)
    assert tail is not None and len(tail) <= 50
    assert head is not None and len(head) <= 50
    assert tail.endswith("word")
    assert head.startswith("word")


def test_extract_request_id_from_headers():
    headers = [("Content-Type", "audio/mpeg"), ("request-id", "abc-123")]
    assert extract_request_id(headers) == "abc-123"


def test_synthesize_stitched_speech_segments_chains_request_ids():
    calls: list[dict] = []

    def fake_tts_call(*, text, previous_request_ids=None, next_text=None):
        calls.append({
            "text": text,
            "previous_request_ids": previous_request_ids,
            "next_text": next_text,
        })
        req_id = f"req-{len(calls)}"
        return 200, f"audio-{text}".encode(), req_id

    texts = ["First chunk.", "Second chunk.", "Third chunk."]
    chunks, request_ids, failed = synthesize_stitched_speech_segments(
        texts,
        tts_call=fake_tts_call,
    )
    assert failed == -1
    assert len(chunks) == 3
    assert request_ids == ["req-1", "req-2", "req-3"]
    assert calls[0]["previous_request_ids"] is None
    assert calls[0]["next_text"] == "Second chunk."
    assert calls[1]["previous_request_ids"] == ["req-1"]
    assert calls[1]["next_text"] == "Third chunk."
    assert calls[2]["previous_request_ids"] == ["req-1", "req-2"]
    assert calls[2]["next_text"] is None


def test_synthesize_stitched_speech_segments_stops_on_http_error():
    def fake_tts_call(*, text, previous_request_ids=None, next_text=None):
        if text == "bad":
            return 502, b"error", None
        return 200, b"ok", "req-1"

    chunks, request_ids, failed = synthesize_stitched_speech_segments(
        ["ok", "bad"],
        tts_call=fake_tts_call,
    )
    assert failed == 1
    assert len(chunks) == 1
    assert request_ids == ["req-1"]
