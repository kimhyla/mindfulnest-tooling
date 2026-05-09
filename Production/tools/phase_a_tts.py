#!/usr/bin/env python3
"""Phase A M1 Chipper TTS generation.

Generates 3 instruction cues from module_M1_config.json → phaseAConfig →
instructionCues, verbatim (Rule 11 source fidelity). Voice profile from
prod_voice_profiles id=2 (Chipper, formerly "Guide Bird").

Also builds a concatenated lipsync-ready track (with natural pauses between
cues) for ByteDance LipSync on the close-up still.

Outputs:
  Production/Event_1/phase_a_tts/phase_a_cue_01_on_start.mp3
  Production/Event_1/phase_a_tts/phase_a_cue_02_on_timeout.mp3
  Production/Event_1/phase_a_tts/phase_a_cue_03_on_demo_complete.mp3
  Production/Event_1/phase_a_tts/phase_a_speech_combined.mp3
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
OUT_DIR = EVENT_DIR / "phase_a_tts"
OUT_DIR.mkdir(exist_ok=True)
TS = datetime.now().strftime("%Y%m%d-%H%M%S")

# Locked voice profile from prod_voice_profiles id=2
CHIPPER = {
    "voice_id": "7o9pyvsN0ob5GO6LBQp6",
    "voice_settings": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.3},
    "model": "eleven_v3",
}

# Kim-approved cues (Rule 11 source fidelity — module_M1_config.json verbatim,
# with ElevenLabs v3 emotion tags prefixed per Kim approval 2026-04-20).
CUES = [
    {
        "name": "cue_01_on_start",
        "text": (
            "[warm, bright, inviting] For this magic spell, you're going to "
            "learn how to make a ball of invisible energy right between your "
            "hands. Tap your character to see."
        ),
        "gap_after_s": 1.5,
    },
    {
        "name": "cue_02_on_timeout",
        "text": "[gentle, patient] Just watch.",
        "gap_after_s": 1.2,
    },
    {
        "name": "cue_03_on_demo_complete",
        "text": (
            "[building, hushed anticipation at end] When the time comes, "
            "you're going to use your attention, and your breathing, and "
            "you're going to follow the instructions .... and you'll feel "
            "it \u2014 real energy right between your hands like this. "
            "Ready...? .... Listen to the voice on the wind......"
        ),
        "gap_after_s": 0.0,
    },
]

ELEVEN_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_elevenlabs_key() -> str:
    sys.path.insert(0, str(HERE / "credentials_lib"))
    from credentials_lib.credentials import load_credentials  # type: ignore
    creds = load_credentials()
    k = creds.get("elevenlabs_key") or ""
    if not k:
        sys.exit("FATAL: no elevenlabs_key in credentials")
    return k


def tts_one(text: str, out_path: Path, api_key: str) -> int:
    url = ELEVEN_ENDPOINT.format(voice_id=CHIPPER["voice_id"])
    body = json.dumps({
        "text": text,
        "model_id": CHIPPER["model"],
        "voice_settings": CHIPPER["voice_settings"],
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"xi-api-key": api_key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        method="POST",
    )
    log(f"  POST /v1/text-to-speech/{CHIPPER['voice_id'][:10]}... ({len(text)}c)")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.exit(f"ElevenLabs HTTP {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        sys.exit(f"ElevenLabs request failed: {e}")
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


def build_silence(duration_s: float, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r=44100:cl=mono", "-t", f"{duration_s}",
         "-c:a", "libmp3lame", "-b:a", "128k", str(dst)],
        capture_output=True, check=True,
    )


def concat_with_pauses(cue_mp3s: list[tuple[Path, float]], dst: Path) -> None:
    """Concat cue_mp3s [(mp3, gap_after_s), ...] into a single mp3."""
    scratch = dst.parent / f"_concat_{TS}"
    scratch.mkdir(exist_ok=True)
    parts = []
    for i, (mp3, gap) in enumerate(cue_mp3s):
        parts.append(mp3)
        if gap > 0 and i < len(cue_mp3s):  # no tail silence on last
            sil = scratch / f"silence_{i:02d}.mp3"
            build_silence(gap, sil)
            parts.append(sil)
    list_txt = scratch / "concat.txt"
    list_txt.write_text("\n".join(f"file '{p}'" for p in parts))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_txt),
         "-c:a", "libmp3lame", "-b:a", "128k", str(dst)],
        capture_output=True, check=True,
    )
    # Clean up scratch
    import shutil
    shutil.rmtree(scratch)


def main() -> int:
    log("=== Phase A TTS (Chipper) ===")
    api_key = load_elevenlabs_key()
    log(f"  elevenlabs key: ...{api_key[-8:]}")

    results = []
    for cue in CUES:
        out = OUT_DIR / f"phase_a_{cue['name']}.mp3"
        size = tts_one(cue["text"], out, api_key)
        dur = probe_duration(out)
        log(f"  wrote {out.name} ({size/1024:.1f} KB, {dur:.2f}s)")
        results.append({
            "name": cue["name"], "path": str(out.relative_to(PROD_ROOT.parent)),
            "bytes": size, "duration_s": round(dur, 3),
            "gap_after_s": cue["gap_after_s"],
        })

    # Build combined track for lipsync
    log("=== Combined lipsync track ===")
    combined = OUT_DIR / "phase_a_speech_combined.mp3"
    cue_tuples = [(OUT_DIR / f"phase_a_{c['name']}.mp3", c["gap_after_s"])
                  for c in CUES]
    concat_with_pauses(cue_tuples, combined)
    combined_dur = probe_duration(combined)
    log(f"  wrote {combined.name} ({combined.stat().st_size/1024:.1f} KB, "
        f"{combined_dur:.2f}s)")

    summary = {
        "cues": results,
        "combined_speech_mp3": str(combined.relative_to(PROD_ROOT.parent)),
        "combined_duration_s": round(combined_dur, 3),
    }
    log("=== DONE ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
