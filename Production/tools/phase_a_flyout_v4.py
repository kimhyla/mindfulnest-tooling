#!/usr/bin/env python3
"""Phase A fly-out v4 — single-image Kling, straight LEFT exit, no end frame.

Kim April 20 2026:
  v1: vertical, glitchy (rejected)
  v2: 180° mid-flight flip (end=empty_desk fought the path)
  v3: hang with giant spread wings (Kontext end frame poisoned the result)
  v4: NO end frame. Single-image + strong directional prompt + negative prompt
      banning all observed failure modes. Straight flight off LEFT edge.

Then ffmpeg-fade last 0.5s to empty_desk for guaranteed clean tail.
"""
from __future__ import annotations

import base64
import json
import ssl
import subprocess
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
CHIPPER_ON_DESK = EVENT_DIR / "phase_a_chipper_on_desk_wide.png"
EMPTY_DESK = EVENT_DIR / "phase_a_empty_desk.png"

# v5: Kim's verbatim prompt — background motion ALLOWED (fly-out should
# match fly-in's ambient motion). Only the closeup idle keeps bg-locked.
PROMPT = (
    "The bird shown in the image (Chipper, the assistant bird) takes off "
    "naturally and calmly from the wooden desk — an ordinary bird takeoff. "
    "The bird spreads its wings gently, lifts off the desk and flies easily "
    "off the LEFT side of the frame, in one single continuous motion, a "
    "straight line. Same friendly calm expression as in the image. Natural "
    "bird movement, relaxed, gentle. No crouching, no launching, no rushing "
    "— just an easy casual takeoff. Warm firelit wizard office, soft "
    "candlelight, natural ambient motion on the fireplace. Beak closed, "
    "no dialogue."
)

# Rule 8 base + all observed failure modes v1-v4
NEGATIVE_PROMPT = (
    RULE8_ANTI_LIPSYNC + ", "
    "hovering, hanging in mid-air, spreading wings wide, oversized wings, "
    "enormous wings, stopped motion, drifting, floating in place, "
    "changing direction, 180 turn, turning around, flying right, flying upward, "
    "vertical takeoff, wings held still, racing, sprinting, launching, "
    "intense expression, determined expression, furled eyebrows, angry "
    "expression, crouching, crouch before takeoff, fall, trip, stumble, "
    "action scene, dramatic motion, high energy, explosive motion, rushed, "
    "frantic, aggressive motion"
)

DURATION = 5
FADE_TAIL_S = 0.5
KLING_SUBMIT_HOST = "api.wavespeed.ai"
KLING_SUBMIT_PATH = "/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"


def png_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    safe, info, _ = ensure_min_dimensions(raw)
    log(f"  {path.name}: {info}")
    return "data:image/png;base64," + base64.b64encode(safe).decode()


def submit_single_image(start_uri: str, prompt: str, neg_prompt: str,
                        api_key: str) -> str:
    """Kling single-image (no end_image) submission. Rule 8 safeguards."""
    payload = {
        "image": start_uri,
        "prompt": prompt,
        "negative_prompt": neg_prompt,
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


def fade_tail_to_empty(kling_mp4: Path, dst: Path) -> None:
    """xfade last FADE_TAIL_S to empty_desk. Uses settb to normalize
    timebases so xfade doesn't choke (v3's bug)."""
    # Probe Kling output
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,width,height",
         "-of", "json", str(kling_mp4)],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)["streams"][0]
    fps_num, fps_den = info["r_frame_rate"].split("/")
    fps = int(fps_num) / int(fps_den)
    w, h = info["width"], info["height"]
    dur_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(kling_mp4)],
        capture_output=True, text=True, check=True,
    )
    kling_dur = float(dur_probe.stdout.strip())
    fade_start = kling_dur - FADE_TAIL_S
    log(f"  kling dur: {kling_dur:.3f}s, fade start: {fade_start:.3f}s")

    # NOTE: settb=AVTB on both branches + fps filter normalizes timebase +
    # framerate so xfade can match streams.
    cmd = [
        "ffmpeg", "-y",
        "-i", str(kling_mp4),
        "-loop", "1", "-t", f"{FADE_TAIL_S + 0.1}", "-i", str(EMPTY_DESK),
        "-filter_complex",
        f"[0:v]fps={fps},settb=AVTB[v0];"
        f"[1:v]scale={w}:{h},fps={fps},settb=AVTB[v1];"
        f"[v0][v1]xfade=transition=fade:duration={FADE_TAIL_S}:"
        f"offset={fade_start}[v]",
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"ffmpeg failed:\n{r.stderr[-1500:]}")
        sys.exit(1)


def main() -> int:
    keys = load_api_keys()
    api_key = keys["wavespeed"]
    log("=== Fly-out v4 (single-image, LEFT exit, no end frame) ===")
    uri = png_to_data_uri(CHIPPER_ON_DESK)
    log(f"  prompt: {PROMPT[:80]}...")
    log(f"  neg   : {NEGATIVE_PROMPT[:80]}...")
    log("  submitting (cfg=0.5, sound=false, 5s)...")
    task_id = submit_single_image(uri, PROMPT, NEGATIVE_PROMPT, api_key)
    log(f"  task_id: {task_id}")
    result = poll_fresh(task_id, api_key, timeout_s=900)
    status = (result.get("status") or "").lower()
    if status != "completed":
        sys.exit(f"kling failed: {result}")
    outputs = result.get("outputs") or []
    if not outputs:
        sys.exit(f"no outputs: {result}")
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    kling_raw = EVENT_DIR / f"phase_a_flyout_v4_kling_{ts}.mp4"
    download(outputs[0], kling_raw)

    # ffmpeg fade tail to empty_desk
    log("=== ffmpeg tail fade to empty_desk ===")
    final = EVENT_DIR / f"phase_a_flyout_v4_{ts}.mp4"
    fade_tail_to_empty(kling_raw, final)

    log("=== DONE ===")
    print(json.dumps({
        "kling_raw_mp4": str(kling_raw.relative_to(HERE.parent.parent)),
        "final_mp4": str(final.relative_to(HERE.parent.parent)),
        "final_size_mb": round(final.stat().st_size / 1024 / 1024, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
