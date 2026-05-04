#!/usr/bin/env python3
"""Phase A close-up idle animation (single-image Kling).

Animates phase_a_chipper_closeup.png with natural fireplace flicker + subtle
bird idle (beak closed, gentle breathing/feather ruffle). 10s clip — will be
pingpong-looped in ffmpeg to cover the 22.38s TTS track before ByteDance
LipSync is applied.

Rule 8 + 8.2 compliance: cfg_scale=0.5, sound=false, Rule 8 negative prompt.
Positive prompt has NO motion-lock / gaze-lock language (would starve LipSync
per §8.2). One single Rule 8 "beak closed" mention, no intensifiers.
"""
from __future__ import annotations

import base64
import json
import ssl
import sys
import time
import http.client
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # type: ignore
    load_api_keys, ensure_min_dimensions, robust_https_request,
    RULE8_ANTI_LIPSYNC, log,
)

EVENT_DIR = HERE.parent / "Event_1"
SRC = EVENT_DIR / "phase_a_chipper_closeup.png"

PROMPT = (
    "A close-up portrait of a small cartoon bird on a wooden desk in a warm "
    "firelit wizard office. The fireplace in the background flickers gently "
    "with warm orange light, soft candlelight, wisps of smoke rising. The "
    "bird has natural subtle idle motion — occasional slow blinks, feathers "
    "gently ruffling, small breathing motion. Beak closed, no dialogue in video."
)

DURATION = 10
KLING_SUBMIT_HOST = "api.wavespeed.ai"
KLING_SUBMIT_PATH = "/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"


def png_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    safe_bytes, info, _ = ensure_min_dimensions(raw)
    log(f"  {path.name}: {info}")
    return "data:image/png;base64," + base64.b64encode(safe_bytes).decode()


def submit_single_image(start_uri: str, prompt: str, api_key: str) -> str:
    """Kling single-image (no end_image) submission."""
    payload = {
        "image": start_uri,
        "prompt": prompt,
        "negative_prompt": RULE8_ANTI_LIPSYNC,
        "duration": DURATION,
        "cfg_scale": 0.5,
        "sound": False,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    status, raw = robust_https_request(
        host=KLING_SUBMIT_HOST, path=KLING_SUBMIT_PATH, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        body=body_bytes, timeout=90, max_retries=3,
    )
    if status >= 400:
        sys.exit(f"Kling submit HTTP {status}: {raw[:500]}")
    data = json.loads(raw.decode("utf-8"))
    task_id = (data.get("data", {}).get("id")
               or data.get("id") or data.get("task_id"))
    if not task_id:
        sys.exit(f"no task_id: {data}")
    return task_id


def poll_fresh(task_id: str, api_key: str, timeout_s: int = 900) -> dict:
    path = f"/api/v3/predictions/{task_id}/result"
    start_t = time.time()
    last_status = None
    while time.time() - start_t < timeout_s:
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection(KLING_SUBMIT_HOST, timeout=20, context=ctx)
            try:
                conn.request("GET", path,
                             headers={"Authorization": f"Bearer {api_key}"})
                resp = conn.getresponse()
                body = resp.read().decode("utf-8", errors="replace")
            finally:
                conn.close()
            data = json.loads(body).get("data", {})
            status = (data.get("status") or "").lower()
            if status != last_status:
                log(f"  t+{int(time.time()-start_t):3d}s status={status}")
                last_status = status
            if status in ("completed", "failed", "error"):
                return data
        except Exception as e:
            log(f"  t+{int(time.time()-start_t):3d}s poll err: {e}")
        time.sleep(5)
    return {"status": "timeout"}


def download(url: str, dst: Path) -> None:
    from urllib.request import urlopen
    for a in range(3):
        try:
            with urlopen(url, timeout=120) as r:
                dst.write_bytes(r.read())
            log(f"  downloaded {dst.name} ({dst.stat().st_size/1024/1024:.1f} MB)")
            return
        except Exception as e:
            log(f"  dl attempt {a+1} failed: {e}")
            time.sleep(3 * (2 ** a))
    sys.exit(f"download failed: {url}")


def main() -> int:
    keys = load_api_keys()
    api_key = keys["wavespeed"]
    log("=== Close-up idle Kling (10s) ===")
    uri = png_to_data_uri(SRC)
    log("  submitting (cfg=0.5, sound=false, 10s)...")
    task_id = submit_single_image(uri, PROMPT, api_key)
    log(f"  task_id: {task_id}")
    result = poll_fresh(task_id, api_key, timeout_s=900)
    status = (result.get("status") or "").lower()
    if status != "completed":
        sys.exit(f"kling failed: {result}")
    outputs = result.get("outputs") or []
    if not outputs:
        sys.exit(f"no outputs: {result}")
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    dst = EVENT_DIR / f"phase_a_closeup_idle_{ts}.mp4"
    download(outputs[0], dst)
    log("=== DONE ===")
    print(json.dumps({
        "closeup_idle_mp4": str(dst.relative_to(HERE.parent.parent)),
        "size_mb": round(dst.stat().st_size / 1024 / 1024, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
