#!/usr/bin/env python3
"""One-shot smoke: Arlo beat_10 on canonical O3 Pro + Element + create-voice path.

Uses the same reference-to-video recipe as Tessa/Chipper (sound:true, element_list,
ElevenLabs-derived Kling create-voice via Element binding) — no WaveSpeed lipsync.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PROD = TOOLS.parent
DEPLOY_BG = (
    PROD.parent
    / ".deploy_backups"
    / "20260607T153224Z"
    / "Production"
    / "tools"
    / "beat_generator.py"
)
BEAT_ID = "bg_arc1_event1_pre_beat_10"
OUT_ROOT = PROD / "Event_1" / "kling_o3_clips" / "arlo_bound_voice_smoke"


def _load_deploy_build_prompt():
    spec = importlib.util.spec_from_file_location("deploy_beat_generator", DEPLOY_BG)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(PROD))
    spec.loader.exec_module(mod)
    return mod.build_kling_o3_prompt


def _inject_locked_voice(prompt: str, speaker: str, spoken: str) -> str:
    from tools import kling_o3_prompt as o3p

    locked = o3p.voice_block(speaker, spoken)
    lines = prompt.splitlines()
    out: list[str] = []
    replaced = False
    for line in lines:
        low = line.lower()
        if not replaced and (" says:" in low or " speaks in a " in low or "<<<voice_" in low):
            out.append(locked)
            replaced = True
        else:
            out.append(line)
    if replaced:
        return "\n".join(out)
    marker = "Children's illustrated"
    idx = prompt.find(marker)
    if idx < 0:
        return f"{prompt.rstrip()}\n\n{locked}\n"
    return f"{prompt[:idx].rstrip()}\n\n{locked}\n\n{prompt[idx:]}"


def _spoken_from_beat(beat: dict, normalize_fn) -> str:
    dialogue = (beat.get("dialogue_text") or "").strip()
    import re

    spoken = re.sub(r"\[[^\]]+\]", " ", dialogue)
    spoken = normalize_fn(re.sub(r"\s+", " ", spoken).strip())
    return spoken or normalize_fn(dialogue)


def _find_beat(obj, beat_id: str):
    if isinstance(obj, dict):
        if obj.get("beat_id") == beat_id:
            return obj
        for v in obj.values():
            found = _find_beat(v, beat_id)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_beat(v, beat_id)
            if found:
                return found
    return None


def _probe_video(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(path),
    ]
    raw = subprocess.check_output(cmd, text=True)
    streams = json.loads(raw).get("streams") or [{}]
    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    audio_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(path),
    ]
    audio = subprocess.run(audio_cmd, capture_output=True, text=True)
    has_audio = audio.returncode == 0 and "audio" in (audio.stdout or "")
    min_dim = min(width, height) if width and height else 0
    return {
        "width": width,
        "height": height,
        "min_dimension": min_dim,
        "has_audio": has_audio,
        "gate_pass": bool(has_audio and min_dim >= 720),
    }


def main() -> int:
    sys.path.insert(0, str(PROD))
    from tools.credentials_lib.credentials import load_credentials
    from tools import kling_character_registry as reg
    from tools import kling_o3_client as o3

    build_prompt = _load_deploy_build_prompt()
    deploy_bg = importlib.util.spec_from_file_location("deploy_beat_generator", DEPLOY_BG)
    deploy_mod = importlib.util.module_from_spec(deploy_bg)
    assert deploy_bg.loader is not None
    deploy_bg.loader.exec_module(deploy_mod)
    normalize_spoken = deploy_mod._kling_o3_normalize_spoken

    sidecar_path = PROD / "beat_generator_state.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    beat = _find_beat(sidecar, BEAT_ID)
    if not beat:
        raise SystemExit(f"Beat not found: {BEAT_ID}")

    char_path = (beat.get("reference_image") or {}).get("abs_path")
    bg_path = (beat.get("bg_ref_image") or {}).get("abs_path")
    if not char_path or not bg_path:
        raise SystemExit("Beat missing reference_image or bg_ref_image")

    ok, align_msg = reg.char_ref_matches_element_images(char_path, beat.get("speaker") or "Arlo")
    if not ok:
        print(f"WARN: @Image1 alignment: {align_msg}")

    speaker = beat.get("speaker") or "Arlo"
    prompt = build_prompt(beat)
    spoken = _spoken_from_beat(beat, normalize_spoken)
    prompt = _inject_locked_voice(prompt, speaker, spoken)
    duration = int(beat.get("kling_o3_duration") or 8)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{BEAT_ID}_arlo_bound_voice.mp4"

    creds = load_credentials()
    api_key = creds.get("wavespeed_key") or creds.get("wavespeed")
    if not api_key:
        raise SystemExit("Missing wavespeed API key")

    meta = {
        "beat_id": BEAT_ID,
        "speaker": speaker,
        "element": reg.get_element_list_entry(speaker),
        "kling_voice_id": reg.get_bound_voice_id(speaker),
        "elevenlabs_voice_name": (reg.get_character_entry(speaker) or {}).get("elevenlabs_voice_name"),
        "char_ref": char_path,
        "bg_ref": bg_path,
        "duration": duration,
        "voice_delivery_lock": "KLING_O3_ARLO_VOICE_DELIVERY",
        "spoken": spoken,
        "prompt_preview": prompt[:700],
        "route": "o3_pro_reference_to_video_sound_true",
    }
    (out_dir / "submit_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    print("\nSubmitting O3 Pro reference-to-video (bound voice, no lipsync)...")

    result = o3.run_beat_generation(
        api_key,
        prompt,
        char_path,
        bg_path,
        dest,
        duration=duration,
        speaker=speaker,
    )
    (out_dir / "run_result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    if not result.get("ok"):
        print("FAILED:", json.dumps(result, indent=2, default=str))
        return 1

    probe = _probe_video(dest)
    qa = {
        "beat_id": BEAT_ID,
        "video_path": str(dest),
        "probe": probe,
        "compare": {
            "lipsync_path_resolution": "832x464 (failed gate)",
            "expected": "min(width,height) >= 720 with audio",
        },
    }
    (out_dir / "qa_report.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    print("\nQA:", json.dumps(qa, indent=2))
    return 0 if probe["gate_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
