#!/usr/bin/env python3
"""
regen_tts_beat_06_09.py

Regenerate TTS audio for beat_06 (Guide Bird / Pip) and beat_09 (Tessa)
using ElevenLabs eleven_v3 and the locked voice profiles in prod_voice_profiles.

Voice settings per Directus prod_voice_profiles (April 17 2026 snapshot):
  beat_06 (id=2): Guide Bird  7o9pyvsN0ob5GO6LBQp6  stab=0.3 sim=0.8 style=0.3
  beat_09 (id=3): Tessa       cgSgspJ2msm6clMCkdW9  stab=0.5 sim=0.8 style=0.3 speed=1.0

Text per Kim's chat 2026-04-17 afternoon (Rule 11 Source Fidelity — verbatim).

Preserves prior TTS renders to preserved_winners/ before writing.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"
TS = datetime.now().strftime("%Y%m%d-%H%M%S")

# ----- Voice profiles (locked from prod_voice_profiles) -----
GUIDE_BIRD = {
    "voice_id": "7o9pyvsN0ob5GO6LBQp6",
    "voice_settings": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.3},
    "model": "eleven_v3",
}
TESSA = {
    "voice_id": "cgSgspJ2msm6clMCkdW9",
    "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.3, "speed": 1.0},
    "model": "eleven_v3",
}

# ----- Per-beat config (text verbatim per Kim's chat) -----
BEATS = {
    "beat_06": {
        "speaker": "Guide Bird",
        "voice": GUIDE_BIRD,
        "text": (
            "[warm, encouraging, friendly introduction] Well maybe we can help. "
            "[pause] [pause] I'm Pip. [pause] This is my new apprentice. "
            "[pause] [pause] We're training in the Magical Arts."
        ),
        "out_file": TTS_DIR / "line_06_guide_bird.mp3",
    },
    "beat_09": {
        "speaker": "Tessa",
        "voice": TESSA,
        "text": "[cautiously hopeful, uncertain] Do you think you can really do it?",
        "out_file": TTS_DIR / "line_09_tessa.mp3",
    },
}

ELEVENLABS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_elevenlabs_key() -> str:
    sys.path.insert(0, str(HERE / "credentials_lib"))
    from credentials_lib.credentials import load_credentials  # type: ignore
    creds = load_credentials()
    key = creds.get("elevenlabs_key") or ""
    if not key:
        sys.exit("FATAL: no elevenlabs_key in credentials")
    return key


def preserve_prior_renders(beat_id: str, out_path: Path) -> list[Path]:
    """Copy any existing line_NN*.mp3 to preserved_winners/ with TS stamp."""
    PRESERVED.mkdir(exist_ok=True)
    beat_num = beat_id.split("_")[1]  # "06" / "09"
    preserved = []
    for prior in sorted(TTS_DIR.glob(f"line_{beat_num}*.mp3")):
        dst = PRESERVED / f"pre_regen_{prior.stem}_{TS}.mp3"
        shutil.copy2(prior, dst)
        preserved.append(dst)
        log(f"  preserved → preserved_winners/{dst.name}")
    return preserved


def tts_generate(voice: dict, text: str, out_path: Path, api_key: str) -> int:
    """Call ElevenLabs v1/text-to-speech, write audio, return bytes written."""
    url = ELEVENLABS_ENDPOINT.format(voice_id=voice["voice_id"])
    body = json.dumps({
        "text": text,
        "model_id": voice["model"],
        "voice_settings": voice["voice_settings"],
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        method="POST",
    )
    log(f"  POST {url[:80]}... ({len(text)}c, {voice['model']})")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.exit(f"ElevenLabs HTTP {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"ElevenLabs request failed: {e}")
    # Atomic write
    tmp = out_path.with_suffix(f".tmp.{os.getpid()}.mp3")
    tmp.write_bytes(audio)
    os.replace(tmp, out_path)
    return len(audio)


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip()) if r.returncode == 0 else 0.0


def directus_log(beat_id: str, out_file: str, text: str, voice: dict,
                 size_bytes: int, duration_s: float) -> None:
    """Rule 18 two-write: log this TTS regen to prod_activity_log."""
    try:
        sys.path.insert(0, str(HERE / "credentials_lib"))
        from credentials_lib.credentials import load_credentials  # type: ignore
        from credentials_lib.directus import DirectusClient  # type: ignore
        creds = load_credentials()
        c = DirectusClient(creds["directus_url"], creds["directus_email"],
                           creds["directus_password"])
        c._request("POST", "/items/prod_activity_log", data={
            "action": "tts_regenerated",
            "module_id": 1,
            "performed_by": "regen_tts_beat_06_09",
            "details": json.dumps({
                "beat_id": beat_id,
                "speaker_voice_id": voice["voice_id"],
                "voice_settings": voice["voice_settings"],
                "model": voice["model"],
                "text_full": text,
                "out_file": out_file,
                "size_bytes": size_bytes,
                "duration_s": duration_s,
                "ts": TS,
                "rule_reference": "Rule 11 source fidelity + prod_voice_profiles",
            }),
        })
        log(f"  directus activity_log written")
    except Exception as e:
        log(f"  directus log failed (non-fatal): {e}")


def main():
    log("=" * 70)
    log(f"Regenerate TTS for beat_06 + beat_09 — TS {TS}")
    log("=" * 70)
    api_key = load_elevenlabs_key()
    log(f"  elevenlabs key loaded: ...{api_key[-8:]}")

    results = []
    for beat_id, cfg in BEATS.items():
        log(f"\n--- {beat_id} ({cfg['speaker']}) ---")
        log(f"  text: {cfg['text'][:120]}{'...' if len(cfg['text'])>120 else ''}")

        preserve_prior_renders(beat_id, cfg["out_file"])

        size = tts_generate(cfg["voice"], cfg["text"], cfg["out_file"], api_key)
        dur = probe_duration(cfg["out_file"])
        log(f"  → {cfg['out_file'].name} ({dur:.2f}s, {size:,} bytes)")

        # Also preserve this fresh render with WINNER tag for safety
        shutil.copy2(
            cfg["out_file"],
            PRESERVED / f"{cfg['out_file'].stem}_FRESH_{TS}.mp3",
        )

        directus_log(beat_id, cfg["out_file"].name, cfg["text"],
                     cfg["voice"], size, dur)

        results.append((beat_id, cfg["out_file"], dur, size))

    # Open both in QuickTime for review
    log("\n" + "=" * 70)
    log("TTS REGENERATION COMPLETE — opening in QuickTime for review")
    log("=" * 70)
    for beat_id, path, dur, size in results:
        log(f"  {beat_id}: {path.name} ({dur:.2f}s)")
        subprocess.run(["open", "-a", "QuickTime Player", str(path)])


if __name__ == "__main__":
    main()
