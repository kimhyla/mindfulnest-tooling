"""Prototype-scoped pipeline adapter.

Standalone HTTP server on localhost:8090 that bridges Directus Flow webhooks
to the same underlying APIs production_server.py uses (ElevenLabs, BFL
FLUX Kontext, WaveSpeed Kling v3.0 Pro start-end per §8.3, WaveSpeed
ByteDance LatentSync, and ffmpeg silcomp per §8.4). Does NOT touch
production_server.py or Event_1 state.

Endpoints:
  POST /animate          Kling basic image-to-video (original endpoint,
                         kept for backward compat with existing Flow)
  POST /tts              ElevenLabs v3 TTS → beat.tts_audio
  POST /kling-startend   §8.3: BFL end-frame + Kling start-end submit →
                         new prod_video_candidates row + selected_option
  POST /silcomp          §8.4: ffmpeg silencedetect + concat compression
                         on beat.tts_audio → beat.tts_audio_compressed
  POST /lipsync          ByteDance LatentSync on selected_option video +
                         tts_audio_compressed → beat.lipsync_output,
                         status=approved, lipsync_status=done

All endpoints return 202 Accepted immediately; work runs in a background
thread so Directus Flows don't hit their 5-min operation cap.

Teardown: kill this process (no state beyond running threads).
"""
from __future__ import annotations

# --- WA-C14 Doppler migration (per LD-208) ---
import os as _os, sys as _sys
from pathlib import Path as _Path
_p = _Path(__file__).resolve()
while _p.parent != _p and _p.name != "Production":
    _p = _p.parent
if _p.name == "Production":
    _sys.path.insert(0, str(_p))
from lib.credential_store import get_secret  # noqa: E402
# --- end WA-C14 boilerplate ---

import json, sys, os, time, threading, mimetypes, traceback, subprocess, tempfile, re
import urllib.request, urllib.parse, ssl, http.client, base64
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

HERE = Path(__file__).resolve()
PROD_ROOT = HERE.parent.parent.parent  # .../Production
sys.path.insert(0, str(PROD_ROOT / "tools"))
sys.path.insert(0, str(HERE.parent))

# The Doppler boilerplate above already cached `lib` as Production/lib (for
# credential_store). That shadows `lib.directus` which lives at
# Production/tools/lib/directus.py. Load it directly via importlib so we
# don't fight the package-name collision.
import importlib.util as _ilu
def _load_file(name: str, path: Path):
    spec = _ilu.spec_from_file_location(name, str(path))
    mod = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod
_directus_mod = _load_file("_prototype_directus", PROD_ROOT / "tools" / "lib" / "directus.py")
DirectusClient = _directus_mod.DirectusClient
DirectusError = _directus_mod.DirectusError

from _clients import LOCAL_URL, LOCAL_EMAIL, LOCAL_PASSWORD  # type: ignore

# Reusable helpers from production tooling (unchanged — we wrap, not replace)
from kling_startend_pipeline import (  # type: ignore
    flux_kontext_generate_end_frame,
    kling_startend_submit,
    kling_poll_fresh,
    ensure_min_dimensions,
)
from lipsync_sender import LipSyncClient, COST_PER_LIPSYNC  # type: ignore


# =========================================================================
#  API keys + constants
# =========================================================================

WAVESPEED_KEY = get_secret("WAVESPEED_API_KEY")
ELEVENLABS_KEY = get_secret("ELEVENLABS_API_KEY")
BFL_KEY = get_secret("BFL_API_KEY")

WAVESPEED_SUBMIT = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-v3.0-pro/image-to-video"
WAVESPEED_POLL = "https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"

# Rule 8.1 anti-lipsync negative, used on all Kling submits
NEGATIVE_PROMPT = (
    "lip sync, speaking, talking, mouth movement, dialogue, speech, "
    "open mouth, Chinese, audio, voice, singing"
)

# Jessica = ElevenLabs library voice used as Tessa. Config matches Kim's ask:
# eleven_v3, stability 0.5, style 0.3.
JESSICA_VOICE_ID = "cgSgspJ2msm6clMCkdW9"
TTS_MODEL_ID = "eleven_v3"
TTS_STABILITY = 0.5
TTS_STYLE = 0.3
TTS_SIMILARITY = 0.75
ELEVENLABS_TTS_ENDPOINT = (
    "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
)

DRY_RUN_DEFAULT = os.environ.get("PROTOTYPE_DRY_RUN", "1") == "1"
MAX_CONCURRENT_JOBS = 3  # prototype hard cap

_job_semaphore = threading.Semaphore(MAX_CONCURRENT_JOBS)
_active_jobs: dict[str, dict] = {}
_active_lock = threading.Lock()


def _dclient() -> DirectusClient:
    c = DirectusClient(LOCAL_URL, LOCAL_EMAIL, LOCAL_PASSWORD)
    c.authenticate()
    return c


def _job_key(beat_id: str, kind: str) -> str:
    return f"{beat_id}:{kind}"


def _mark_job(beat_id: str, kind: str, **patch):
    with _active_lock:
        key = _job_key(beat_id, kind)
        job = _active_jobs.get(key) or {
            "beat_id": beat_id, "kind": kind,
            "started_at": time.time(), "stage": "starting", "error": None,
        }
        job.update(patch)
        _active_jobs[key] = job
        return job


def _download_directus_asset(c: DirectusClient, file_id: str) -> tuple[bytes, str]:
    """Fetch a file from local Directus /assets/<id>. Returns (bytes, mime)."""
    req = urllib.request.Request(
        f"{LOCAL_URL}/assets/{file_id}",
        headers={"Authorization": f"Bearer {c._token}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "application/octet-stream")


def _upload_to_directus(c: DirectusClient, raw: bytes, filename: str,
                       title: str, content_type: str) -> str:
    """Upload bytes to local Directus /files. Returns file uuid."""
    boundary = f"----pa{int(time.time()*1000)}"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="title"\r\n\r\n'
    body += title.encode() + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{filename}"\r\n').encode()
    body += f"Content-Type: {content_type}\r\n\r\n".encode()
    body += raw
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{LOCAL_URL}/files", data=body, method="POST",
        headers={
            "Authorization": f"Bearer {c._token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["data"]["id"]


def _download_url(url: str, timeout: int = 180) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"non-https URL refused: {url!r}")
    ctx = ssl.create_default_context()
    ctx.options |= ssl.OP_NO_TICKET | ssl.OP_NO_COMPRESSION
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout, context=ctx)
    try:
        conn.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""),
                     headers={"Connection": "close"})
        resp = conn.getresponse()
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"download HTTP {resp.status}")
        return resp.read()
    finally:
        try: conn.close()
        except Exception: pass


# =========================================================================
#  run_job: original /animate (kept for backward compat)
# =========================================================================

def run_job(beat_id: str, prompt: str, duration: int, dry_run: bool):
    job = _mark_job(beat_id, "animate", dry_run=dry_run)
    try:
        c = _dclient()
        job["stage"] = "fetching-beat"
        beat = c.get_one("prod_storyboard_beats", beat_id)
        if not beat:
            raise RuntimeError(f"beat {beat_id} not found")
        c.update("prod_storyboard_beats", beat_id, {"status": "animating"})

        if dry_run:
            job["stage"] = "dry-run-sleep"
            time.sleep(15)
            cand = c.create("prod_video_candidates", {
                "beat_id": beat_id,
                "option_label": f"DRY_{datetime.now().strftime('%H%M%S')}",
                "source": "dry_run_stub",
                "clip_path": "", "duration_ms": 0,
            })
            c.update("prod_storyboard_beats", beat_id, {
                "status": "approved",
                "selected_option": cand["id"],
                "kim_feedback": "DRY RUN: no real Kling call.",
            })
            job["stage"] = "done-dry"
            return

        job["stage"] = "reading-image"
        image_id = beat.get("image_override")
        if not image_id:
            raise RuntimeError("no image_override on beat — drop an image first")
        img_bytes, mime = _download_directus_asset(c, image_id)
        data_uri = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"

        job["stage"] = "submitting"
        submit_body = {
            "image": data_uri, "prompt": prompt,
            "negative_prompt": NEGATIVE_PROMPT,
            "duration": duration, "cfg_scale": 0.5, "sound": False,
        }
        req = urllib.request.Request(
            WAVESPEED_SUBMIT, data=json.dumps(submit_body).encode(),
            method="POST",
            headers={"Authorization": f"Bearer {WAVESPEED_KEY}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            submit_resp = json.loads(r.read())
        task_id = (submit_resp.get("data") or {}).get("id") or submit_resp.get("id") or submit_resp.get("task_id")
        if not task_id:
            raise RuntimeError(f"no task_id: {submit_resp}")
        job["task_id"] = task_id

        job["stage"] = "polling"
        deadline = time.time() + 7 * 60
        result_url = None
        while time.time() < deadline:
            time.sleep(10)
            try:
                req = urllib.request.Request(
                    WAVESPEED_POLL.format(task_id=task_id),
                    headers={"Authorization": f"Bearer {WAVESPEED_KEY}"},
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    poll = json.loads(r.read())
            except Exception as e:
                job["last_poll_error"] = str(e)
                continue
            d = poll.get("data") or {}
            status = d.get("status") or poll.get("status")
            if status == "completed":
                outs = d.get("outputs") or poll.get("outputs") or []
                if outs:
                    result_url = outs[0] if isinstance(outs[0], str) else outs[0].get("url")
                break
            if status in ("failed", "canceled"):
                raise RuntimeError(f"WaveSpeed {status}: {poll}")
        if not result_url:
            raise RuntimeError("WaveSpeed poll timed out without completion")

        job["stage"] = "downloading"
        vid = _download_url(result_url)
        job["stage"] = "uploading"
        file_id = _upload_to_directus(
            c, vid, f"beat_{beat_id[:8]}_kling.mp4",
            f"kling beat {beat_id[:8]} {datetime.now().isoformat()}",
            "video/mp4",
        )
        job["stage"] = "recording"
        cand = c.create("prod_video_candidates", {
            "beat_id": beat_id,
            "option_label": f"K_{datetime.now().strftime('%H%M%S')}",
            "source": "kling", "clip_path": f"/assets/{file_id}",
            "duration_ms": duration * 1000,
        })
        c.update("prod_storyboard_beats", beat_id, {
            "status": "approved", "selected_option": cand["id"],
            "kim_feedback": f"Real Kling generation complete (task_id={task_id}).",
        })
        job["stage"] = "done"

    except Exception as exc:
        traceback.print_exc()
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["stage"] = "failed"
        try:
            c = _dclient()
            c.update("prod_storyboard_beats", beat_id, {
                "status": "pending",
                "kim_feedback": f"/animate failed at {job.get('stage')}: {job['error']}",
            })
        except Exception:
            pass
    finally:
        job["finished_at"] = time.time()


# =========================================================================
#  /tts — ElevenLabs Jessica (eleven_v3)
# =========================================================================

def run_tts_job(beat_id: str):
    job = _mark_job(beat_id, "tts")
    try:
        c = _dclient()
        job["stage"] = "fetching-beat"
        beat = c.get_one("prod_storyboard_beats", beat_id)
        text = (beat.get("dialogue_text") or "").strip()
        if not text:
            raise RuntimeError("beat.dialogue_text is empty — edit the line first")
        # Strip "[prototype placeholder]" tag if present so TTS doesn't read it
        text = re.sub(r"^\s*\[prototype placeholder\]\s*", "", text).strip()
        if not text:
            raise RuntimeError("after stripping placeholder tag, dialogue_text is empty")

        job["stage"] = "submitting-elevenlabs"
        body = {
            "text": text,
            "model_id": TTS_MODEL_ID,
            "voice_settings": {
                "stability": TTS_STABILITY,
                "similarity_boost": TTS_SIMILARITY,
                "style": TTS_STYLE,
                "use_speaker_boost": True,
            },
            "output_format": "mp3_44100_128",
        }
        req = urllib.request.Request(
            ELEVENLABS_TTS_ENDPOINT.format(voice_id=JESSICA_VOICE_ID),
            data=json.dumps(body).encode(), method="POST",
            headers={
                "xi-api-key": ELEVENLABS_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            status = r.status
            mp3 = r.read()
        if status != 200 or not mp3:
            raise RuntimeError(f"ElevenLabs HTTP {status}: {mp3[:200]!r}")
        job["stage"] = "uploading"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_id = _upload_to_directus(
            c, mp3, f"beat_{beat_id[:8]}_tts_{stamp}.mp3",
            f"TTS Jessica/eleven_v3 beat {beat_id[:8]} {datetime.now().isoformat()}",
            "audio/mpeg",
        )
        job["stage"] = "recording"
        c.update("prod_storyboard_beats", beat_id, {
            "tts_audio": file_id,
            "dialogue_text_locked_tts": text,
            "text_modified_after_tts": False,
            "kim_feedback": f"TTS rendered (Jessica / eleven_v3 / stability {TTS_STABILITY} / style {TTS_STYLE}).",
        })
        job["stage"] = "done"
        job["file_id"] = file_id

    except Exception as exc:
        traceback.print_exc()
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["stage"] = "failed"
        try:
            c = _dclient()
            c.update("prod_storyboard_beats", beat_id, {
                "kim_feedback": f"/tts failed at {job.get('stage')}: {job['error']}",
            })
        except Exception:
            pass
    finally:
        job["finished_at"] = time.time()


# =========================================================================
#  /kling-startend — §8.3 pipeline
# =========================================================================

DEFAULT_END_PROMPT = (
    "Same character, same outfit, same lighting, same art style. "
    "A slight emotional softening, eyes half-closed, gaze downward. "
    "Mouth at rest."
)

DEFAULT_KLING_PROMPT = (
    "Silent subtle idle movement only. no dialogue in video."
)

def run_kling_startend_job(beat_id: str, end_prompt: str | None,
                           kling_prompt: str | None, duration: int):
    job = _mark_job(beat_id, "kling-startend")
    try:
        c = _dclient()
        job["stage"] = "fetching-beat"
        beat = c.get_one("prod_storyboard_beats", beat_id)
        image_id = beat.get("image_override")
        if not image_id:
            raise RuntimeError("no image_override — drop an image onto the beat first")

        job["stage"] = "fetching-start-image"
        start_bytes, _ = _download_directus_asset(c, image_id)

        # Rule 6: ensure shortest side ≥600px
        job["stage"] = "rule6-upscale-check"
        start_bytes, start_info, (sw, sh) = ensure_min_dimensions(start_bytes)
        job["start_dims"] = f"{sw}x{sh} ({start_info})"

        # §8.3: generate end-frame via FLUX Kontext
        job["stage"] = "flux-kontext-end-frame"
        end_prompt = end_prompt or DEFAULT_END_PROMPT
        end_bytes = flux_kontext_generate_end_frame(
            start_image_bytes=start_bytes, end_prompt=end_prompt,
            api_key=BFL_KEY, aspect_ratio="4:3",
        )
        # Rule 6 on end-frame too
        end_bytes, end_info, (ew, eh) = ensure_min_dimensions(end_bytes)
        job["end_dims"] = f"{ew}x{eh} ({end_info})"

        # Stash end-frame in Directus for auditability
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        end_file_id = _upload_to_directus(
            c, end_bytes, f"beat_{beat_id[:8]}_endframe_{stamp}.png",
            f"Kontext end-frame beat {beat_id[:8]}", "image/png",
        )

        # §8.3 Kling submission
        job["stage"] = "kling-startend-submit"
        c.update("prod_storyboard_beats", beat_id, {"status": "animating"})
        start_uri = f"data:image/png;base64,{base64.b64encode(start_bytes).decode()}"
        end_uri = f"data:image/png;base64,{base64.b64encode(end_bytes).decode()}"
        kling_prompt = kling_prompt or DEFAULT_KLING_PROMPT
        task_id = kling_startend_submit(
            start_b64_uri=start_uri, end_b64_uri=end_uri,
            prompt=kling_prompt,
            negative_prompt=NEGATIVE_PROMPT,
            duration=duration,
            api_key=WAVESPEED_KEY,
        )
        job["task_id"] = task_id

        # §8.3 poll
        job["stage"] = "kling-poll"
        result = kling_poll_fresh(task_id, api_key=WAVESPEED_KEY, timeout_s=900)
        if result.get("status") != "completed":
            raise RuntimeError(f"Kling non-completed: {result.get('status')}")
        outputs = result.get("outputs") or []
        if not outputs:
            raise RuntimeError(f"Kling completed but no outputs: {result}")
        url = outputs[0] if isinstance(outputs[0], str) else outputs[0].get("url")
        if not url:
            raise RuntimeError(f"no URL on output: {outputs}")

        # Download + upload to Directus
        job["stage"] = "downloading"
        vid = _download_url(url)
        job["stage"] = "uploading-candidate"
        vid_file_id = _upload_to_directus(
            c, vid, f"beat_{beat_id[:8]}_startend_{stamp}.mp4",
            f"Kling start-end beat {beat_id[:8]} {datetime.now().isoformat()}",
            "video/mp4",
        )
        job["stage"] = "recording"
        cand = c.create("prod_video_candidates", {
            "beat_id": beat_id,
            "option_label": f"SE_{datetime.now().strftime('%H%M%S')}",
            "source": "kling_startend",
            "clip_path": f"/assets/{vid_file_id}",
            "duration_ms": duration * 1000,
        })
        c.update("prod_storyboard_beats", beat_id, {
            "status": "approved",
            "selected_option": cand["id"],
            "kim_feedback": (
                f"§8.3 start-end complete. End-frame file={end_file_id}. "
                f"Kling task={task_id}. duration={duration}s."
            ),
        })
        job["stage"] = "done"
        job["candidate_id"] = cand["id"]
        job["video_file_id"] = vid_file_id

    except Exception as exc:
        traceback.print_exc()
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["stage"] = "failed"
        try:
            c = _dclient()
            c.update("prod_storyboard_beats", beat_id, {
                "status": "pending",
                "kim_feedback": f"/kling-startend failed at {job.get('stage')}: {job['error']}",
            })
        except Exception:
            pass
    finally:
        job["finished_at"] = time.time()


# =========================================================================
#  /silcomp — §8.4 pipeline (ffmpeg silencedetect + concat)
# =========================================================================

def _detect_silences(src: Path, noise_db: float = -32.0, min_s: float = 0.15
                     ) -> list[tuple[float, float, float]]:
    """Run ffmpeg silencedetect, return silences as (start, end, duration)."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(src),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_s}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = proc.stderr
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start:\s*([0-9.]+)", out)]
    ends = []
    for m in re.finditer(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", out):
        ends.append((float(m.group(1)), float(m.group(2))))
    silences = []
    for i, (end, dur) in enumerate(ends):
        if i < len(starts):
            silences.append((starts[i], end, dur))
    return silences


def _compress_silences(src: Path, dst: Path,
                       threshold_s: float = 1.0, target_s: float = 0.8):
    """Per §8.4: silences > threshold_s get collapsed to target_s. Returns the
    new list of (start, end, dur_new) segments + writes dst mp3."""
    detected = _detect_silences(src)
    to_compress = [(s, e, target_s) for (s, e, d) in detected if d > threshold_s]
    if not to_compress:
        # No-op: just copy src to dst re-encoded to mp3 for consistency
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i",
               str(src), "-c:a", "libmp3lame", "-b:a", "192k", str(dst)]
        subprocess.run(cmd, check=True)
        return []
    # Build concatenation of [prev_end..s_start] + anullsrc(target_s) + tail
    scratch = []
    prev_end = 0.0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for idx, (s_start, s_end, s_new) in enumerate(to_compress):
            # Copy segment up to silence start
            p1 = td / f"seg{idx:02d}a.wav"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{prev_end:.3f}", "-i", str(src),
                "-t", f"{max(s_start - prev_end, 0.01):.3f}",
                "-ac", "1", "-ar", "44100", str(p1),
            ], check=True)
            scratch.append(p1)
            # Synthesized silence
            p2 = td / f"seg{idx:02d}b.wav"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-t", f"{s_new:.3f}",
                "-ac", "1", "-ar", "44100", str(p2),
            ], check=True)
            scratch.append(p2)
            prev_end = s_end
        # Tail
        src_dur_out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
            capture_output=True, text=True, check=True,
        )
        src_dur = float(src_dur_out.stdout.strip())
        if src_dur > prev_end + 0.01:
            tail = td / "tail.wav"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-ss", f"{prev_end:.3f}", "-i", str(src),
                "-t", f"{src_dur - prev_end:.3f}",
                "-ac", "1", "-ar", "44100", str(tail),
            ], check=True)
            scratch.append(tail)
        # Concat
        concat_list = td / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p}'" for p in scratch))
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:a", "libmp3lame", "-b:a", "192k", str(dst),
        ], check=True)
    return detected


def run_silcomp_job(beat_id: str, threshold_s: float, target_s: float):
    job = _mark_job(beat_id, "silcomp")
    try:
        c = _dclient()
        job["stage"] = "fetching-beat"
        beat = c.get_one("prod_storyboard_beats", beat_id)
        tts_id = beat.get("tts_audio")
        if not tts_id:
            raise RuntimeError("beat.tts_audio not set — render TTS first")
        job["stage"] = "fetching-tts"
        mp3_bytes, _ = _download_directus_asset(c, tts_id)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "in.mp3"
            src.write_bytes(mp3_bytes)
            dst = td / "compressed.mp3"
            job["stage"] = "silencedetect-compress"
            detected = _compress_silences(src, dst, threshold_s, target_s)
            out_bytes = dst.read_bytes()

        job["stage"] = "uploading"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_id = _upload_to_directus(
            c, out_bytes, f"beat_{beat_id[:8]}_silcomp_{stamp}.mp3",
            f"silcomp §8.4 beat {beat_id[:8]} "
            f"({len([d for d in detected if d[2] > threshold_s])} silences compressed)",
            "audio/mpeg",
        )
        c.update("prod_storyboard_beats", beat_id, {
            "tts_audio_compressed": file_id,
            "kim_feedback": (
                f"§8.4 silcomp applied: {len(detected)} silences detected, "
                f"{len([d for d in detected if d[2] > threshold_s])} compressed "
                f">{threshold_s}s → {target_s}s."
            ),
        })
        job["stage"] = "done"
        job["file_id"] = file_id
        job["detected"] = len(detected)
        job["compressed"] = len([d for d in detected if d[2] > threshold_s])

    except Exception as exc:
        traceback.print_exc()
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["stage"] = "failed"
        try:
            c = _dclient()
            c.update("prod_storyboard_beats", beat_id, {
                "kim_feedback": f"/silcomp failed at {job.get('stage')}: {job['error']}",
            })
        except Exception:
            pass
    finally:
        job["finished_at"] = time.time()


# =========================================================================
#  /lipsync — ByteDance LatentSync
# =========================================================================

def run_lipsync_job(beat_id: str):
    job = _mark_job(beat_id, "lipsync")
    try:
        c = _dclient()
        job["stage"] = "fetching-beat"
        beat = c.get_one("prod_storyboard_beats", beat_id)
        selected_id = beat.get("selected_option")
        audio_id = beat.get("tts_audio_compressed") or beat.get("tts_audio")
        if not selected_id:
            raise RuntimeError("beat.selected_option not set — generate animation first")
        if not audio_id:
            raise RuntimeError("beat.tts_audio(_compressed) not set — render TTS first")

        cand = c.get_one("prod_video_candidates", selected_id)
        clip_path = cand.get("clip_path") or ""
        if not clip_path.startswith("/assets/"):
            raise RuntimeError(f"selected candidate clip_path is not a Directus asset: {clip_path!r}")
        video_file_id = clip_path.split("/assets/", 1)[1]

        job["stage"] = "fetching-video"
        video_bytes, _ = _download_directus_asset(c, video_file_id)
        job["stage"] = "fetching-audio"
        audio_bytes, _ = _download_directus_asset(c, audio_id)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vpath = td / "video.mp4"
            apath = td / "audio.mp3"
            vpath.write_bytes(video_bytes)
            apath.write_bytes(audio_bytes)

            c.update("prod_storyboard_beats", beat_id, {"lipsync_status": "running"})

            client = LipSyncClient(WAVESPEED_KEY)
            job["stage"] = "lipsync-submit"
            # Python urllib / http.client consistently hit a 75s connect-
            # timeout on this machine when POSTing the ~9MB base64 body to
            # api.wavespeed.ai/bytedance/lipsync (even though shell curl
            # with the exact same body completes in 14s). Shell-out to
            # curl --data-binary with an explicit body file — proven working.
            video_uri = f"data:video/mp4;base64,{base64.b64encode(vpath.read_bytes()).decode()}"
            audio_uri = f"data:audio/mpeg;base64,{base64.b64encode(apath.read_bytes()).decode()}"
            body_file = td / "submit_body.json"
            with open(body_file, "wb") as bf:
                bf.write(json.dumps({"video": video_uri, "audio": audio_uri}).encode())
            # -4 forces IPv4. Without it, curl's happy-eyeballs tries IPv6
            # to api.wavespeed.ai (which routes through Tencent CLB) and
            # hangs until the connect-timeout, even though no AAAA record
            # exists. Shell curl has different DNS caching that hides this
            # in interactive use, but subprocess curl reliably stalls.
            curl_cmd = [
                "curl", "-4", "-s", "-S",
                "--connect-timeout", "30",
                "--max-time", "300",
                "-X", "POST",
                "-H", f"Authorization: Bearer {WAVESPEED_KEY}",
                "-H", "Content-Type: application/json",
                "--data-binary", f"@{body_file}",
                "https://api.wavespeed.ai/api/v3/bytedance/lipsync/audio-to-video",
            ]
            proc = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=330)
            if proc.returncode != 0:
                raise RuntimeError(f"LipSync curl exit={proc.returncode}: {proc.stderr[:400]}")
            try:
                submit_resp = json.loads(proc.stdout)
            except json.JSONDecodeError:
                raise RuntimeError(f"LipSync non-JSON response: {proc.stdout[:400]}")
            task_id = ((submit_resp.get("data") or {}).get("id")
                       or submit_resp.get("id") or submit_resp.get("task_id"))
            if not task_id:
                raise RuntimeError(f"LipSync submit missing task_id: {submit_resp}")
            job["task_id"] = task_id

            # Poll directly via urllib (small GET responses work fine — the
            # large-body IPv6 stall only affected the submit POST).
            job["stage"] = "lipsync-poll"
            poll_url = f"https://api.wavespeed.ai/api/v3/predictions/{task_id}/result"
            deadline = time.time() + 10 * 60
            url = None
            while time.time() < deadline:
                time.sleep(10)
                try:
                    preq = urllib.request.Request(
                        poll_url,
                        headers={"Authorization": f"Bearer {WAVESPEED_KEY}"},
                    )
                    with urllib.request.urlopen(preq, timeout=30) as r:
                        pr = json.loads(r.read())
                except Exception as e:
                    job["last_poll_error"] = str(e)
                    continue
                d = pr.get("data") or {}
                status = d.get("status") or pr.get("status")
                if status == "completed":
                    outs = d.get("outputs") or pr.get("outputs") or []
                    if outs:
                        url = outs[0] if isinstance(outs[0], str) else outs[0].get("url")
                    break
                if status in ("failed", "canceled"):
                    raise RuntimeError(f"LatentSync {status}: {pr}")
            if not url:
                raise RuntimeError("LatentSync poll timed out without completion")

            job["stage"] = "downloading"
            lipsync_bytes = _download_url(url)

        job["stage"] = "uploading"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file_id = _upload_to_directus(
            c, lipsync_bytes, f"beat_{beat_id[:8]}_lipsync_{stamp}.mp4",
            f"ByteDance LatentSync beat {beat_id[:8]} {datetime.now().isoformat()}",
            "video/mp4",
        )
        c.update("prod_storyboard_beats", beat_id, {
            "lipsync_output": file_id,
            "lipsync_status": "done",
            "status": "approved",
            "kim_feedback": f"LatentSync complete. task={task_id}.",
        })
        job["stage"] = "done"
        job["file_id"] = file_id

    except Exception as exc:
        traceback.print_exc()
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["stage"] = "failed"
        try:
            c = _dclient()
            c.update("prod_storyboard_beats", beat_id, {
                "lipsync_status": "failed",
                "kim_feedback": f"/lipsync failed at {job.get('stage')}: {job['error']}",
            })
        except Exception:
            pass
    finally:
        job["finished_at"] = time.time()


# =========================================================================
#  HTTP handler
# =========================================================================

ENDPOINTS = {
    "/animate": ("animate", run_job),
    "/tts": ("tts", run_tts_job),
    "/kling-startend": ("kling-startend", run_kling_startend_job),
    "/silcomp": ("silcomp", run_silcomp_job),
    "/lipsync": ("lipsync", run_lipsync_job),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{datetime.now().isoformat(timespec='seconds')}] "
                         f"{self.address_string()} - {fmt%args}\n")

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            with _active_lock:
                snap = {k: dict(v) for k, v in _active_jobs.items()}
            self._json(200, {
                "ok": True,
                "active_jobs": snap,
                "endpoints": list(ENDPOINTS.keys()),
                "dry_run_default": DRY_RUN_DEFAULT,
                "max_concurrent": MAX_CONCURRENT_JOBS,
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ENDPOINTS:
            self._json(404, {"error": "not found",
                             "available": list(ENDPOINTS.keys())})
            return
        kind, worker = ENDPOINTS[self.path]

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return

        beat_id = payload.get("beat_id")
        if not beat_id:
            self._json(400, {"error": "beat_id required"})
            return

        if not _job_semaphore.acquire(blocking=False):
            self._json(429, {"error": f"max {MAX_CONCURRENT_JOBS} concurrent jobs"})
            return

        def runner():
            try:
                if kind == "animate":
                    worker(
                        beat_id,
                        payload.get("prompt") or "Silent subtle idle movement only. no dialogue in video.",
                        int(payload.get("duration") or 5),
                        bool(payload.get("dry_run", DRY_RUN_DEFAULT)),
                    )
                elif kind == "tts":
                    worker(beat_id)
                elif kind == "kling-startend":
                    worker(
                        beat_id,
                        payload.get("end_prompt"),
                        payload.get("kling_prompt"),
                        int(payload.get("duration") or 5),
                    )
                elif kind == "silcomp":
                    worker(
                        beat_id,
                        float(payload.get("threshold_s") or 1.0),
                        float(payload.get("target_s") or 0.8),
                    )
                elif kind == "lipsync":
                    worker(beat_id)
            finally:
                _job_semaphore.release()

        threading.Thread(target=runner, daemon=True).start()
        self._json(202, {
            "accepted": True, "beat_id": beat_id, "kind": kind,
            "poll": "http://localhost:8090/",
        })


def main():
    port = 8090
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"prototype pipeline adapter listening on http://127.0.0.1:{port}")
    print(f"  endpoints: {list(ENDPOINTS.keys())}")
    print(f"  dry_run_default={DRY_RUN_DEFAULT}  max_concurrent={MAX_CONCURRENT_JOBS}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
