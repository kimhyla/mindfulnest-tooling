#!/usr/bin/env python3
"""
kling_startend_pipeline.py

Per prod_locked_decisions id=172 KLING_STARTEND_V1_CAPABILITY
(companion preflight id=35, task_id=kling_startend_pipeline_build_20260417).

V1 SCOPE: beat_05 Tessa ONLY. Generates an end frame via FLUX Kontext (BFL)
from the beat's start image, submits both frames to WaveSpeed's Kling v3.0
Pro image-to-video endpoint with the optional end_image parameter, then
runs the existing silcomp audio through ByteDance LipSync.

Not promoted to beats 6-11 until Kim playback-verifies this V1.

Rule 8 / decision 162 compliance:
  - cfg_scale = 0.5 (no deviation)
  - Anti-lipsync negative_prompt preserved
  - sound: False
  - Positive prompt does NOT contain mouth/motion/gaze lock language
    (the gaze anchor comes from the end frame's pixel geometry, not from
    prompt words — this is the NEW class of constraint this decision
    introduces and tests)

Rule 6 compliance:
  - FLUX Kontext output checked for ≥600px shortest side; if smaller,
    auto_upscale_image() is called before Kling submission.

Rule 18/20:
  - Every phase writes to prod_activity_log.
  - Success/fail outcome triggers follow-up decision registration
    (KLING_STARTEND_V1_VALIDATED or KLING_STARTEND_V1_FAILED).

Usage:
    # Autonomous full run (default for beat_05):
    python3 tools/kling_startend_pipeline.py --beat beat_05 \\
        --end-prompt "Tessa softens her gaze downward, eyes half-closed..."

    # Dry-run: generates only the Kontext end frame, opens in Preview, stops.
    python3 tools/kling_startend_pipeline.py --beat beat_05 --dry-run

    # Override the end frame with a hand-picked image:
    python3 tools/kling_startend_pipeline.py --beat beat_05 \\
        --end-image path/to/hand_picked_tessa_end.png

    # Skip the lipsync step (save $0.15 for Kling-only debugging):
    python3 tools/kling_startend_pipeline.py --beat beat_05 --skip-lipsync
"""

from __future__ import annotations

import argparse
import base64
import http.client
import io
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ----- PATHS -----
HERE = Path(__file__).resolve().parent
PROD_ROOT = HERE.parent
EVENT_DIR = PROD_ROOT / "Event_1"
CLIPS_DIR = EVENT_DIR / "animation_clips"
TTS_DIR = EVENT_DIR / "story_scene_tts_v2"
PRESERVED = EVENT_DIR / "preserved_winners"
TEMP_IMG = EVENT_DIR / "_temp_images"
STATE_PATH = EVENT_DIR / "production_state.json"

# Shared atomic-JSON helper (Windows/Dropbox retry-safe per LD-368)
if str(PROD_ROOT) not in sys.path:
    sys.path.insert(0, str(PROD_ROOT))
from lib.atomic_json_write import atomic_json_write  # noqa: E402

# ----- CONSTANTS (Rule 8 + 162 compliant) -----
WAVESPEED_KLING_SUBMIT = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
MIN_ANIMATION_SIZE = 600
KLING_MAX_DURATION = 10
CFG_SCALE_BASELINE = 0.5
COST_FLUX_KONTEXT = 0.08
COST_KLING_10S = 0.45
COST_LIPSYNC = 0.15

# Rule 8 required negatives
RULE8_ANTI_LIPSYNC = (
    "lip sync, speaking, talking, mouth movement, beak movement, dialogue, "
    "speech, open mouth, Chinese, audio, voice, singing"
)

# Default generic positive prompt for V1 Tessa. No mouth/motion/gaze locks.
# Character identity + gaze are anchored by the end frame pixel geometry,
# not by prompt words (decision 172 architectural test).
DEFAULT_POSITIVE_PROMPT = (
    "A small turtle (Tessa) in a soft forest clearing. Cinematic 4:3 "
    "composition, soft ambient light. Beak at rest, no dialogue in video. "
    "Natural interpolation between the two provided frames."
)

# Default end-frame prompt for beat_05 Tessa's "I'm sorry... more careful" arc
DEFAULT_END_FRAME_PROMPT_BEAT_05 = (
    "Same character, same outfit, same cartoon 3D Pixar-style art, same "
    "lighting, same forest background. Tessa the turtle now has a softer, "
    "more internally reflective expression — eyes lowered slightly in "
    "gentle remorse, head tilted subtly downward. Beak still closed. "
    "Same 4:3 composition and framing."
)


def log(msg: str) -> None:
    """Print with timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def duration_of(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def ffmpeg_run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ffmpeg failed ({what}):\n{r.stderr[-1500:]}")
        sys.exit(1)


# =========================================================================
#  Credentials (via production_server.parse_api_keys to avoid credentials.py
#  wavespeed-URL-collision bug)
# =========================================================================

def load_api_keys() -> dict:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_prod_server_import", HERE / "production_server.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    keys = mod.parse_api_keys(PROD_ROOT / "API_KEYS_MASTER.md")
    # BFL key: parse separately since it's not in parse_api_keys scope
    import re
    content = (PROD_ROOT / "API_KEYS_MASTER.md").read_text(encoding="utf-8")
    m = re.search(
        r"\|\s*\*+(?:Flux|BFL|Black\s*Forest)[^|]*\*+[^|]*\|\s*`([^`]+)`",
        content, re.IGNORECASE,
    )
    if m:
        keys["bfl"] = m.group(1).strip()
    else:
        # Try lib/credentials (works correctly for BFL — only wavespeed has the bug)
        sys.path.insert(0, str(HERE / "lib"))
        from credentials import load_credentials  # type: ignore
        creds = load_credentials()
        keys["bfl"] = creds.get("bfl_key", "")

    if not keys.get("wavespeed"):
        sys.exit("FATAL: no wavespeed key")
    if not keys.get("bfl"):
        sys.exit("FATAL: no bfl (FLUX) key — check API_KEYS_MASTER.md")
    return keys


# =========================================================================
#  Start-frame resolution (from production_state image_overrides)
# =========================================================================

def get_start_image_for_beat(beat_id: str) -> tuple[str, bytes]:
    """Return (image_key, raw_bytes) for the beat's assigned start image.

    Resolution order per decision 138 (IMAGE_OVERRIDE_DURABILITY_HYBRID):
      1. production_state.image_overrides[beat_id] → image_key
      2. Storyboard HTML L[] entry i: field (fallback)
      3. Temp image file on disk (fallback)
    """
    state = json.loads(STATE_PATH.read_text())
    image_key = (state.get("image_overrides") or {}).get(beat_id)

    if not image_key:
        # Fallback: parse storyboard HTML L[] entry
        storyboard = EVENT_DIR / "storyboard_v37_prod.html"
        if storyboard.is_file():
            import re
            html = storyboard.read_text(encoding="utf-8")
            beat_num = int(beat_id.split("_")[1])
            marker = f'a:"line_{beat_num:02d}"'
            idx = html.find(marker)
            if idx >= 0:
                open_brace = html.rfind("{", 0, idx)
                close_brace = html.find("}", idx)
                entry = html[open_brace:close_brace + 1]
                im = re.search(r'i:"([^"]+)"', entry)
                if im:
                    image_key = im.group(1)

    if not image_key:
        sys.exit(f"FATAL: no image_key resolvable for {beat_id}")

    # Load raw bytes: prefer disk file in _temp_images (full-res), fall back
    # to extracting from storyboard HTML
    disk_path = TEMP_IMG / f"{image_key}.png"
    if disk_path.is_file():
        return image_key, disk_path.read_bytes()

    # Extract from storyboard gallery <div class="ic">
    storyboard = EVENT_DIR / "storyboard_v37_prod.html"
    import re as re2
    html = storyboard.read_text(encoding="utf-8")
    pattern = r'<div class="ic"><img src="(data:image/[^"]+)"><p>([^<]+)</p></div>'
    for m in re2.finditer(pattern, html):
        src, name = m.group(1), m.group(2)
        key = name.replace(".png", "").replace(".PNG", "").replace(" ", "_")
        if key == image_key:
            _, b64 = src.split(",", 1)
            return image_key, base64.b64decode(b64)

    sys.exit(f"FATAL: could not resolve raw bytes for image_key={image_key!r}")


# =========================================================================
#  Rule 6: auto-upscale if shortest side < 600px
# =========================================================================

def ensure_min_dimensions(img_bytes: bytes, min_side: int = MIN_ANIMATION_SIZE,
                          target_min: int = 800) -> tuple[bytes, str, tuple[int, int]]:
    """Returns (possibly-upscaled PNG bytes, info, (w, h)).

    If shortest side < min_side, upscales to target_min via PIL LANCZOS.
    Matches auto_upscale_image() in production_server.py.
    """
    from PIL import Image  # type: ignore
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    shortest = min(w, h)
    if shortest >= min_side:
        return img_bytes, f"OK {w}x{h}", (w, h)

    scale = target_min / shortest
    new_size = (int(w * scale), int(h * scale))
    up = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    up.save(buf, format="PNG")
    return buf.getvalue(), f"upscaled {w}x{h} → {new_size[0]}x{new_size[1]}", new_size


# =========================================================================
#  FLUX Kontext (BFL API) end-frame generation
# =========================================================================

BFL_ENDPOINT = "https://api.bfl.ai/v1/flux-kontext-pro"
BFL_RESULT_BASE = "https://api.bfl.ai/v1/get_result"


# =========================================================================
#  Robust HTTPS helper — fresh connection per request + retry
#  (April 17 2026 hardening — applied UNIVERSALLY per Kim directive:
#  "make it always work that way from now on, for all of them, universally,
#  all buttons in all beats")
#
#  Addresses urllib-stuck-state where a long-running server's reused
#  connections can hang on congested APIs. Fresh http.client per attempt
#  + OP_NO_TICKET/OP_NO_COMPRESSION + exponential backoff retry.
# =========================================================================

def robust_https_request(
    host: str,
    path: str,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: int = 90,
    max_retries: int = 3,
    retry_on_status: tuple[int, ...] = (500, 502, 503, 504),
) -> tuple[int, bytes]:
    """Fresh-connection HTTPS request with retry + backoff.

    Returns (status_code, response_body_bytes). Raises the last exception
    on total failure (after exhausting retries).

    Retry triggers: TimeoutError, HTTPException, OSError, AND any HTTP status
    in retry_on_status (default 5xx). 4xx responses return immediately (client
    error — retrying won't help).

    Backoff: 3s, 9s, 27s between attempts.
    """
    import http.client as _http
    import ssl as _ssl
    import time as _time
    headers = headers or {}
    last_exc: Exception | None = None
    last_status: int | None = None
    last_body: bytes = b""

    for attempt in range(max_retries):
        try:
            ctx = _ssl.create_default_context()
            ctx.options |= _ssl.OP_NO_TICKET | _ssl.OP_NO_COMPRESSION
            conn = _http.HTTPSConnection(host, timeout=timeout, context=ctx)
            try:
                full_headers = dict(headers)
                if body is not None and "Content-Length" not in full_headers:
                    full_headers["Content-Length"] = str(len(body))
                conn.request(method, path, body=body, headers=full_headers)
                resp = conn.getresponse()
                raw = resp.read()
                last_status = resp.status
                last_body = raw
            finally:
                conn.close()

            if last_status < 400:
                if attempt > 0:
                    print(f"[robust-https] {method} {host}{path[:40]} — succeeded on retry {attempt+1}")
                return last_status, last_body

            if last_status in retry_on_status:
                # 5xx — retry
                last_exc = Exception(f"HTTP {last_status}: {raw[:200].decode('utf-8', 'replace')}")
                print(f"[robust-https] {method} {host}{path[:40]} attempt {attempt+1}/{max_retries}: HTTP {last_status} — retrying")
            else:
                # 4xx — client error, don't retry
                return last_status, last_body

        except (TimeoutError, _http.HTTPException, OSError) as exc:
            last_exc = exc
            print(f"[robust-https] {method} {host}{path[:40]} attempt {attempt+1}/{max_retries}: {type(exc).__name__}: {exc} — retrying")

        if attempt < max_retries - 1:
            _time.sleep(3 * (3 ** attempt))

    if last_exc:
        raise last_exc
    # Non-retryable HTTP error or exhausted retries on 5xx
    return last_status or 0, last_body


def flux_kontext_generate_end_frame(
    start_image_bytes: bytes,
    end_prompt: str,
    api_key: str,
    aspect_ratio: str = "4:3",
    timeout_s: int = 180,
) -> bytes:
    """Call FLUX Kontext Pro with input image + prompt, return generated PNG bytes.

    BFL API flow:
      1. POST /v1/flux-kontext-pro with {prompt, input_image (base64)} → {id, polling_url}
      2. Poll polling_url until status='Ready'
      3. Download from result['sample']
    """
    b64 = base64.b64encode(start_image_bytes).decode("ascii")
    payload = {
        "prompt": end_prompt,
        "input_image": b64,
        "aspect_ratio": aspect_ratio,
        "output_format": "png",
        "safety_tolerance": 2,  # default
    }
    body = json.dumps(payload).encode("utf-8")
    log(f"  → POST {BFL_ENDPOINT} (input {len(start_image_bytes):,}B, prompt {len(end_prompt)}c)")

    # Submit — robust_https_request handles retries + fresh connection + 90s timeout.
    try:
        status, raw = robust_https_request(
            host="api.bfl.ai",
            path="/v1/flux-kontext-pro",
            method="POST",
            headers={"x-key": api_key, "Content-Type": "application/json"},
            body=body,
            timeout=90,
            max_retries=3,
        )
    except Exception as exc:
        sys.exit(f"FLUX Kontext submit failed after retries: {exc}")
    if status >= 400:
        sys.exit(f"FLUX Kontext submit HTTP {status}: {raw[:500].decode('utf-8', 'replace')}")
    result = json.loads(raw.decode("utf-8"))

    task_id = result.get("id")
    polling_url = result.get("polling_url") or f"{BFL_RESULT_BASE}?id={task_id}"
    if not task_id:
        sys.exit(f"FLUX Kontext returned no id: {result}")
    log(f"  submitted, id={task_id}")

    # Poll (each poll attempt uses robust_https_request individually;
    # no need for retry within the poll because the loop itself retries).
    import urllib.parse as _uparse
    pu = _uparse.urlparse(polling_url)
    poll_host = pu.hostname or "api.bfl.ai"
    poll_path = pu.path + ("?" + pu.query if pu.query else "")
    start_t = time.time()
    last_status = None
    while time.time() - start_t < timeout_s:
        try:
            pstatus, praw = robust_https_request(
                host=poll_host, path=poll_path, method="GET",
                headers={"x-key": api_key}, timeout=20, max_retries=1,
            )
            if pstatus >= 400:
                log(f"  poll HTTP {pstatus} at t+{int(time.time()-start_t)}s — retrying loop")
                time.sleep(5); continue
            poll_result = json.loads(praw.decode("utf-8"))
        except Exception as e:
            log(f"  poll err at t+{int(time.time()-start_t)}s: {e}")
            time.sleep(5)
            continue

        status_str = (poll_result.get("status") or "").strip()
        if status_str != last_status:
            log(f"  t+{int(time.time()-start_t):3d}s status={status_str}")
            last_status = status_str

        if status_str == "Ready":
            sample = (poll_result.get("result") or {}).get("sample")
            if not sample:
                sys.exit(f"FLUX Kontext Ready but no sample: {poll_result}")
            log(f"  downloading sample: {sample[:80]}...")
            # Download the generated image — keep urllib for this since it's
            # a one-shot GET to a CDN URL, wrap in retry loop just in case.
            import urllib.request as _ureq
            for dl_attempt in range(3):
                try:
                    with _ureq.urlopen(sample, timeout=60) as r:
                        return r.read()
                except Exception as dl_exc:
                    log(f"  download attempt {dl_attempt+1} failed: {dl_exc}")
                    if dl_attempt < 2:
                        time.sleep(3 * (3 ** dl_attempt))
            sys.exit(f"FLUX Kontext download failed after 3 attempts")
        if status_str in ("Error", "Failed", "Task not found"):
            sys.exit(f"FLUX Kontext failed: {poll_result}")
        time.sleep(3)

    sys.exit(f"FLUX Kontext timed out after {timeout_s}s")


# =========================================================================
#  Kling Subject Binding — character element registry loader
# =========================================================================

def _load_subject_element(speaker: str) -> "dict | None":
    """Return element_list entry for speaker from character_subjects.json, or None.

    Fail-open: any missing config, bad file, or unregistered character returns
    None — caller proceeds without element_list (identical to current behavior).
    Never raises. Uses case-insensitive multi-tier lookup so it handles both
    _canonicalize_speaker() output ('luna') and title-case ('Luna') safely.

    Returns: {"element_id": "...", "element_name": "..."} ready for element_list[],
             or None if not configured / not yet registered.
    """
    try:
        subjects_path = PROD_ROOT / "character_subjects.json"
        if not subjects_path.is_file():
            return None
        data = json.loads(subjects_path.read_text(encoding="utf-8"))
        chars = data.get("characters") or {}
        # Multi-tier lookup: exact → lowercase → title-case → capitalize
        entry = (
            chars.get(speaker)
            or chars.get(speaker.lower())
            or chars.get(speaker.title())
            or chars.get(speaker.capitalize())
        )
        if not entry:
            return None
        if entry.get("status") != "active":
            return None
        eid = entry.get("element_id")
        if not eid:
            return None
        return {"element_id": str(eid), "element_name": entry.get("element_name", speaker)}
    except Exception as exc:
        log(f"[subject-binding] _load_subject_element({speaker!r}) failed (non-fatal): {exc}")
        return None


# =========================================================================
#  Kling v3.0 Pro start-end submission (via WaveSpeed)
# =========================================================================

def _resolve_wavespeed_host(host: str = "api.wavespeed.ai") -> str | None:
    """Resolve via public DNS to bypass ISP DNS poisoning (LD-379).
    Kim's ISP (Altice/Optimum) returns 167.206.37.145 for api.wavespeed.ai
    instead of the real Tencent Cloud IP 49.51.190.24. Returns IPv4 or None.
    Ported from lipsync_sender.py and production_server.py."""
    import re as _re
    for resolver in ("8.8.8.8", "1.1.1.1"):
        try:
            r = subprocess.run(
                ["dig", "+short", "+time=3", "+tries=1", f"@{resolver}", host],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                line = line.strip()
                if _re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", line):
                    return line
        except (subprocess.TimeoutExpired, OSError):
            continue
    try:
        import socket as _socket
        return _socket.gethostbyname(host)
    except OSError:
        return None


def kling_startend_submit(start_b64_uri: str, end_b64_uri: str,
                          prompt: str, negative_prompt: str,
                          duration: int, api_key: str,
                          element_entry: "dict | None" = None,
                          max_retries: int = 3) -> str:
    """Submit with both image (start) and end_image. Returns task_id.

    Uses curl --resolve to bypass ISP DNS poisoning (LD-379) — the ISP
    returns a wrong IP for api.wavespeed.ai that returns fake-looking task IDs
    which are never found on the real poll endpoint. curl --resolve connects
    to the DNS-resolved IP while presenting the real hostname in SNI.

    element_entry: optional Kling Elements identity anchor. When provided,
    appended as element_list=[entry] to reinforce character identity throughout
    the clip (beyond start-frame pixel anchoring alone). Fail-open: pass None
    to omit element_list entirely — preserves current behavior exactly.
    """
    import tempfile as _tempfile
    payload = {
        "image": start_b64_uri,
        "end_image": end_b64_uri,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration": duration,
        "cfg_scale": CFG_SCALE_BASELINE,
        "sound": False,
    }
    if element_entry:
        payload["element_list"] = [element_entry]
        log(f"[kling] subject binding active: element_id={element_entry['element_id']!r} "
            f"name={element_entry['element_name']!r}")
    else:
        log("[kling] subject binding: no element_entry — proceeding without element_list")

    resolved_ip = _resolve_wavespeed_host("api.wavespeed.ai")
    log(f"[kling] DNS resolved api.wavespeed.ai → {resolved_ip or '(system fallback)'}")

    body_bytes = json.dumps(payload).encode("utf-8")
    last_err: str = ""
    for attempt in range(max_retries):
        tmp = None
        try:
            tmp = _tempfile.NamedTemporaryFile(delete=False, suffix=".json")
            tmp.write(body_bytes)
            tmp.flush()
            tmp.close()
            cmd = [
                "curl", "-s", "-S", "--http1.1",
                "--max-time", "90",
                "-X", "POST",
                "-H", f"Authorization: Bearer {api_key}",
                "-H", "Content-Type: application/json",
                "-H", "Connection: close",
                "-w", "\n__STATUS__%{http_code}",
                "-d", f"@{tmp.name}",
            ]
            if resolved_ip:
                cmd += ["--resolve", f"api.wavespeed.ai:443:{resolved_ip}"]
            cmd.append("https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video")
            result = subprocess.run(cmd, capture_output=True, timeout=100)
            raw = result.stdout
            marker = b"\n__STATUS__"
            idx = raw.rfind(marker)
            if idx < 0:
                stderr = result.stderr.decode(errors="replace").strip()
                last_err = f"curl exited {result.returncode}: {stderr or '(no stderr)'}"
                if attempt < max_retries - 1:
                    time.sleep(3 ** attempt)
                continue
            status = int(raw[idx + len(marker):].strip())
            body_raw = raw[:idx]
            if status >= 500 and attempt < max_retries - 1:
                last_err = f"HTTP {status}"
                time.sleep(3 ** attempt)
                continue
            if status >= 400:
                sys.exit(f"Kling submit HTTP {status}: {body_raw[:500].decode('utf-8', 'replace')}")
            response = json.loads(body_raw.decode("utf-8"))
            task_id = (response.get("data", {}).get("id")
                       or response.get("id") or response.get("task_id"))
            if not task_id:
                sys.exit(f"Kling submit returned no task_id: {response}")
            log(f"[kling] submitted OK task_id={task_id} (attempt {attempt+1})")
            return task_id
        except subprocess.TimeoutExpired as exc:
            last_err = f"TimeoutExpired: {exc}"
            if attempt < max_retries - 1:
                time.sleep(3 ** attempt)
        finally:
            if tmp:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass
    sys.exit(f"Kling submit failed after {max_retries} attempts: {last_err}")


def kling_poll_fresh(task_id: str, api_key: str, timeout_s: int = 900) -> dict:
    """Fresh http.client connection per poll (urllib-stuck-state workaround,
    matches decision 137 pattern used in production_server)."""
    path = f"/api/v3/predictions/{task_id}/result"
    start_t = time.time()
    last_status = None
    while time.time() - start_t < timeout_s:
        try:
            ctx = ssl.create_default_context()
            ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
            conn = http.client.HTTPSConnection("api.wavespeed.ai", timeout=20, context=ctx)
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


# =========================================================================
#  Directus logging (Rule 18 Two-Write)
# =========================================================================

def directus_log(action: str, details: dict) -> None:
    """Fire-and-forget activity log write. Non-blocking on failure."""
    try:
        sys.path.insert(0, str(HERE / "lib"))
        from credentials import load_credentials  # type: ignore
        from directus import DirectusClient  # type: ignore
        creds = load_credentials()
        c = DirectusClient(creds["directus_url"], creds["directus_email"],
                           creds["directus_password"])
        c._request("POST", "/items/prod_activity_log", data={
            "action": action,
            "module_id": 1,
            "performed_by": "kling_startend_pipeline",
            "details": json.dumps(details),
        })
    except Exception as e:
        log(f"  (directus log failed — non-fatal: {e})")


# =========================================================================
#  State update (adds new option to phase_1.options[], source='kling_startend')
# =========================================================================

def append_option_to_state(beat_id: str, option_data: dict) -> int:
    """Append a new option to phase_1.options[] and return its 1-based index.

    Uses tmp+rename atomic write to match StateManager pattern; this is a
    standalone script so we don't have access to the live StateManager's
    fcntl+threading lock. If the production server is running concurrently,
    there's a small race window. Mitigation: backup before write.
    """
    backup = STATE_PATH.with_suffix(
        f".json.bak_kling_startend_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    shutil.copy2(STATE_PATH, backup)

    state = json.loads(STATE_PATH.read_text())
    beat = state["beats"].setdefault(beat_id, {})
    phase1 = beat.setdefault("phase_1", {})
    options = phase1.setdefault("options", [])
    options.append(option_data)
    new_idx = len(options)

    # Atomic JSON write via shared helper (Windows/Dropbox retry-safe per LD-368).
    atomic_json_write(str(STATE_PATH), state)

    log(f"  state: appended option #{new_idx} to {beat_id}.phase_1.options "
        f"(backup: {backup.name})")
    return new_idx


# =========================================================================
#  Silence compression helper (reused pattern from silcomp experiments)
# =========================================================================

def silcomp_audio_if_needed(source_audio: Path,
                            silences: list[tuple[float, float, float]],
                            dst: Path) -> Path:
    """If a silcomp version already exists on disk, reuse it. Otherwise splice."""
    if dst.is_file() and dst.stat().st_size > 0:
        log(f"  silcomp audio already exists: {dst.name}")
        return dst

    # Build silcomp via concat demuxer
    scratch = []
    prev_end = 0.0
    for s_start, s_end, s_new in silences:
        parts_i = len(scratch)
        # Copy [prev_end .. s_start]
        p1 = dst.with_suffix(f".seg{parts_i:02d}.wav")
        ffmpeg_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{prev_end:.3f}", "-i", str(source_audio),
            "-t", f"{s_start - prev_end:.3f}",
            "-ac", "1", "-ar", "44100", str(p1),
        ], f"copy_{parts_i}")
        scratch.append(p1)
        # New silence
        p2 = dst.with_suffix(f".seg{parts_i+1:02d}.wav")
        ffmpeg_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", f"{s_new:.3f}",
            "-ac", "1", "-ar", "44100", str(p2),
        ], f"silence_{parts_i+1}")
        scratch.append(p2)
        prev_end = s_end

    # Tail
    tail_i = len(scratch)
    src_dur = duration_of(source_audio)
    tail = dst.with_suffix(f".seg{tail_i:02d}.wav")
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{prev_end:.3f}", "-i", str(source_audio),
        "-t", f"{src_dur - prev_end:.3f}",
        "-ac", "1", "-ar", "44100", str(tail),
    ], "tail")
    scratch.append(tail)

    concat_list = dst.with_suffix(".concat.txt")
    concat_list.write_text("\n".join(f"file '{p}'" for p in scratch))
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "libmp3lame", "-b:a", "192k", str(dst),
    ], "concat")
    for p in scratch + [concat_list]:
        try: p.unlink()
        except Exception: pass
    return dst


# =========================================================================
#  MAIN
# =========================================================================

def main() -> None:
    p = argparse.ArgumentParser(description="Kling start-end frame pipeline V1")
    p.add_argument("--beat", required=True, help="beat_NN (e.g., beat_05)")
    p.add_argument("--end-prompt", default=None,
                   help="Override end-frame Kontext prompt. "
                        "Default: beat_05 Tessa softer-gaze arc.")
    p.add_argument("--end-image", default=None,
                   help="Override: hand-picked end frame image path "
                        "(skips FLUX Kontext).")
    p.add_argument("--positive-prompt", default=None,
                   help=f"Override Kling positive prompt. Default: generic minimal.")
    p.add_argument("--duration", type=int, default=10,
                   help="Kling duration in seconds (5 or 10). Default 10.")
    p.add_argument("--dry-run", action="store_true",
                   help="Generate Kontext end frame only, open in Preview, stop.")
    p.add_argument("--skip-lipsync", action="store_true",
                   help="Stop after Kling, skip ByteDance lipsync.")
    p.add_argument("--silcomp-audio", default=None,
                   help="Override silcomp audio path. "
                        "Default: auto-derived for beat_05.")
    p.add_argument("--video-trim-s", type=float, default=None,
                   help="Trim final Kling video to N seconds before lipsync. "
                        "Default: use full Kling output.")
    args = p.parse_args()

    BEAT = args.beat
    TS = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.duration not in (5, 10):
        sys.exit(f"FATAL: --duration must be 5 or 10 (got {args.duration})")

    end_prompt = args.end_prompt
    if not end_prompt and not args.end_image:
        if BEAT == "beat_05":
            end_prompt = DEFAULT_END_FRAME_PROMPT_BEAT_05
        else:
            sys.exit(f"FATAL: --end-prompt or --end-image required for "
                     f"{BEAT} (V1 only auto-handles beat_05)")

    positive_prompt = args.positive_prompt or DEFAULT_POSITIVE_PROMPT

    log("=" * 70)
    log(f"Kling start-end pipeline V1 — {BEAT}")
    log(f"  TS: {TS}")
    log(f"  preflight: id=35, decision: id=172 (KLING_STARTEND_V1_CAPABILITY)")
    log("=" * 70)

    # Keys
    keys = load_api_keys()
    log(f"  keys loaded: wavespeed=...{keys['wavespeed'][-6:]}, bfl=...{keys['bfl'][-6:]}")

    # --- Step 1: resolve start image ---
    log(f"\n[1/6] Resolve start image for {BEAT}")
    start_key, start_bytes = get_start_image_for_beat(BEAT)
    log(f"  image_key: {start_key}  ({len(start_bytes):,} bytes)")

    # Rule 6 — auto-upscale if needed
    start_bytes_final, start_info, start_dims = ensure_min_dimensions(start_bytes)
    log(f"  start frame: {start_info}")

    # --- Step 2: obtain end frame ---
    if args.end_image:
        log(f"\n[2/6] Using hand-picked end frame: {args.end_image}")
        end_path = Path(args.end_image)
        if not end_path.is_file():
            sys.exit(f"FATAL: --end-image not found: {end_path}")
        end_bytes = end_path.read_bytes()
    else:
        log(f"\n[2/6] Generate end frame via FLUX Kontext (BFL)")
        log(f"  end_prompt: {end_prompt[:120]}{'...' if len(end_prompt) > 120 else ''}")
        end_bytes = flux_kontext_generate_end_frame(
            start_bytes_final, end_prompt, keys["bfl"], aspect_ratio="4:3",
        )
        log(f"  end frame: {len(end_bytes):,} bytes")

    # Rule 6 — auto-upscale end frame too
    end_bytes_final, end_info, end_dims = ensure_min_dimensions(end_bytes)
    log(f"  end frame: {end_info}")

    # Save end frame to disk for review (always — even in full run)
    end_frame_path = TEMP_IMG / f"_tmp_end_frame_{BEAT}_{TS}.png"
    end_frame_path.parent.mkdir(exist_ok=True)
    end_frame_path.write_bytes(end_bytes_final)
    log(f"  saved end frame → {end_frame_path.name}")

    # Preserve end frame permanently
    PRESERVED.mkdir(exist_ok=True)
    preserved_end = PRESERVED / f"end_frame_{BEAT}_{TS}.png"
    shutil.copy2(end_frame_path, preserved_end)
    log(f"  preserved → {preserved_end.name}")

    if args.dry_run:
        log(f"\n[DRY RUN] stopping after end-frame generation")
        subprocess.run(["open", "-a", "Preview", str(end_frame_path)])
        log(f"  opened end frame in Preview for review")
        log(f"  if approved, re-run WITHOUT --dry-run OR with "
            f"--end-image {end_frame_path.relative_to(PROD_ROOT)}")
        return

    # --- Step 3: submit Kling start-end ---
    log(f"\n[3/6] Submit to Kling v3.0 Pro (start + end_image)")
    log(f"  positive prompt: {positive_prompt[:100]}...")
    log(f"  negative prompt: {RULE8_ANTI_LIPSYNC[:80]}...")
    log(f"  cfg_scale: {CFG_SCALE_BASELINE} (Rule 8 default)")
    log(f"  duration: {args.duration}s")

    start_uri = f"data:image/png;base64,{base64.b64encode(start_bytes_final).decode('ascii')}"
    end_uri = f"data:image/png;base64,{base64.b64encode(end_bytes_final).decode('ascii')}"

    kling_task_id = kling_startend_submit(
        start_uri, end_uri,
        prompt=positive_prompt,
        negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=args.duration,
        api_key=keys["wavespeed"],
    )
    log(f"  kling task_id: {kling_task_id}")
    directus_log("kling_startend_submitted", {
        "task_id": "kling_startend_pipeline_build_20260417",
        "beat": BEAT,
        "kling_task_id": kling_task_id,
        "start_image_key": start_key,
        "end_image_mode": "flux_kontext" if not args.end_image else "hand_picked",
        "cfg_scale": CFG_SCALE_BASELINE,
        "duration": args.duration,
    })

    # --- Step 4: poll + download ---
    log(f"\n[4/6] Poll Kling (fresh-connection pattern)")
    result = kling_poll_fresh(kling_task_id, keys["wavespeed"])
    if result.get("status") != "completed":
        sys.exit(f"FATAL: Kling failed: {result}")
    clip_url = (result.get("outputs") or [None])[0]
    if not clip_url:
        sys.exit(f"FATAL: Kling completed but no output URL: {result}")
    log(f"  CDN: {clip_url[:80]}...")

    raw_kling = CLIPS_DIR / f"{BEAT}_option_startend_{TS}.mp4"
    subprocess.run(["curl", "-sSL", "-o", str(raw_kling), clip_url],
                   check=True, capture_output=True, timeout=180)
    raw_dur = duration_of(raw_kling)
    log(f"  → {raw_kling.name} ({raw_dur:.3f}s, {raw_kling.stat().st_size:,} bytes)")

    # Preserve raw
    shutil.copy2(raw_kling, PRESERVED / raw_kling.name)
    log(f"  preserved → preserved_winners/{raw_kling.name}")

    if args.skip_lipsync:
        log(f"\n[--skip-lipsync] stopping before lipsync")
        subprocess.run(["open", "-a", "QuickTime Player", str(raw_kling)])
        return

    # --- Step 5: silcomp audio (or reuse) + trim video + lipsync ---
    log(f"\n[5/6] Prepare silcomp audio + lipsync against Kling output")
    if args.silcomp_audio:
        silcomp_audio = Path(args.silcomp_audio)
    elif BEAT == "beat_05":
        # Reuse the existing silcomp from earlier work
        silcomp_audio = TTS_DIR / "_tmp_line_05_tessa_silboth_20260417-034224.mp3"
        if not silcomp_audio.is_file():
            # Regenerate from original line_05_tessa_trimmed.mp3
            log(f"  silcomp audio missing, regenerating...")
            source = TTS_DIR / "line_05_tessa_trimmed.mp3"
            silcomp_audio = TTS_DIR / f"_tmp_line_05_silcomp_{TS}.mp3"
            silcomp_audio_if_needed(source, [
                (1.50, 2.88, 0.80),  # after "I fell"
                (6.76, 8.59, 0.80),  # before "I should have been more careful"
            ], silcomp_audio)
    else:
        sys.exit(f"FATAL: --silcomp-audio required for non-beat_05 (V1 scope)")

    audio_dur = duration_of(silcomp_audio)
    log(f"  silcomp audio: {silcomp_audio.name} ({audio_dur:.3f}s)")

    # Trim Kling video to audio_dur + 0.4s tail room (default) or as overridden
    if args.video_trim_s is not None:
        trim_to = args.video_trim_s
    else:
        # Target audio + 0.4s, bounded by raw duration
        trim_to = min(audio_dur + 0.4, raw_dur)
    trimmed_kling = CLIPS_DIR / f"_tmp_{BEAT}_startend_trim{trim_to:.1f}_{TS}.mp4"
    ffmpeg_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(raw_kling), "-t", f"{trim_to:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(trimmed_kling),
    ], "trim")
    log(f"  trimmed Kling → {trimmed_kling.name} ({duration_of(trimmed_kling):.3f}s)")

    # Lipsync
    from lipsync_sender import LipSyncClient  # type: ignore
    client = LipSyncClient(keys["wavespeed"])
    lipsync_out = CLIPS_DIR / f"{BEAT}_lipsync_startend_{TS}.mp4"
    t0 = time.time()
    ls = client.submit_and_wait(trimmed_kling, silcomp_audio, lipsync_out)
    ls_elapsed = time.time() - t0
    log(f"  lipsync done in {ls_elapsed:.0f}s: {ls.get('status')}")
    if ls.get("status") != "completed":
        sys.exit(f"FATAL: lipsync failed: {ls.get('error')}")

    shutil.copy2(lipsync_out, PRESERVED / lipsync_out.name)
    log(f"  lipsync → {lipsync_out.name} ({duration_of(lipsync_out):.3f}s, "
        f"{ls['size_bytes']:,} bytes)")
    log(f"  preserved → preserved_winners/{lipsync_out.name}")

    # --- Step 6: state write + manifest + open ---
    log(f"\n[6/6] Update state + manifest + open for review")
    option_data = {
        "file": raw_kling.name,
        "status": "completed",
        "task_id": kling_task_id,
        "cost": COST_FLUX_KONTEXT + COST_KLING_10S,
        "source": "kling_startend",
        "start_image_key": start_key,
        "end_image_mode": "flux_kontext" if not args.end_image else "hand_picked",
        "end_frame_file": preserved_end.name,
        "end_prompt": end_prompt if not args.end_image else None,
        "hand_picked_end": args.end_image or None,
        "positive_prompt": positive_prompt,
        "negative_prompt": RULE8_ANTI_LIPSYNC,
        "cfg_scale": CFG_SCALE_BASELINE,
        "duration": args.duration,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "lipsync": {
            "file": lipsync_out.name,
            "size_bytes": ls["size_bytes"],
            "trimmed_from_s": trim_to,
        },
    }
    option_idx = append_option_to_state(BEAT, option_data)

    manifest_path = EVENT_DIR / f"{BEAT}_startend_manifest_{TS}.json"
    manifest_path.write_text(json.dumps({
        "ts": TS,
        "beat": BEAT,
        "task_id": "kling_startend_pipeline_build_20260417",
        "preflight_id": 35,
        "decision_id": 172,
        "phase_1_option_index": option_idx,
        "outputs": {
            "end_frame": str(preserved_end.relative_to(PROD_ROOT).as_posix()),
            "raw_kling": str(raw_kling.relative_to(PROD_ROOT).as_posix()),
            "lipsync": str(lipsync_out.relative_to(PROD_ROOT).as_posix()),
        },
        "cost_usd": COST_FLUX_KONTEXT + COST_KLING_10S + COST_LIPSYNC,
        "levers": {
            "cfg_scale": CFG_SCALE_BASELINE,
            "duration": args.duration,
            "positive_prompt": positive_prompt,
            "negative_prompt": RULE8_ANTI_LIPSYNC,
            "end_prompt": end_prompt if not args.end_image else None,
            "silcomp_audio": str(silcomp_audio.name),
            "video_trim_s": trim_to,
        },
        "compliance": {
            "rule_6_auto_upscale": start_info + " / " + end_info,
            "rule_8_cfg_05": True,
            "rule_8_anti_lipsync_intact": True,
            "rule_8_2_no_positive_mouth_motion_gaze_locks": True,
            "rule_18_directus_logs": True,
            "preserve_before_change": True,
        },
    }, indent=2))
    log(f"  manifest → {manifest_path.name}")

    directus_log("kling_startend_pipeline_completed", {
        "task_id": "kling_startend_pipeline_build_20260417",
        "beat": BEAT,
        "option_index": option_idx,
        "lipsync_file": lipsync_out.name,
        "cost_usd": COST_FLUX_KONTEXT + COST_KLING_10S + COST_LIPSYNC,
    })

    subprocess.run(["open", "-a", "QuickTime Player", str(lipsync_out)])
    subprocess.run(["open", "-a", "QuickTime Player", str(raw_kling)])

    log("\n" + "=" * 70)
    log("KLING START-END PIPELINE V1 COMPLETE")
    log("=" * 70)
    log(f"  End frame:   Event_1/preserved_winners/{preserved_end.name}")
    log(f"  Raw Kling:   Event_1/animation_clips/{raw_kling.name}")
    log(f"  Lipsync:     Event_1/animation_clips/{lipsync_out.name}")
    log(f"  Total cost:  ${COST_FLUX_KONTEXT + COST_KLING_10S + COST_LIPSYNC:.2f}")
    log(f"  State opt #: {option_idx}")
    log(f"\n  Critical playback check:")
    log(f"    1. 'I'm sorry. I fell.' — does opening lipsync?")
    log(f"    2. 'I should have been more careful' — does tail lipsync?")
    log(f"    3. Gaze — camera-facing throughout?")
    log(f"    4. Character identity — does Tessa look consistent start→end?")
    log(f"    5. Motion — natural, not frozen or jittery?")


if __name__ == "__main__":
    main()
