"""ElevenLabs → Kling create-voice → Element registration (permanent Beat Gen voice path).

Uses curl for WaveSpeed (Python http.client times out on this host).
Voice samples live in Production/kling_voice_samples/ (persistent on disk).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CREATE_VOICE_URL = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v2.6/create-voice"
ELEMENTS_URL = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-elements-advanced"
CATBOX_URL = "https://catbox.moe/user/api.php"
ELEVENLABS_TTS = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

MIN_SAMPLE_S = 5.0
MAX_SAMPLE_S = 30.0
MAX_ELEMENT_DESC = 100

# Locked roster — VOICE_ROSTER_LOCKED_v2.md (April 6, 2026)
ELEVENLABS_VOICE_ROSTER: dict[str, dict[str, Any]] = {
    "Chipper": {
        "elevenlabs_voice_id": "7o9pyvsN0ob5GO6LBQp6",
        "elevenlabs_voice_name": "Chipper1",
        "stability": 0.70,
        "similarity_boost": 0.75,
        "style": 0.08,
        "speed": 1.15,
        "model": "eleven_v3",
    },
    "Arlo": {
        "elevenlabs_voice_id": "7o9pyvsN0ob5GO6LBQp6",
        "elevenlabs_voice_name": "Arlo (Chipper1 interim)",
        # Guide delivery: high stability + low style (same Chipper fix, slightly calmer speed).
        "stability": 0.75,
        "similarity_boost": 0.75,
        "style": 0.05,
        "speed": 1.0,
        "model": "eleven_v3",
    },
    "Tessa": {
        "elevenlabs_voice_id": "cgSgspJ2msm6clMCkdW9",
        "elevenlabs_voice_name": "Jessica",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 1.15,
        "model": "eleven_v3",
    },
    "Luna": {
        "elevenlabs_voice_id": "PoHUWWWMHFrA8z7Q88pu",
        "elevenlabs_voice_name": "Miranda",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 1.15,
        "model": "eleven_v3",
    },
    "Lorelai": {
        "elevenlabs_voice_id": "PoHUWWWMHFrA8z7Q88pu",
        "elevenlabs_voice_name": "Miranda",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 1.15,
        "model": "eleven_v3",
    },
    "Ember": {
        "elevenlabs_voice_id": "T720RsqorTx4ZZWohrNN",
        "elevenlabs_voice_name": "Katie",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 1.0,
        "model": "eleven_v3",
    },
    "Bramble": {
        "elevenlabs_voice_id": "wo6udizrrtpIxWGp2qJk",
        "elevenlabs_voice_name": "Northern Terry",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 0.9,
        "model": "eleven_v3",
    },
    "Benson": {
        "elevenlabs_voice_id": "n7Wi4g1bhpw4Bs8HK5ph",
        "elevenlabs_voice_name": "Gigi",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 0.95,
        "model": "eleven_v3",
    },
    "Bork": {
        "elevenlabs_voice_id": "zzePw2Fo1hmm1iJnqh4y",
        "elevenlabs_voice_name": "Bork2",
        "stability": 0.20,
        "similarity_boost": 0.80,
        "style": 0.40,
        "speed": 0.95,
        "model": "eleven_v3",
    },
    "Oliver": {
        "elevenlabs_voice_id": "3XOBzXhnDY98yeWQ3GdM",
        "elevenlabs_voice_name": "Brayden",
        "stability": 0.35,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 1.0,
        "model": "eleven_v3",
    },
    "Grizzle": {
        "elevenlabs_voice_id": "M9UAxraM2w5tCjpOaIB0",
        "elevenlabs_voice_name": "Gotham Boss",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 1.0,
        "model": "eleven_v3",
    },
    "Willow": {
        "elevenlabs_voice_id": "ftDdhfYtmfGP0tFlBYA1",
        "elevenlabs_voice_name": "Alisha",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 0.85,
        "model": "eleven_v3",
    },
    "The King": {
        "elevenlabs_voice_id": "qNkzaJoHLLdpvgh5tISm",
        "elevenlabs_voice_name": "Carter",
        "stability": 0.30,
        "similarity_boost": 0.80,
        "style": 0.30,
        "speed": 0.9,
        "model": "eleven_v3",
    },
}

# Preferred arc_1_v3 sources (Dropbox project root relative) for create-voice samples.
# Chipper omitted — always generate from ElevenLabs Chipper1 (never legacy guide_bird audio).
ARC1_SAMPLE_SOURCES: dict[str, str] = {
    "Tessa": "Production/Event_1/line_03_tessa.mp3",
    "Luna": "video_pipeline/audio/arc_1_v3/event_2_luna_intro/luna_04.mp3",
    "Lorelai": "video_pipeline/audio/arc_1_v3/event_2_luna_intro/luna_04.mp3",
    "Ember": "video_pipeline/audio/arc_1_v3/event_3_ember_intro/ember_03.mp3",
    "Bramble": "video_pipeline/audio/arc_1_v3/event_4_bramble_intro/bramble_28.mp3",
    "Bork": "video_pipeline/audio/arc_1_v3/event_6_bork_intro/bork_07.mp3",
    "Oliver": "video_pipeline/audio/arc_1_v3/event_3b_oliver_meet/oliver_03.mp3",
}


def prod_root() -> Path:
    return Path(__file__).resolve().parent.parent


def dropbox_root() -> Path:
    from lib.paths import DROPBOX_ROOT
    return DROPBOX_ROOT


def voice_samples_dir() -> Path:
    return prod_root() / "kling_voice_samples"


def curl_json(method: str, url: str, api_key: str, payload: dict | None = None) -> dict:
    from kling_o3_client import resolve_wavespeed_host

    cmd = [
        "curl", "-s", "-S", "--http1.1", "-m", "120", "-X", method,
        "-H", f"Authorization: Bearer {api_key}", "-H", "Connection: close",
    ]
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(payload)]
    resolved = resolve_wavespeed_host()
    if resolved and "api.wavespeed.ai" in url:
        cmd += ["--resolve", f"api.wavespeed.ai:443:{resolved}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed: {r.stderr}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def upload_catbox(file_path: Path) -> str:
    cmd = [
        "curl", "-s", "-S", "-m", "120",
        "-F", "reqtype=fileupload",
        "-F", f"fileToUpload=@{file_path}",
        CATBOX_URL,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=130)
    url = r.stdout.strip()
    if r.returncode != 0 or not url.startswith("https://"):
        raise RuntimeError(f"catbox upload failed for {file_path.name}: {url[:200]}")
    return url


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def poll_wavespeed(prediction_id: str, api_key: str, label: str, timeout_s: int = 180) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(3)
        poll = curl_json(
            "GET",
            f"https://api.wavespeed.ai/api/v3/predictions/{prediction_id}/result",
            api_key,
        )
        data = poll.get("data") or poll
        status = (data.get("status") or "unknown").lower()
        if status in ("completed", "succeeded"):
            return data
        if status in ("failed", "error"):
            raise RuntimeError(f"{label} failed: {json.dumps(poll)[:800]}")
    raise TimeoutError(f"{label} timed out after {timeout_s}s")


def truncate_element_description(text: str) -> str:
    t = (text or "").strip()
    if len(t) <= MAX_ELEMENT_DESC:
        return t
    return t[: MAX_ELEMENT_DESC - 1].rstrip() + "…"


def generate_elevenlabs_sample(
    char_name: str,
    text: str,
    elevenlabs_key: str,
    dest: Path,
) -> Path:
    """Synthesize a clean MP3 sample for create-voice (5–30s target)."""
    roster = ELEVENLABS_VOICE_ROSTER.get(char_name)
    if not roster:
        raise KeyError(f"No ElevenLabs roster entry for {char_name!r}")
    voice_id = roster["elevenlabs_voice_id"]
    voice_settings = {
        k: float(roster[k])
        for k in ("stability", "similarity_boost", "style", "speed")
        if roster.get(k) is not None
    }
    model_id = roster.get("model") or "eleven_v3"
    body = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": voice_settings,
    }).encode("utf-8")
    url = ELEVENLABS_TTS.format(voice_id=voice_id)
    cmd = [
        "curl", "-s", "-S", "-m", "90", "-X", "POST",
        "-H", f"xi-api-key: {elevenlabs_key}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: audio/mpeg",
        "-d", body.decode("utf-8"),
        "-o", str(dest),
        url,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=100)
    if r.returncode != 0 or not dest.is_file() or dest.stat().st_size < 1000:
        raise RuntimeError(f"ElevenLabs TTS failed for {char_name}: {r.stderr[:300]}")
    return dest


def ensure_voice_sample(
    char_name: str,
    cfg: dict,
    elevenlabs_key: str | None = None,
    *,
    force_regenerate: bool = False,
) -> Path:
    """Return a persistent 5–30s MP3 in kling_voice_samples/ (copy or generate).

    Sample text comes from voice_sample_lock / element_sample_lines — never silently
    from legacy audition_line when a lock exists with different lines.
    """
    from kling_voice_sample_lock import (
        resolve_element_sample_text,
        stored_sample_matches_lock,
    )

    samples_dir = voice_samples_dir()
    samples_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", char_name.lower()).strip("_")
    dest = samples_dir / f"{slug}.mp3"
    sample_text = resolve_element_sample_text(char_name, cfg)

    if force_regenerate and dest.is_file():
        dest.unlink()

    if not force_regenerate:
        rel = cfg.get("elevenlabs_voice_sample_path")
        if rel:
            existing = prod_root() / rel
            if existing.is_file():
                dur = ffprobe_duration(existing)
                if MIN_SAMPLE_S <= dur <= MAX_SAMPLE_S and stored_sample_matches_lock(
                    char_name, cfg, existing, dur,
                ):
                    if not dest.is_file() or dest.resolve() != existing.resolve():
                        shutil.copy2(existing, dest)
                    return dest

        if dest.is_file():
            dur = ffprobe_duration(dest)
            if MIN_SAMPLE_S <= dur <= MAX_SAMPLE_S and stored_sample_matches_lock(
                char_name, cfg, dest, dur,
            ):
                return dest

        # Try arc_1_v3 source copy (non-Chipper legacy path only)
        if not cfg.get("voice_sample_lock"):
            arc_rel = ARC1_SAMPLE_SOURCES.get(char_name)
            if arc_rel:
                src = dropbox_root() / arc_rel
                if src.is_file():
                    dur = ffprobe_duration(src)
                    if MIN_SAMPLE_S <= dur <= MAX_SAMPLE_S:
                        shutil.copy2(src, dest)
                        return dest

    if not elevenlabs_key:
        raise RuntimeError(
            f"No valid sample for {char_name} and ELEVENLABS_API_KEY required to generate"
        )

    line = sample_text
    generate_elevenlabs_sample(char_name, line, elevenlabs_key, dest)
    dur = ffprobe_duration(dest)
    if dur < MIN_SAMPLE_S:
        line = (
            f"{line} I speak clearly and at a natural conversational pace "
            "for children and families learning magic together."
        )
        generate_elevenlabs_sample(char_name, line, elevenlabs_key, dest)
        dur = ffprobe_duration(dest)
    if dur < MIN_SAMPLE_S:
        raise RuntimeError(
            f"Generated sample for {char_name} is {dur:.1f}s — need ≥{MIN_SAMPLE_S}s. "
            f"Add element_sample_lines in character_subjects.json."
        )
    if dur > MAX_SAMPLE_S:
        raise RuntimeError(
            f"Generated sample for {char_name} is {dur:.1f}s — need ≤{MAX_SAMPLE_S}s. "
            "Shorten element_sample_lines."
        )
    return dest


def create_kling_voice(audio_url: str, wavespeed_key: str) -> str:
    resp = curl_json("POST", CREATE_VOICE_URL, wavespeed_key, {"audio": audio_url})
    prediction_id = (resp.get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"create-voice: no prediction id: {resp}")
    data = poll_wavespeed(str(prediction_id), wavespeed_key, "create-voice")
    outputs = data.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"create-voice: no outputs: {data}")
    first = outputs[0]
    voice_id = first.get("voice_id") if isinstance(first, dict) else str(first)
    if not voice_id:
        raise RuntimeError(f"create-voice: no voice_id: {data}")
    return str(voice_id)


def register_kling_element(
    char_name: str,
    cfg: dict,
    voice_id: str,
    wavespeed_key: str,
) -> tuple[str, str]:
    """Register image_refer Element with bound custom voice. Returns (element_id, prediction_id)."""
    frontal_path = prod_root() / cfg["frontal_image"]
    refer_paths = [prod_root() / p for p in (cfg.get("refer_images") or [])]
    if not frontal_path.is_file():
        raise FileNotFoundError(f"Missing frontal_image: {frontal_path}")
    for rp in refer_paths:
        if not rp.is_file():
            raise FileNotFoundError(f"Missing refer_image: {rp}")

    frontal_url = upload_catbox(frontal_path)
    refer_urls = [upload_catbox(rp) for rp in refer_paths]

    payload = {
        "name": cfg.get("element_name") or char_name,
        "description": truncate_element_description(cfg.get("description") or char_name),
        "reference_type": "image_refer",
        "frontal_image": frontal_url,
        "refer_images": refer_urls,
        "voice_id": voice_id,
    }
    resp = curl_json("POST", ELEMENTS_URL, wavespeed_key, payload)
    prediction_id = str((resp.get("data") or {}).get("id") or "")
    if not prediction_id:
        raise RuntimeError(f"elements: no prediction id: {resp}")
    data = poll_wavespeed(prediction_id, wavespeed_key, "element", timeout_s=120)
    outputs = data.get("outputs") or []
    element_id = data.get("element_id")
    if not element_id and outputs:
        first = outputs[0]
        element_id = first.get("element_id") if isinstance(first, dict) else first
    if not element_id:
        raise RuntimeError(f"elements: no element_id: {data}")
    return str(element_id), prediction_id


def setup_character_voice(
    char_name: str,
    cfg: dict,
    wavespeed_key: str,
    elevenlabs_key: str | None = None,
    *,
    force: bool = False,
) -> dict:
    """Full pipeline: sample → create-voice → element. Returns updated cfg."""
    if cfg.get("status") == "active" and cfg.get("element_id") and not force:
        return cfg

    roster = ELEVENLABS_VOICE_ROSTER.get(char_name, {})
    sample_path = ensure_voice_sample(
        char_name, cfg, elevenlabs_key, force_regenerate=force,
    )
    rel_sample = f"kling_voice_samples/{sample_path.name}"

    audio_url = upload_catbox(sample_path)
    kling_voice_id = create_kling_voice(audio_url, wavespeed_key)
    element_id, prediction_id = register_kling_element(char_name, cfg, kling_voice_id, wavespeed_key)

    updated = dict(cfg)
    updated["elevenlabs_voice_id"] = roster.get("elevenlabs_voice_id")
    updated["elevenlabs_voice_name"] = roster.get("elevenlabs_voice_name")
    updated["elevenlabs_voice_sample_path"] = rel_sample
    updated["kling_voice_id"] = kling_voice_id
    updated["kling_voice_label"] = f"ElevenLabs {roster.get('elevenlabs_voice_name', '')} (create-voice)"
    updated["element_id"] = element_id
    updated["status"] = "active"
    updated["created_at"] = datetime.now(timezone.utc).isoformat()
    updated["wavespeed_prediction_id"] = prediction_id
    lock = cfg.get("voice_sample_lock")
    if lock:
        updated["voice_sample_lock"] = lock
        updated["element_sample_lines"] = cfg.get("element_sample_lines") or lock.get("element_sample_lines")
        updated["element_sample_text"] = cfg.get("element_sample_text") or lock.get("element_sample_text")
        updated["audition_speed"] = lock.get("locked_speed") or cfg.get("audition_speed")
    return updated
