#!/usr/bin/env python3
"""Durable Arlo Beat Gen video pipeline.

Generates an Arlo visual with Kling O3, renders dialogue with Arlo's
Chipper-backed ElevenLabs voice profile, lipsyncs the visual to that audio, and
optionally applies a final sharpening pass. This replaces one-off shell snippets
used during the Chipper -> Arlo migration.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROD = HERE.parent
TOOLING_SIDE = Path("/Users/kimberlysmith/Projects/mindfulnest-tooling/Production/beat_generator_state.json")
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    _resolve_wavespeed_host,
    kling_poll_fresh,
    load_api_keys,
    robust_https_request,
)
from lipsync_sender import LIPSYNC_PROVIDER_CONTRACT, LipSyncClient  # noqa: E402
from video_delivery import encode_delivery_video, encode_lipsync_input  # noqa: E402
import beat_generator as bg_sidecar  # noqa: E402
import production_server as ps  # noqa: E402

O3_MODEL_URLS = {
    "std": "https://api.wavespeed.ai/api/v3/kwaivgi/kling-video-o3-std/reference-to-video",
    "pro": "https://api.wavespeed.ai/api/v3/kwaivgi/kling-video-o3-pro/reference-to-video",
}

LIPSYNC_HEAD_PAD_S = 0.7
LIPSYNC_TAIL_PAD_S = 2.5
LIPSYNC_MAX_PADDED_AUDIO_S = 9.9


def _ref_path(value) -> Path:
    if isinstance(value, dict):
        return Path(value.get("abs_path") or value.get("path") or value.get("local_path") or "")
    return Path(value or "")


def _mime(path: Path) -> str:
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if path.suffix.lower() == ".webp":
        return "image/webp"
    return "image/png"


def _data_uri(path: Path) -> str:
    return f"data:{_mime(path)};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _clean_bg_text(text: str) -> str:
    # Preserve bracketed emotional direction for ElevenLabs v3. The shared
    # cleaner only converts explicit [pause]/[break]/[silence] cues to
    # ellipses; stripping leading [emotion] tags made Arlo sound neutral.
    return ps._clean_text_for_tts(text)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return slug or "speaker"


def _visual_prompt(base_prompt: str, *, speaker: str) -> str:
    prompt = re.sub(
        rf"{re.escape(speaker)} speaks.*?\".*?\"",
        f"{speaker} is present as a silent visual base for later lip sync. Mouth relaxed, "
        "natural friendly expression, small idle head, ear, tail, and paw motion only.",
        base_prompt or "",
        flags=re.S,
    )
    prompt = re.sub(
        r"Audio:.*",
        "No audio, no voice, no music, no soundtrack. Silent visual-only base clip for later ElevenLabs lip sync.",
        prompt,
        flags=re.S,
    )
    prompt += (
        "\n\nSilent visual base only: do not generate speech or sound. "
        f"Keep {speaker} centered and visible for later lip sync.\n"
        "Preserve crisp character-detail from @Image1: sharp eyes, defined fur tufts, "
        "clean clothing folds, crisp edges, detailed character silhouette. "
        "Avoid soft focus, blur, painterly smearing, low-detail fur, or washed-out features."
    )
    return prompt


def _submit_o3(*, api_key: str, model: str, character: Path, background: Path, prompt: str, duration: int) -> tuple[str, dict]:
    payload = {
        "images": [_data_uri(character), _data_uri(background)],
        "prompt": prompt,
        "sound": False,
        "keep_original_sound": False,
        "duration": duration,
        "aspect_ratio": "16:9",
        "shot_type": "customize",
    }
    resolved_ip = _resolve_wavespeed_host("api.wavespeed.ai")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        tmp.write(json.dumps(payload).encode("utf-8"))
        tmp_path = tmp.name
    try:
        cmd = [
            "curl", "-s", "-S", "--http1.1", "--max-time", "120",
            "-X", "POST",
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "Content-Type: application/json",
            "-H", "Connection: close",
            "-w", "\n__STATUS__%{http_code}",
            "-d", f"@{tmp_path}",
        ]
        if resolved_ip:
            cmd += ["--resolve", f"api.wavespeed.ai:443:{resolved_ip}"]
        cmd.append(O3_MODEL_URLS[model])
        result = subprocess.run(cmd, capture_output=True, timeout=140)
        marker = b"\n__STATUS__"
        idx = result.stdout.rfind(marker)
        if idx < 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace") or "curl returned no status marker")
        status = int(result.stdout[idx + len(marker):].strip())
        raw = result.stdout[:idx]
        body = json.loads(raw.decode("utf-8"))
        if status >= 400:
            raise RuntimeError(f"O3 {model} submit HTTP {status}: {raw[:1000].decode('utf-8', 'replace')}")
        task_id = (body.get("data") or {}).get("id") or body.get("id") or body.get("task_id")
        if not task_id:
            raise RuntimeError(f"O3 {model} submit returned no task id: {body}")
        return str(task_id), body
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _write_elevenlabs_audio(*, event_dir: Path, beat_id: str, speaker: str, text: str, keys: dict) -> tuple[Path, dict, str, float]:
    profile = ps._resolve_voice_profile(speaker)
    if not profile or not profile.get("voice_id"):
        raise RuntimeError(f"No voice profile for {speaker}: {profile}")
    voice_settings = {
        k: float(profile[k])
        for k in ("stability", "similarity_boost", "style", "speed")
        if profile.get(k) is not None
    }
    model = profile.get("model") or "eleven_v3"
    audio_dir = event_dir / "story_scene_tts_v2/storyboard_v59_prod"
    audio_dir.mkdir(parents=True, exist_ok=True)
    match = re.search(r"_beat_(\d+)", beat_id)
    beat_num = match.group(1) if match else "xx"
    audio = audio_dir / f"line_{beat_num}_{_safe_slug(speaker)}_voice.mp3"
    body = json.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": voice_settings,
    }).encode("utf-8")
    status, audio_bytes = robust_https_request(
        host="api.elevenlabs.io",
        path=f"/v1/text-to-speech/{profile['voice_id']}",
        method="POST",
        headers={
            "xi-api-key": keys["elevenlabs"],
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        body=body,
        timeout=90,
        max_retries=3,
    )
    if status >= 400:
        raise RuntimeError(f"ElevenLabs HTTP {status}: {audio_bytes[:500]!r}")
    audio.write_bytes(audio_bytes)
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio),
    ], text=True).strip())
    return audio, profile, model, dur


def _media_duration(path: Path) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], text=True).strip())


def _make_lipsync_padded_audio(audio: Path, *, audio_dur: float) -> tuple[Path, dict]:
    """Pad lipsync submission audio so Kling has neutral lead-in and face-return tail.

    The unpadded ElevenLabs MP3 remains the source-of-truth voice artifact. This
    derivative is only for Kling lipsync timing: Kling returns output near audio
    length, so sending raw speech causes the video to cut at the final phoneme or
    mid-blink. The tail pad restores the older Beat Gen invariant that lipsync
    clips include settle time after speech.
    """
    head_s = LIPSYNC_HEAD_PAD_S
    tail_s = min(LIPSYNC_TAIL_PAD_S, max(0.0, LIPSYNC_MAX_PADDED_AUDIO_S - audio_dur - head_s))
    if tail_s < 0.5:
        raise RuntimeError(
            f"Audio {audio_dur:.2f}s leaves only {tail_s:.2f}s lipsync tail; "
            "shorten dialogue or split the beat so face-return padding is preserved."
        )
    padded = audio.with_name(audio.stem + "_lipsync_padded.mp3")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-t", f"{head_s:.3f}", "-i", "anullsrc=r=44100:cl=mono",
        "-i", str(audio),
        "-f", "lavfi", "-t", f"{tail_s:.3f}", "-i", "anullsrc=r=44100:cl=mono",
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
        "-map", "[out]",
        "-codec:a", "libmp3lame", "-q:a", "2",
        str(padded),
    ], check=True, timeout=60)
    padded_dur = _media_duration(padded)
    return padded, {
        "source_audio_path": str(audio),
        "lipsync_audio_path": str(padded),
        "source_audio_duration_s": round(audio_dur, 3),
        "head_pad_s": round(head_s, 3),
        "tail_pad_s": round(tail_s, 3),
        "padded_audio_duration_s": round(padded_dur, 3),
        "rule": "Lipsync audio is padded so Kling output includes lead-in and face-return tail.",
    }


def _delivery_video(src: Path, *, sharpen: bool) -> Path:
    dst = src.with_name(src.stem + "_delivery.mp4")
    return encode_delivery_video(src, dst, include_audio=True, sharpen=sharpen)


def _probe_video_size(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    return int(stream.get("width") or 0), int(stream.get("height") or 0)


def _has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return bool(json.loads(result.stdout).get("streams"))


def _ensure_lipsync_audio(path: Path, audio: Path) -> tuple[Path, dict]:
    """Kling lipsync should include audio, but never approve video-only output.

    Some providers return a video track with mouth motion but omit audio. In
    that case, keep the lipsynced video frames and mux the exact padded
    ElevenLabs audio used for the lipsync request back into the MP4.
    """
    if _has_audio_stream(path):
        return path, {
            "audio_present": True,
            "audio_source": "kling_lipsync_output",
            "path": str(path),
        }
    muxed = path.with_name(path.stem + "_with_padded_audio.mp4")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(path),
        "-i", str(audio),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(muxed),
    ], check=True, timeout=120)
    return muxed, {
        "audio_present": False,
        "audio_source": "muxed_padded_elevenlabs_audio",
        "path": str(muxed),
        "source_video_path": str(path),
        "source_audio_path": str(audio),
    }


def _assert_lipsync_quality(path: Path) -> dict:
    width, height = _probe_video_size(path)
    result = {
        "path": str(path),
        "width": width,
        "height": height,
        "min_dimension": min(width, height),
        "rule": "Kling LipSync output must stay at >=720p before delivery encode.",
    }
    if min(width, height) < 720:
        raise RuntimeError(
            f"Kling LipSync returned sub-720p output {width}x{height}; "
            "refusing to approve soft/upscaled delivery video."
        )
    return result


def _lipsync_failure_message(result: dict) -> str:
    raw = result.get("raw") if isinstance(result.get("raw"), dict) else result
    return str(raw.get("error") or result.get("error") or raw)[:2000]


def _should_retry_lipsync_with_data_uri(result: dict) -> bool:
    msg = _lipsync_failure_message(result).lower()
    return (
        "could not download the input" in msg
        or "queued_timeout" in msg
        or "queued timeout" in msg
        or "without_retry" in msg
    )


def _submit_and_poll_lipsync_with_fallback(
    client: LipSyncClient,
    *,
    lipsync_input: Path,
    lipsync_audio: Path,
    keys: dict,
    beat_id: str,
    beat: dict,
    persist,
) -> tuple[str, dict, str]:
    """Submit Kling lipsync with schema-compliant URL transport first.

    WaveSpeed's current schema says video/audio must be URLs. Data URI
    submissions are accepted by the endpoint but have repeatedly returned
    degraded 832x464 output from valid 1080p input, so the fallback is disabled
    by default for Beat Gen quality-sensitive runs.
    """
    attempts = ["url"]
    if os.environ.get("MINDFULNEST_ALLOW_LOW_QUALITY_LIPSYNC_DATA_URI_FALLBACK") == "1":
        attempts.append("data_uri")
    last_result: dict | None = None
    last_task = ""
    for index, transport in enumerate(attempts):
        print(json.dumps({
            "phase": "lipsync_submit",
            "beat_id": beat_id,
            "transport": transport,
        }), flush=True)
        try:
            lipsync_task = client.submit(lipsync_input, lipsync_audio, transport=transport)
        except Exception as exc:
            persist({
                "kling_o3_voice_fix_status": "failed_provider_fetch",
                "kling_o3_voice_fix_phase": "lipsync_submit",
                "kling_o3_voice_fix_error_code": "PROVIDER_FETCH_OR_HOSTING",
                "kling_o3_voice_fix_error": str(exc),
                "kling_o3_voice_fix_lipsync_transport": transport,
                "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
            }, remove=("kling_o3_voice_fix_ui_job_id",))
            raise
        last_task = lipsync_task
        fields = {
            "kling_o3_voice_fix_task_id": lipsync_task,
            "kling_o3_voice_fix_lipsync_transport": transport,
            "kling_o3_voice_fix_phase": "lipsync_poll",
            "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if transport == "url":
            fields["kling_o3_voice_fix_url_preflight"] = getattr(client, "last_url_transport_preflight", None)
        persist(fields)
        print(json.dumps({
            "phase": "lipsync_poll",
            "beat_id": beat_id,
            "task_id": lipsync_task,
            "transport": transport,
        }), flush=True)
        result = kling_poll_fresh(lipsync_task, keys["wavespeed"], timeout_s=900)
        last_result = result
        if (result.get("status") or "").lower() == "completed":
            return lipsync_task, result, transport
        if index == 0 and len(attempts) > 1 and _should_retry_lipsync_with_data_uri(result):
            persist({
                "kling_o3_voice_fix_url_transport_error": _lipsync_failure_message(result),
                "kling_o3_voice_fix_status": "lipsync_retrying_data_uri",
                "kling_o3_voice_fix_phase": "lipsync_retry",
                "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
            })
            print(json.dumps({
                "phase": "lipsync_retry",
                "beat_id": beat_id,
                "from": "url",
                "to": "data_uri",
                "reason": _lipsync_failure_message(result),
            }), flush=True)
            continue
        if index == 0 and _should_retry_lipsync_with_data_uri(result):
            persist({
                "kling_o3_voice_fix_url_transport_error": _lipsync_failure_message(result),
                "kling_o3_voice_fix_status": "failed_provider_fetch",
                "kling_o3_voice_fix_error_code": "PROVIDER_FETCH_FAILED",
                "kling_o3_voice_fix_error": (
                "WaveSpeed could not download the temporary lipsync URL. "
                "Data-URI fallback is disabled because it returns sub-720p 832x464 output."
                ),
                "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
            }, remove=("kling_o3_voice_fix_ui_job_id",))
        return lipsync_task, result, transport
    return last_task, last_result or {"status": "failed", "error": "lipsync failed before polling"}, attempts[-1]


def _o3_option_key(beat_id: str, video_path: str) -> str:
    digest = re.sub(r"[^a-f0-9]", "", __import__("hashlib").sha1(video_path.encode("utf-8")).hexdigest())[:10]
    return f"{beat_id}_o3_video_{digest}"


def _is_user_selectable_o3_video(video_path: str) -> bool:
    name = Path(video_path or "").name.lower()
    return bool(video_path) and not any(
        marker in name
        for marker in (
            "_silent_o3_base",
            "_delivery_input",
            "_noaudio",
        )
    )


def _upsert_o3_option(beat: dict, *, video_path: str, label: str, active: bool, now: str) -> None:
    if not _is_user_selectable_o3_video(video_path):
        return
    import beat_generator as bg  # noqa: PLC0415

    slot_index = int(beat.get("kling_o3_replace_slot_index") or 0)
    bg.assign_kling_o3_option_to_slot(
        beat,
        slot_index,
        video_path=video_path,
        label=label,
        source="kling_o3_voice_video",
        now=now,
        make_active=active,
    )


def _restore_prior_video_state(beat: dict, *, prior_video: str | None, prior_status: str | None, prior_beat_status: str | None) -> None:
    if prior_video:
        beat["kling_o3_video_path"] = str(prior_video)
        beat["kling_o3_status"] = "approved" if prior_status in {"approved", "visual_running", "visual_ready"} else (prior_status or "approved")
        beat["status"] = "approved" if (prior_beat_status or "").endswith("_running") or prior_status == "approved" else (prior_beat_status or "approved")
    else:
        beat["status"] = "arlo_lipsync_failed"
        beat["kling_o3_status"] = "failed"


def _find_beat(sidecar: dict, beat_id: str) -> tuple[dict, str] | None:
    for arc in (sidecar.get("arcs") or {}).values():
        for segment_key, segment in (arc.get("segments") or {}).items():
            for beat in segment.get("beats") or []:
                if isinstance(beat, dict) and beat.get("beat_id") == beat_id:
                    return beat, str(segment_key)
    return None


def _event_dir_for_segment(segment_key: str) -> Path:
    match = re.match(r"event_(\d+)_", segment_key or "")
    if match:
        return PROD / f"Event_{match.group(1)}"
    return PROD / "Event_1"


def run_pipeline(beat_id: str, *, model: str = "pro", sharpen: bool = True, attempt_id: str | None = None) -> dict:
    attempt_id = attempt_id or os.environ.get("MN_O3_ATTEMPT_ID") or __import__("uuid").uuid4().hex
    print(json.dumps({"phase": "starting", "beat_id": beat_id, "model": model, "sharpen": sharpen, "attempt_id": attempt_id}), flush=True)
    sidecar = PROD / "beat_generator_state.json"
    sc = json.loads(sidecar.read_text(encoding="utf-8"))
    found = _find_beat(sc, beat_id)
    beat = found[0] if found else None
    if not beat:
        raise RuntimeError(f"beat not found: {beat_id}")
    event_dir = _event_dir_for_segment(found[1] if found else "")
    backup_dir = event_dir / "_arlo_migration_backups" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"_pre_arlo_pipeline_{beat_id}"
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sidecar, backup_dir / "beat_generator_state.json")
    speaker = (beat.get("speaker") or "").strip()
    if not speaker:
        raise RuntimeError(f"{beat_id} has no speaker")
    speaker_slug = _safe_slug(speaker)
    now = datetime.now(timezone.utc).isoformat()
    prior_video = beat.get("kling_o3_video_path")
    prior_status = beat.get("kling_o3_status")
    prior_beat_status = beat.get("status")
    if _is_user_selectable_o3_video(str(prior_video or "")):
        _upsert_o3_option(beat, video_path=str(prior_video), label="previous approved O3 video", active=True, now=now)

    def persist(fields: dict | None = None, *, remove: tuple[str, ...] = (), expected: bool = True) -> None:
        """Persist only this beat's changed fields under the shared sidecar lock."""
        if fields:
            beat.update(fields)
        for key in remove:
            beat.pop(key, None)

        def apply(current: dict, _sidecar: dict) -> None:
            if fields:
                current.update(fields)
            for key in remove:
                current.pop(key, None)

        ok, _current = bg_sidecar.update_beat_locked(
            beat_id,
            apply,
            expected_attempt_id=attempt_id if expected else None,
        )
        if not ok and expected:
            raise RuntimeError(f"{beat_id} attempt {attempt_id} was superseded before sidecar update")

    keys = load_api_keys()
    char = _ref_path(beat.get("reference_image"))
    bg = _ref_path(beat.get("bg_ref_image"))
    if not char.is_file():
        raise FileNotFoundError(f"char ref missing: {char}")
    if not bg.is_file():
        raise FileNotFoundError(f"bg ref missing: {bg}")
    spoken = _clean_bg_text(beat.get("dialogue_text") or "")
    print(json.dumps({"phase": "tts_start", "beat_id": beat_id, "spoken_text": spoken}), flush=True)
    audio, profile, voice_model, audio_dur = _write_elevenlabs_audio(event_dir=event_dir, beat_id=beat_id, speaker=speaker, text=spoken, keys=keys)
    lipsync_audio, lipsync_padding = _make_lipsync_padded_audio(audio, audio_dur=audio_dur)
    duration = max(
        int(beat.get("kling_o3_duration") or 8),
        min(10, math.ceil(float(lipsync_padding["padded_audio_duration_s"]) + 0.25)),
    )

    persist({
        "status": "arlo_o3_visual_running",
        "kling_o3_status": "visual_running",
        "kling_o3_voice_fix_attempt_id": attempt_id,
        "kling_o3_voice_fix_status": "tts_ready",
        "kling_o3_voice_fix_phase": "tts",
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
        "kling_o3_voice_fix_audio_path": str(audio),
        "kling_o3_voice_fix_lipsync_audio_path": str(lipsync_audio),
        "kling_o3_voice_fix_lipsync_padding": lipsync_padding,
        "kling_o3_voice_fix_voice_id": profile["voice_id"],
        "kling_o3_voice_fix_spoken_text": spoken,
        "kling_o3_voice_fix_audio_duration_s": round(audio_dur, 3),
        "kling_o3_model": model,
    }, expected=False)

    print(json.dumps({"phase": "o3_submit", "beat_id": beat_id, "duration": duration}), flush=True)
    o3_task, submit_response = _submit_o3(
        api_key=keys["wavespeed"],
        model=model,
        character=char,
        background=bg,
        prompt=_visual_prompt(beat.get("kling_o3_prompt") or "", speaker=speaker),
        duration=duration,
    )
    persist({
        "kling_o3_task_id": o3_task,
        "kling_o3_submit_response": submit_response,
        "kling_o3_voice_fix_status": "visual_running",
        "kling_o3_voice_fix_phase": "o3",
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
    })

    print(json.dumps({"phase": "o3_poll", "beat_id": beat_id, "task_id": o3_task}), flush=True)
    o3_result = kling_poll_fresh(o3_task, keys["wavespeed"], timeout_s=900)
    if (o3_result.get("status") or "").lower() != "completed":
        persist({
            "status": "approved" if prior_video else "arlo_o3_failed",
            "kling_o3_status": "approved" if prior_video else "failed",
            "kling_o3_voice_fix_status": "failed_o3",
            "kling_o3_voice_fix_error_code": "O3_FAILED",
            "kling_o3_voice_fix_error": json.dumps(o3_result)[:1000],
            "kling_o3_error": json.dumps(o3_result)[:1000],
            "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
        }, remove=("kling_o3_voice_fix_ui_job_id",))
        raise RuntimeError(f"O3 failed: {o3_result}")

    client = LipSyncClient(keys["wavespeed"])
    clips_dir = event_dir / "kling_o3_clips"
    base = clips_dir / f"{beat_id}_{speaker_slug}_{model}_silent_o3_base.mp4"
    client.download((o3_result.get("outputs") or [None])[0], base)
    silent = clips_dir / f"{beat_id}_{speaker_slug}_{model}_silent_o3_base_noaudio.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-an", "-c:v", "copy", str(silent)], check=True, timeout=60)
    lipsync_input = clips_dir / f"{beat_id}_{speaker_slug}_{model}_silent_o3_base_delivery_input.mp4"
    encode_lipsync_input(silent, lipsync_input)

    running_fields = {
        "status": "arlo_lipsync_running",
        "kling_o3_status": "visual_ready",
    }
    # Keep silent/intermediate lipsync input out of the visible O3 option slots.
    # If a prior approved clip exists, it remains the active preview while this
    # replacement attempt is running or if it later fails.
    remove = ("kling_o3_video_path",) if not prior_video else ()
    running_fields.update({
        "kling_o3_poll_result": o3_result,
        "kling_o3_voice_fix_status": "lipsync_running",
        "kling_o3_voice_fix_phase": "lipsync",
        "kling_o3_voice_fix_updated_at": datetime.now(timezone.utc).isoformat(),
        "kling_o3_voice_fix_base_video_path": str(base),
        "kling_o3_voice_fix_silent_video_path": str(silent),
        "kling_o3_voice_fix_lipsync_input_path": str(lipsync_input),
        "kling_o3_voice_fix_lipsync_input_profile": {
            "resolution": "1920x1080",
            "reason": "Kling LipSync has no resolution parameter; submit 1080p as best source and reject any sub-720p provider output.",
        },
        "kling_o3_voice_fix_provider_contract": LIPSYNC_PROVIDER_CONTRACT,
    })
    persist(running_fields, remove=remove)

    try:
        lipsync_task, lipsync_result, lipsync_transport = _submit_and_poll_lipsync_with_fallback(
            client,
            lipsync_input=lipsync_input,
            lipsync_audio=lipsync_audio,
            keys=keys,
            beat_id=beat_id,
            beat=beat,
            persist=persist,
        )
    except Exception:
        _restore_prior_video_state(beat, prior_video=prior_video, prior_status=prior_status, prior_beat_status=prior_beat_status)
        persist({
            "status": beat.get("status"),
            "kling_o3_status": beat.get("kling_o3_status"),
            "kling_o3_video_path": beat.get("kling_o3_video_path"),
        }, remove=("kling_o3_voice_fix_ui_job_id",))
        raise
    if (lipsync_result.get("status") or "").lower() != "completed":
        _restore_prior_video_state(beat, prior_video=prior_video, prior_status=prior_status, prior_beat_status=prior_beat_status)
        persist({
            "status": beat.get("status"),
            "kling_o3_status": beat.get("kling_o3_status"),
            "kling_o3_video_path": beat.get("kling_o3_video_path"),
            "kling_o3_voice_fix_status": "failed_provider_fetch",
            "kling_o3_voice_fix_error_code": "PROVIDER_LIPSYNC_FAILED",
            "kling_o3_voice_fix_error": json.dumps(lipsync_result)[:1000],
            "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
        }, remove=("kling_o3_voice_fix_ui_job_id",))
        raise RuntimeError(f"lipsync failed: {lipsync_result}")

    out = clips_dir / f"{beat_id}_{speaker_slug}_voice_lipsync.mp4"
    client.download((lipsync_result.get("outputs") or [None])[0], out)
    out, lipsync_audio_check = _ensure_lipsync_audio(out, lipsync_audio)
    try:
        lipsync_quality = _assert_lipsync_quality(out)
    except Exception as exc:
        _restore_prior_video_state(beat, prior_video=prior_video, prior_status=prior_status, prior_beat_status=prior_beat_status)
        width, height = _probe_video_size(out)
        persist({
            "status": beat.get("status"),
            "kling_o3_status": beat.get("kling_o3_status"),
            "kling_o3_video_path": beat.get("kling_o3_video_path"),
            "kling_o3_voice_fix_status": "failed_provider_sub720",
            "kling_o3_voice_fix_error_code": "PROVIDER_SUB720",
            "kling_o3_voice_fix_error": str(exc),
            "kling_o3_voice_fix_output_profile": {
                "path": str(out),
                "width": width,
                "height": height,
                "min_dimension": min(width, height),
            },
            "kling_o3_voice_fix_completed_at": datetime.now(timezone.utc).isoformat(),
        }, remove=("kling_o3_voice_fix_ui_job_id",))
        raise
    active = _delivery_video(out, sharpen=sharpen)
    print(json.dumps({"phase": "finalize", "beat_id": beat_id, "video": str(active)}), flush=True)
    out_dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(active),
    ], text=True).strip())
    now = datetime.now(timezone.utc).isoformat()
    final_fields = {
        "kling_o3_video_path": str(active),
        "kling_o3_status": "approved",
        "status": "approved",
        "kling_o3_completed_at": now,
        "kling_o3_voice_fix_status": "approved",
        "kling_o3_voice_fix_phase": "finalize",
        "kling_o3_voice_fix_lipsync_transport": lipsync_transport,
        "kling_o3_voice_fix_completed_at": now,
        "kling_o3_voice_fix_result": lipsync_result,
        "kling_o3_voice_fix_lipsync_quality": lipsync_quality,
        "kling_o3_voice_fix_output_profile": lipsync_quality,
        "kling_o3_voice_fix_lipsync_audio_check": lipsync_audio_check,
        "kling_o3_voice_fix_lipsync_padding": lipsync_padding,
        "kling_o3_voice_fix_base_video_path": str(base),
        "kling_o3_voice_fix_silent_video_path": str(silent),
        "kling_o3_voice_fix_lipsync_input_path": str(lipsync_input),
        "kling_o3_voice_fix_lipsync_input_profile": {
            "resolution": "1920x1080",
            "reason": "Kling LipSync has no resolution parameter; submit 1080p as best source and reject any sub-720p provider output.",
        },
        "kling_o3_voice_fix_provider_contract": LIPSYNC_PROVIDER_CONTRACT,
        "kling_o3_voice_fix_output_duration_s": round(out_dur, 3),
    }
    beat.update(final_fields)
    _upsert_o3_option(beat, video_path=str(active), label="latest O3 voice video", active=True, now=now)
    final_fields["kling_o3_options"] = beat.get("kling_o3_options")
    final_fields["arlo_visual_quality"] = {
        "speaker": speaker,
        "model": model,
        "delivery_profile": "LD-296/LD-284 kid-facing 1280x720 H.264 High yuv420p 24fps <=1.9Mbps +faststart",
        "sharpened_delivery": sharpen,
        "o3_master_video_path": str(base),
        "o3_silent_master_video_path": str(silent),
        "lipsync_input_video_path": str(lipsync_input),
        "lipsync_master_video_path": str(out),
        "lipsync_master_quality": lipsync_quality,
        "lipsync_audio_check": lipsync_audio_check,
        "playback_video_path": str(active),
        "active_video_path": str(active),
        "method": "O3 Pro visual master + LD-296 720p lipsync input + ElevenLabs Chipper voice + Kling lipsync + compact delivery encode",
        "applied_at": now,
    }
    persist(final_fields, remove=("kling_o3_voice_fix_ui_job_id", "kling_o3_voice_fix_error", "kling_o3_voice_fix_error_code"))
    bg_sidecar.auto_pin_approved_kling_o3_delivery(beat, event_dir)
    if TOOLING_SIDE.parent.exists():
        shutil.copy2(sidecar, TOOLING_SIDE)
    return {
        "ok": True,
        "beat_id": beat_id,
        "video": str(active),
        "duration_s": round(out_dur, 3),
        "voice_id": profile["voice_id"],
        "voice_model": voice_model,
        "o3_model": model,
        "o3_task_id": o3_task,
        "lipsync_task_id": lipsync_task,
        "sharpened": sharpen,
        "playback_video": str(active),
        "master_video": str(out),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beat-id", required=True)
    parser.add_argument("--model", choices=sorted(O3_MODEL_URLS), default="pro")
    parser.add_argument("--no-sharpen", action="store_true")
    parser.add_argument("--attempt-id", default=None)
    args = parser.parse_args()
    print(json.dumps(run_pipeline(args.beat_id, model=args.model, sharpen=not args.no_sharpen, attempt_id=args.attempt_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
