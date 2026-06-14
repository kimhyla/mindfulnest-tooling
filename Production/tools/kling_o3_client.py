"""Kling O3 STD reference-to-video client (WaveSpeed).

Validated recipe: Production/tools/test_kling_o3_omni_voice_speed_v2.py
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

ENDPOINT_STD = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-video-o3-std/reference-to-video"
ENDPOINT_PRO = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-video-o3-pro/reference-to-video"
ENDPOINT_STD_ITV = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-video-o3-std/image-to-video"
ENDPOINT_PRO_ITV = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-video-o3-pro/image-to-video"
POLL_TIMEOUT_S = int(os.environ.get("KLING_O3_POLL_TIMEOUT_S", "1800"))
POLL_TIMEOUT_RETRY_S = int(os.environ.get("KLING_O3_POLL_TIMEOUT_RETRY_S", "900"))
POLL_INTERVAL_S = 10
POLL_TRANSIENT_HTTP = (429, 500, 502, 503, 504)
POLL_TRANSIENT_MAX_RETRIES = int(os.environ.get("KLING_O3_POLL_TRANSIENT_RETRIES", "12"))
POLL_TRANSIENT_BACKOFF_S = (3, 6, 12, 24, 30, 45, 60, 90, 120, 120, 150, 180)

KLING_O3_AUDIO_LOCK = (
    "Audio: spoken character dialogue only — absolutely no background music, "
    "no ambient bed, no forest ambience, no nature sounds, no environmental audio, "
    "no soundtrack, no score, no music of any kind. Silent world except speech."
)


def ensure_kling_o3_speech_only_prompt(prompt: str) -> str:
    """Append or upgrade speech-only audio lock (manual or auto prompts)."""
    text = (prompt or "").rstrip()
    lower = text.lower()
    if "silent world except speech" in lower or "forest ambience" in lower:
        return text
    if "no background music" in lower:
        text = re.sub(
            r"\n\nAudio: character dialogue and voice only[^\n]*(?:\n[^\n@][^\n]*)*",
            "",
            text,
            flags=re.IGNORECASE,
        ).rstrip()
    return f"{text}\n\n{KLING_O3_AUDIO_LOCK}"


def resolve_wavespeed_host(host: str = "api.wavespeed.ai") -> str | None:
    for resolver in ("8.8.8.8", "1.1.1.1"):
        try:
            r = subprocess.run(
                ["dig", "+short", "+time=3", "+tries=1", f"@{resolver}", host],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", line):
                    return line
        except (subprocess.TimeoutExpired, OSError):
            continue
    try:
        import socket

        return socket.gethostbyname(host)
    except OSError:
        return None


def image_to_data_uri(path: str | Path) -> str:
    p = Path(path)
    data = p.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    ext = p.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return f"data:image/{mime};base64,{b64}"


def curl_json(method: str, url: str, api_key: str, payload: dict | None = None) -> tuple[int, dict]:
    cmd = [
        "curl", "-s", "-S", "--http1.1", "--max-time", "90",
        "-X", method,
        "-H", f"Authorization: Bearer {api_key}",
        "-H", "Connection: close",
        "-w", "\n__STATUS__%{http_code}",
    ]
    tmp_path: str | None = None
    if payload is not None:
        cmd += ["-H", "Content-Type: application/json"]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            tmp.write(json.dumps(payload).encode("utf-8"))
            tmp_path = tmp.name
        cmd += ["-d", f"@{tmp_path}"]

    resolved_ip = resolve_wavespeed_host()
    if resolved_ip:
        cmd += ["--resolve", f"api.wavespeed.ai:443:{resolved_ip}"]
    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=100)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    raw = result.stdout
    marker = b"\n__STATUS__"
    idx = raw.rfind(marker)
    if idx < 0:
        raise RuntimeError(f"curl failed: {result.stderr.decode(errors='replace')}")
    status = int(raw[idx + len(marker):].strip())
    body_raw = raw[:idx].decode("utf-8", errors="replace")
    try:
        body = json.loads(body_raw) if body_raw.strip() else {}
    except json.JSONDecodeError:
        body = {"raw": body_raw[:2000]}
    return status, body


def submit_image_to_video_startend(
    api_key: str,
    prompt: str,
    start_image_path: str | Path,
    end_image_path: str | Path,
    duration: int = 5,
    speaker: str | None = None,
    *,
    sound: bool = False,
    tier: str | None = None,
) -> tuple[str, str]:
    """Submit O3 Omni image-to-video with start + end frames.

    Uses O3 Pro when speaker has an active Element (or tier='pro'), else Std.
    """
    from tools import kling_character_registry as reg

    element_entry = reg.get_element_list_entry(speaker or "")
    use_pro = tier == "pro" or (tier is None and element_entry)
    endpoint = ENDPOINT_PRO_ITV if use_pro else ENDPOINT_STD_ITV
    resolved_tier = "pro" if use_pro else "std"

    payload: dict = {
        "image": image_to_data_uri(start_image_path),
        "end_image": image_to_data_uri(end_image_path),
        "prompt": prompt,
        "duration": duration,
        "sound": sound,
        "shot_type": "customize",
    }
    if element_entry:
        payload["element_list"] = [element_entry]

    status, body = curl_json("POST", endpoint, api_key, payload)
    if status >= 400:
        raise RuntimeError(
            f"Kling O3 {resolved_tier} image-to-video HTTP {status}: {json.dumps(body)[:1500]}"
        )
    task_id = body.get("data", {}).get("id") or body.get("id")
    if not task_id:
        raise RuntimeError(f"No task_id in response: {body}")
    return task_id, resolved_tier


def submit_image_to_video_single(
    api_key: str,
    prompt: str,
    start_image_path: str | Path,
    duration: int = 7,
    speaker: str | None = None,
    *,
    sound: bool = False,
    tier: str | None = None,
) -> tuple[str, str]:
    """Submit O3 Omni image-to-video from one start frame (no end_image).

    Prefer this over start+end when natural character motion is the goal.
    """
    from tools import kling_character_registry as reg

    element_entry = reg.get_element_list_entry(speaker or "")
    use_pro = tier == "pro" or (tier is None and element_entry)
    endpoint = ENDPOINT_PRO_ITV if use_pro else ENDPOINT_STD_ITV
    resolved_tier = "pro" if use_pro else "std"

    payload: dict = {
        "image": image_to_data_uri(start_image_path),
        "prompt": prompt,
        "duration": duration,
        "sound": sound,
        "shot_type": "customize",
    }
    if element_entry:
        payload["element_list"] = [element_entry]

    status, body = curl_json("POST", endpoint, api_key, payload)
    if status >= 400:
        raise RuntimeError(
            f"Kling O3 {resolved_tier} image-to-video HTTP {status}: {json.dumps(body)[:1500]}"
        )
    task_id = body.get("data", {}).get("id") or body.get("id")
    if not task_id:
        raise RuntimeError(f"No task_id in response: {body}")
    return task_id, resolved_tier


def run_single_image_generation(
    api_key: str,
    prompt: str,
    start_image_path: str | Path,
    dest_mp4: Path,
    duration: int = 7,
    speaker: str | None = None,
    *,
    sound: bool = False,
    tier: str | None = None,
) -> dict:
    """Poll O3 Omni single-image image-to-video through to downloaded MP4."""
    task_id, resolved_tier = submit_image_to_video_single(
        api_key,
        prompt,
        start_image_path,
        duration=duration,
        speaker=speaker,
        sound=sound,
        tier=tier,
    )
    result = poll_until_done(task_id, api_key)
    status = (result.get("status") or "").lower()
    if status != "completed":
        return {"ok": False, "task_id": task_id, "status": status, "tier": resolved_tier, "result": result}
    url = extract_output_url(result)
    if not url:
        return {"ok": False, "task_id": task_id, "status": "no_output_url", "tier": resolved_tier, "result": result}
    download_mp4(url, dest_mp4)
    return {
        "ok": True,
        "task_id": task_id,
        "tier": resolved_tier,
        "video_path": str(dest_mp4),
        "video_url": url,
        "status": status,
        "mode": "o3_image_to_video_single",
    }


def submit_reference_to_video(
    api_key: str,
    prompt: str,
    char_image_path: str | Path,
    bg_image_path: str | Path,
    duration: int = 8,
    speaker: str | None = None,
) -> tuple[str, str]:
    """Submit O3 reference-to-video. Uses O3 Pro when speaker has active Element."""
    from tools import kling_character_registry as reg

    element_entry = reg.get_element_list_entry(speaker or "")
    endpoint = ENDPOINT_PRO if element_entry else ENDPOINT_STD
    tier = "pro" if element_entry else "std"

    payload = {
        "prompt": ensure_kling_o3_speech_only_prompt(prompt),
        "images": [image_to_data_uri(char_image_path), image_to_data_uri(bg_image_path)],
        "sound": True,
        "keep_original_sound": False,
        "duration": duration,
        "aspect_ratio": "16:9",
        "shot_type": "customize",
    }
    if element_entry:
        payload["element_list"] = [element_entry]

    status, body = curl_json("POST", endpoint, api_key, payload)
    if status >= 400:
        raise RuntimeError(
            f"Kling O3 {tier} submit HTTP {status}: {json.dumps(body)[:1500]}"
        )
    task_id = body.get("data", {}).get("id") or body.get("id")
    if not task_id:
        raise RuntimeError(f"No task_id in response: {body}")
    return task_id, tier


def is_transient_poll_http(status: int) -> bool:
    return status in POLL_TRANSIENT_HTTP


def _poll_result_url(task_id: str) -> str:
    return f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"


def _poll_once_with_transient_retry(
    url: str,
    api_key: str,
    *,
    label: str = "poll",
) -> tuple[int, dict]:
    """GET poll with backoff on WaveSpeed gateway 5xx / curl transport failures."""
    transient_attempt = 0
    while True:
        try:
            status, body = curl_json("GET", url, api_key)
        except RuntimeError as exc:
            transient_attempt += 1
            if transient_attempt > POLL_TRANSIENT_MAX_RETRIES:
                raise RuntimeError(f"{label} transport failed after retries: {exc}") from exc
            wait_s = POLL_TRANSIENT_BACKOFF_S[
                min(transient_attempt - 1, len(POLL_TRANSIENT_BACKOFF_S) - 1)
            ]
            print(
                f"[kling-o3] {label} transport error attempt {transient_attempt}/"
                f"{POLL_TRANSIENT_MAX_RETRIES}: {exc} — retry in {wait_s}s",
                flush=True,
            )
            time.sleep(wait_s)
            continue

        if status < 400 or not is_transient_poll_http(status):
            return status, body

        transient_attempt += 1
        if transient_attempt > POLL_TRANSIENT_MAX_RETRIES:
            return status, body
        wait_s = POLL_TRANSIENT_BACKOFF_S[
            min(transient_attempt - 1, len(POLL_TRANSIENT_BACKOFF_S) - 1)
        ]
        print(
            f"[kling-o3] {label} HTTP {status} attempt {transient_attempt}/"
            f"{POLL_TRANSIENT_MAX_RETRIES} — retry in {wait_s}s",
            flush=True,
        )
        time.sleep(wait_s)


def poll_until_done(
    task_id: str,
    api_key: str,
    timeout_s: int = POLL_TIMEOUT_S,
    *,
    retry_on_timeout: bool = True,
) -> dict:
    url = _poll_result_url(task_id)
    start = time.time()
    while time.time() - start < timeout_s:
        status, body = _poll_once_with_transient_retry(url, api_key, label=f"poll {task_id}")
        if status >= 400:
            raise RuntimeError(f"Poll HTTP {status}: {body}")
        inner = body.get("data") or body
        job_status = (inner.get("status") or "unknown").lower()
        if job_status in ("completed", "failed", "error"):
            return inner
        time.sleep(POLL_INTERVAL_S)
    if retry_on_timeout:
        retry_start = time.time()
        while time.time() - retry_start < POLL_TIMEOUT_RETRY_S:
            status, body = _poll_once_with_transient_retry(
                url, api_key, label=f"poll-retry {task_id}",
            )
            if status >= 400:
                raise RuntimeError(f"Poll HTTP {status}: {body}")
            inner = body.get("data") or body
            job_status = (inner.get("status") or "unknown").lower()
            if job_status in ("completed", "failed", "error"):
                inner.setdefault("poll_retry", True)
                return inner
            time.sleep(POLL_INTERVAL_S)
    return {
        "status": "timeout",
        "id": task_id,
        "error": (
            f"WaveSpeed poll timed out after {timeout_s + (POLL_TIMEOUT_RETRY_S if retry_on_timeout else 0)}s "
            f"— task {task_id} may still be running; use Redo or wait and poll again"
        ),
    }


def extract_output_url(result: dict) -> str | None:
    outputs = [o for o in (result.get("outputs") or []) if o]
    if outputs:
        return outputs[0]
    out = result.get("output")
    if isinstance(out, str):
        return out
    if isinstance(out, dict):
        return out.get("video_url") or out.get("url")
    return None


def download_mp4(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["curl", "-s", "-S", "-L", "-o", str(dest), "-m", "180", url],
        capture_output=True,
        text=True,
        timeout=200,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Download failed: {r.stderr}")


def run_startend_generation(
    api_key: str,
    prompt: str,
    start_image_path: str | Path,
    end_image_path: str | Path,
    dest_mp4: Path,
    duration: int = 5,
    speaker: str | None = None,
    *,
    sound: bool = False,
    tier: str | None = None,
) -> dict:
    """Poll O3 Omni start+end image-to-video through to downloaded MP4."""
    task_id, resolved_tier = submit_image_to_video_startend(
        api_key,
        prompt,
        start_image_path,
        end_image_path,
        duration=duration,
        speaker=speaker,
        sound=sound,
        tier=tier,
    )
    result = poll_until_done(task_id, api_key)
    status = (result.get("status") or "").lower()
    if status != "completed":
        return {"ok": False, "task_id": task_id, "status": status, "tier": resolved_tier, "result": result}
    url = extract_output_url(result)
    if not url:
        return {"ok": False, "task_id": task_id, "status": "no_output_url", "tier": resolved_tier, "result": result}
    download_mp4(url, dest_mp4)
    return {
        "ok": True,
        "task_id": task_id,
        "tier": resolved_tier,
        "video_path": str(dest_mp4),
        "video_url": url,
        "status": status,
        "mode": "o3_image_to_video_startend",
    }


def run_beat_generation(
    api_key: str,
    prompt: str,
    char_image_path: str | Path,
    bg_image_path: str | Path,
    dest_mp4: Path,
    duration: int = 8,
    speaker: str | None = None,
) -> dict:
    task_id, tier = submit_reference_to_video(
        api_key, prompt, char_image_path, bg_image_path, duration=duration, speaker=speaker,
    )
    try:
        result = poll_until_done(task_id, api_key)
    except RuntimeError as exc:
        msg = str(exc)
        if "Poll HTTP" in msg or "transport failed after retries" in msg:
            return {
                "ok": False,
                "task_id": task_id,
                "status": "poll_gateway_error",
                "tier": tier,
                "error": msg,
                "retry_safe": True,
                "result": {"error": msg},
            }
        raise
    status = (result.get("status") or "").lower()
    if status != "completed":
        return {"ok": False, "task_id": task_id, "status": status, "tier": tier, "result": result}
    url = extract_output_url(result)
    if not url:
        return {"ok": False, "task_id": task_id, "status": "no_output_url", "tier": tier, "result": result}
    download_mp4(url, dest_mp4)
    return {
        "ok": True,
        "task_id": task_id,
        "tier": tier,
        "video_path": str(dest_mp4),
        "video_url": url,
        "status": status,
    }


def resume_task_to_mp4(
    api_key: str,
    task_id: str,
    dest_mp4: Path,
    *,
    timeout_s: int = POLL_TIMEOUT_S,
) -> dict:
    """Poll an existing WaveSpeed task and download when complete."""
    result = poll_until_done(task_id, api_key, timeout_s=timeout_s)
    status = (result.get("status") or "").lower()
    if status != "completed":
        return {"ok": False, "task_id": task_id, "status": status, "result": result}
    url = extract_output_url(result)
    if not url:
        return {"ok": False, "task_id": task_id, "status": "no_output_url", "result": result}
    download_mp4(url, dest_mp4)
    return {
        "ok": True,
        "task_id": task_id,
        "video_path": str(dest_mp4),
        "video_url": url,
        "status": status,
    }
