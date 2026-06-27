"""ElevenLabs TTS helpers — request stitching for multi-segment voice stems.

Phase B/A regen_audio splits scripts on [pause]/[silence:Ns] markers. Each speech
chunk is a separate API call; without ElevenLabs request stitching, prosody and
accent can jump between segments. See:
https://elevenlabs.io/docs/eleven-api/guides/how-to/text-to-speech/request-stitching
"""
from __future__ import annotations

import json
import ssl
import time
from typing import Callable

# ElevenLabs accepts up to 3 prior request IDs; keep context text bounded.
_MAX_PRIOR_REQUEST_IDS = 3
_CONTINUITY_TEXT_CHARS = 400

# Official docs: request stitching is unavailable for eleven_v3.
_STITCHING_UNSUPPORTED_MODELS = frozenset({"eleven_v3", "eleven_v3_preview"})


def model_supports_request_stitching(model_id: str | None) -> bool:
    """True when ElevenLabs accepts previous_request_ids / next_text for this model."""
    return (model_id or "").strip().lower() not in _STITCHING_UNSUPPORTED_MODELS


def inline_v3_pause_tag(duration_s: float) -> str:
    """Map authored short pause seconds → ElevenLabs v3 audio tags (not SSML break)."""
    dur = max(0.0, float(duration_s))
    if dur >= 1.5:
        return "[long pause]"
    if dur >= 0.75:
        return "[pause]"
    return "[short pause]"


def timed_silence_to_v3_pauses(duration_s: float) -> str:
    """Map ``[silence:Ns]`` to v3 pause tags for single-call generation."""
    dur = max(0.0, float(duration_s))
    if dur >= 3.0:
        return " ".join(["[long pause]"] * max(1, round(dur / 2.5)))
    if dur >= 1.5:
        return "[long pause]"
    if dur >= 0.75:
        return "[pause]"
    return "[short pause]"


# Prepended once on Phase B Cedric regen — v3 delivery tags, not spoken as dialogue.
CEDRIC_PHASE_B_V3_ACCENT_PREAMBLE = "[British accent throughout] [warm] "


def build_single_call_v3_script(
    script: str,
    clean_text_fn,
    *,
    accent_preamble: str = "",
) -> str:
    """One ElevenLabs paste for eleven_v3 — accent + v3 pause tags (Kim M4 workflow)."""
    import re as _re

    _marker_pat = _re.compile(
        r"\[(?:silence:\s*(\d+(?:\.\d+)?)\s*s?|pause|break|silence)\]",
        _re.IGNORECASE,
    )
    parts: list[str] = []
    last = 0
    for match in _marker_pat.finditer(script):
        chunk = script[last:match.start()].strip()
        if chunk:
            parts.append(clean_text_fn(chunk))
        dur_raw = match.group(1)
        if dur_raw:
            parts.append(timed_silence_to_v3_pauses(float(dur_raw)))
        else:
            parts.append(inline_v3_pause_tag(0.5))
        last = match.end()
    tail = script[last:].strip()
    if tail:
        parts.append(clean_text_fn(tail))
    if not parts:
        body = clean_text_fn(script)
    else:
        body = " ".join(p for p in parts if p).strip()
    if accent_preamble:
        return f"{accent_preamble.strip()} {body}".strip()
    return body


def coalesce_segments_for_v3_regen(
    segments: list[tuple[str, str | float]],
    clean_text_fn,
    *,
    ffmpeg_silence_min_s: float = 2.0,
) -> list[tuple[str, str | float]]:
    """Coalesce script segments for eleven_v3 PHASE_VOICE_STEM_CONCAT_V1 regen.

    - ``[silence:2s+]`` → real ffmpeg silence (exact hold — Event 1/2 behavior).
    - ``[silence:1s]`` / ``[pause]`` → inline v3 pause tags inside the speech chunk
      (no extra ElevenLabs call — keeps call count ~10, not 22).
    """
    chunks: list[tuple[str, str | float]] = []
    speech_buf: list[str] = []

    def _flush_speech() -> None:
        if not speech_buf:
            return
        text = " ".join(speech_buf).strip()
        speech_buf.clear()
        if text:
            chunks.append(("speech", text))

    for kind, value in segments:
        if kind == "text":
            cleaned = clean_text_fn(value)
            if cleaned:
                speech_buf.append(cleaned)
            continue
        if kind == "timed_silence":
            dur = float(value)
            if dur >= ffmpeg_silence_min_s:
                _flush_speech()
                chunks.append(("silence", dur))
            else:
                speech_buf.append(inline_v3_pause_tag(dur))
            continue
        if kind == "pause":
            speech_buf.append(inline_v3_pause_tag(float(value)))
            continue
        # Backward compat if legacy parser emitted generic silence.
        dur = float(value)
        if dur >= ffmpeg_silence_min_s:
            _flush_speech()
            chunks.append(("silence", dur))
        else:
            speech_buf.append(inline_v3_pause_tag(dur))

    _flush_speech()
    return chunks


def prepend_accent_to_first_speech_chunk(
    coalesced: list[tuple[str, str | float]],
    accent_preamble: str,
) -> list[tuple[str, str | float]]:
    """Prepend v3 delivery tags to the first speech chunk only."""
    if not accent_preamble:
        return coalesced
    out: list[tuple[str, str | float]] = []
    applied = False
    for kind, value in coalesced:
        if not applied and kind == "speech":
            out.append((kind, f"{accent_preamble.strip()} {value}".strip()))
            applied = True
        else:
            out.append((kind, value))
    return out


def continuity_context_tail(text: str | None, *, max_chars: int = _CONTINUITY_TEXT_CHARS) -> str | None:
    """Tail of prior speech for next_text / previous_text continuity hints."""
    if not text:
        return None
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[-max_chars:]


def continuity_context_head(text: str | None, *, max_chars: int = _CONTINUITY_TEXT_CHARS) -> str | None:
    """Head of upcoming speech for next_text continuity hints."""
    if not text:
        return None
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return None
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars]


def build_tts_payload(
    *,
    text: str,
    model_id: str,
    voice_settings: dict,
    previous_request_ids: list[str] | None = None,
    next_text: str | None = None,
) -> dict:
    """Build ElevenLabs /v1/text-to-speech JSON body with optional stitching."""
    payload: dict = {
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings,
    }
    if previous_request_ids and model_supports_request_stitching(model_id):
        payload["previous_request_ids"] = list(previous_request_ids)[-_MAX_PRIOR_REQUEST_IDS:]
    if next_text and model_supports_request_stitching(model_id):
        payload["next_text"] = next_text
    return payload


def extract_request_id(response_headers: list[tuple[str, str]]) -> str | None:
    """Parse ``request-id`` from ElevenLabs response headers."""
    for key, value in response_headers:
        if key.lower() == "request-id" and value:
            return value.strip()
    return None


def call_elevenlabs_tts(
    *,
    api_key: str,
    voice_id: str,
    text: str,
    model_id: str,
    voice_settings: dict,
    previous_request_ids: list[str] | None = None,
    next_text: str | None = None,
    timeout: int = 90,
    max_retries: int = 3,
    retry_on_status: tuple[int, ...] = (500, 502, 503, 504),
) -> tuple[int, bytes, str | None]:
    """POST /v1/text-to-speech/{voice_id}; returns (status, audio_bytes, request_id)."""
    import http.client as _http

    body_bytes = json.dumps(
        build_tts_payload(
            text=text,
            model_id=model_id,
            voice_settings=voice_settings,
            previous_request_ids=previous_request_ids,
            next_text=next_text,
        ),
    ).encode("utf-8")
    path = f"/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
        "Content-Length": str(len(body_bytes)),
    }

    last_exc: Exception | None = None
    last_status: int | None = None
    last_body: bytes = b""
    last_request_id: str | None = None

    for attempt in range(max_retries):
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = _http.HTTPSConnection("api.elevenlabs.io", timeout=timeout, context=ctx)
            try:
                conn.request("POST", path, body=body_bytes, headers=headers)
                resp = conn.getresponse()
                raw = resp.read()
                last_status = resp.status
                last_body = raw
                last_request_id = extract_request_id(resp.getheaders())
            finally:
                conn.close()

            if last_status < 400:
                if attempt > 0:
                    print(
                        f"[elevenlabs-tts] POST {path[:48]} succeeded on retry {attempt + 1}",
                        flush=True,
                    )
                return last_status, last_body, last_request_id

            if last_status in retry_on_status:
                last_exc = Exception(
                    f"HTTP {last_status}: {raw[:200].decode('utf-8', 'replace')}",
                )
                print(
                    f"[elevenlabs-tts] POST {path[:48]} attempt {attempt + 1}/{max_retries}: "
                    f"HTTP {last_status} — retrying",
                    flush=True,
                )
            else:
                return last_status, last_body, last_request_id

        except (TimeoutError, _http.HTTPException, OSError) as exc:
            last_exc = exc
            print(
                f"[elevenlabs-tts] POST {path[:48]} attempt {attempt + 1}/{max_retries}: "
                f"{type(exc).__name__}: {exc} — retrying",
                flush=True,
            )

        if attempt < max_retries - 1:
            time.sleep(3 * (3 ** attempt))

    if last_exc:
        raise last_exc
    return last_status or 0, last_body, last_request_id


def synthesize_stitched_speech_segments(
    speech_texts: list[str],
    *,
    tts_call: Callable[..., tuple[int, bytes, str | None]],
) -> tuple[list[bytes], list[str], int]:
    """Synthesize ordered speech chunks with request-id stitching between calls.

    ``tts_call`` receives keyword args: text, previous_request_ids, next_text.
    Returns (audio_chunks, request_ids, failed_index_or_-1).
    """
    audio_chunks: list[bytes] = []
    request_ids: list[str] = []
    for idx, text in enumerate(speech_texts):
        if not (text or "").strip():
            continue
        next_text = continuity_context_head(
            speech_texts[idx + 1] if idx + 1 < len(speech_texts) else None,
        )
        prev_ids = request_ids[-_MAX_PRIOR_REQUEST_IDS:] if request_ids else None
        status, audio_bytes, request_id = tts_call(
            text=text,
            previous_request_ids=prev_ids,
            next_text=next_text,
        )
        if status >= 400:
            return audio_chunks, request_ids, idx
        audio_chunks.append(audio_bytes)
        if request_id:
            request_ids.append(request_id)
    return audio_chunks, request_ids, -1
