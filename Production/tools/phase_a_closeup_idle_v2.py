#!/usr/bin/env python3
"""Phase A closeup idle v2 — background locked still, bird stays in place.

Kim April 20 2026 feedback on v1:
  - Background invented extra fires (on the floor, chair smoke)
  - Bird paced around the desk

Fix: strong "background locked still" + "bird stands still, no pacing" language
in both positive and negative prompts.
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
    "Close-up portrait of Chipper, the blue bird shown in the image, "
    "standing still on the wooden desk. The bird stays in place — does NOT "
    "pace, does NOT walk, does NOT wander. The background — wooden desk, "
    "wizard office, fireplace in its normal position — stays completely "
    "STILL and unchanged. ONLY very subtle idle motion is allowed on the "
    "bird: slow occasional blinks, tiny head tilts, gentle breathing, "
    "feathers lightly ruffling. Beak closed, no dialogue, no singing."
)

NEGATIVE = (
    RULE8_ANTI_LIPSYNC + ", "
    "walking, pacing, wandering, stepping, moving around, bird movement "
    "across surface, hovering, flying, takeoff, background motion, fire "
    "on floor, chair smoke, extra fires, new fires, moving fire, flames "
    "elsewhere, smoke elsewhere, background changes, scene changes, camera "
    "movement, camera zoom, camera pan, dolly, zoom in, zoom out"
)

DURATION = 10
KLING_HOST = "api.wavespeed.ai"
KLING_PATH = "/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"


def png_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    safe, info, _ = ensure_min_dimensions(raw)
    log(f"  {path.name}: {info}")
    return "data:image/png;base64," + base64.b64encode(safe).decode()


def submit(start_uri: str, api_key: str) -> str:
    payload = {
        "image": start_uri,
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE,
        "duration": DURATION,
        "cfg_scale": 0.5,
        "sound": False,
    }
    body = json.dumps(payload).encode("utf-8")
    status, raw = robust_https_request(
        host=KLING_HOST, path=KLING_PATH, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        body=body, timeout=90, max_retries=3,
    )
    if status >= 400:
        sys.exit(f"submit HTTP {status}: {raw[:500]}")
    data = json.loads(raw.decode("utf-8"))
    return (data.get("data", {}).get("id") or data.get("id")
            or data.get("task_id"))


def poll(task_id: str, api_key: str, timeout_s: int = 900) -> dict:
    path = f"/api/v3/predictions/{task_id}/result"
    start_t = time.time()
    last = None
    while time.time() - start_t < timeout_s:
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection(KLING_HOST, timeout=20, context=ctx)
            try:
                conn.request("GET", path,
                             headers={"Authorization": f"Bearer {api_key}"})
                resp = conn.getresponse()
                body = resp.read().decode("utf-8", errors="replace")
            finally:
                conn.close()
            data = json.loads(body).get("data", {})
            status = (data.get("status") or "").lower()
            if status != last:
                log(f"  t+{int(time.time()-start_t):3d}s status={status}")
                last = status
            if status in ("completed", "failed", "error"):
                return data
        except Exception as e:
            log(f"  t+{int(time.time()-start_t):3d}s poll err: {e}")
        time.sleep(5)
    return {"status": "timeout"}


def main() -> int:
    keys = load_api_keys()
    api_key = keys["wavespeed"]
    log("=== Closeup idle v2 (bird still, bg locked) ===")
    uri = png_to_data_uri(SRC)
    log("  submitting...")
    task_id = submit(uri, api_key)
    log(f"  task_id: {task_id}")
    result = poll(task_id, api_key)
    if (result.get("status") or "").lower() != "completed":
        sys.exit(f"kling failed: {result}")
    outputs = result.get("outputs") or []
    if not outputs:
        sys.exit(f"no outputs: {result}")
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    dst = EVENT_DIR / f"phase_a_closeup_idle_v2_{ts}.mp4"
    from urllib.request import urlopen
    for a in range(3):
        try:
            with urlopen(outputs[0], timeout=120) as r:
                dst.write_bytes(r.read())
            break
        except Exception as e:
            log(f"  dl {a+1}: {e}"); time.sleep(3 * (2 ** a))
    log(f"  downloaded {dst.name} ({dst.stat().st_size/1024/1024:.1f} MB)")
    log("=== DONE ===")
    print(json.dumps({
        "closeup_idle_v2_mp4": str(dst.relative_to(HERE.parent.parent)),
        "size_mb": round(dst.stat().st_size / 1024 / 1024, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
