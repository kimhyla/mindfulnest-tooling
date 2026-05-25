#!/usr/bin/env python3
"""
lipsync_sender.py — Kling LipSync via WaveSpeed API
====================================================
Submits animation clips + TTS audio to Kling LipSync endpoint.
Returns lip-synced video clips ready for storyboard integration.

Uses the same WaveSpeed API key as animation generation (Kling/Seedance).
Endpoint: api.wavespeed.ai/api/v3/kwaivgi/kling-lipsync/audio-to-video
Cost: ~$0.35 per job

SWITCH_TO_KLING_LIPSYNC_20260524: switched from bytedance/lipsync/audio-to-video
to kwaivgi/kling-lipsync/audio-to-video. Kim confirmed Kling lipsync quality is
visibly better. The same API contract applies: {"video": data_uri, "audio": data_uri}
payload, same polling URL pattern. No ByteDance 10s training window constraint.

Usage:
    from lipsync_sender import LipSyncClient

    client = LipSyncClient(wavespeed_api_key)
    task_id = client.submit(video_path, audio_path)
    result = client.poll(task_id)
    if result["status"] == "completed":
        client.download(result["outputs"][0], dest_path)
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# No external dependencies — stdlib only for Mac compatibility

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIPSYNC_BASE_URL = (
    "https://api.wavespeed.ai/api/v3/kwaivgi/kling-lipsync"
)

LIPSYNC_SUBMIT_URL = f"{LIPSYNC_BASE_URL}/audio-to-video"

CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"
UGUU_UPLOAD_URL = "https://uguu.se/api.php?action=upload"  # fallback

PREDICTIONS_POLL_BASE = "https://api.wavespeed.ai/api/v3/predictions"

def lipsync_poll_url(job_id: str) -> str:
    """Poll endpoint — uses shared predictions endpoint (confirmed by WaveSpeed API response urls.get)."""
    return f"{PREDICTIONS_POLL_BASE}/{job_id}/result"

COST_PER_LIPSYNC = 0.35  # Kling lipsync per job (SWITCH_TO_KLING_LIPSYNC_20260524)
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 10, 20]  # seconds
POLL_INTERVAL = 10  # seconds between polls
POLL_TIMEOUT = 1200  # max seconds to wait for completion (20 min — Phase B audio can be 2+ min)
UGUU_UPLOAD_TIMEOUT = 60  # seconds per file upload


# ---------------------------------------------------------------------------
# Helpers — temp file hosting (catbox.moe primary, uguu.se fallback)
# ---------------------------------------------------------------------------

def _build_multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """
    Build multipart/form-data body using stdlib only.
    fields: {name: value} for text fields
    files: {field_name: (filename, file_bytes, mime_type)}
    Returns (body_bytes, content_type_header).
    """
    boundary = f"----MindfulNest{int(time.time() * 1000)}"
    parts = []

    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    for field_name, (filename, file_data, mime) in files.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode())
        parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
        parts.append(file_data)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _upload_to_catbox(file_path: Path) -> str | None:
    """Upload to catbox.moe using stdlib. Returns URL or None."""
    try:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        file_data = file_path.read_bytes()
        body, content_type = _build_multipart(
            fields={"reqtype": "fileupload"},
            files={"fileToUpload": (file_path.name, file_data, mime_type)},
        )

        req = urllib.request.Request(
            CATBOX_UPLOAD_URL,
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=UGUU_UPLOAD_TIMEOUT) as resp:
            result = resp.read().decode("utf-8").strip()
            if result.startswith("https://"):
                return result
            print(f"[lipsync] catbox.moe unexpected response: {result[:200]}")
    except Exception as exc:
        print(f"[lipsync] catbox.moe upload failed for {file_path.name}: {exc}")
    return None


def _upload_to_uguu(file_path: Path) -> str | None:
    """Upload to uguu.se (fallback) using stdlib. Returns URL or None."""
    try:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        file_data = file_path.read_bytes()
        body, content_type = _build_multipart(
            fields={},
            files={"file": (file_path.name, file_data, mime_type)},
        )

        req = urllib.request.Request(
            UGUU_UPLOAD_URL,
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=UGUU_UPLOAD_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "url" in data:
                return data["url"]
        print(f"[lipsync] uguu.se response missing 'url': {data}")
    except Exception as exc:
        print(f"[lipsync] uguu.se upload failed for {file_path.name}: {exc}")
    return None


def upload_to_hosting(file_path: Path) -> str | None:
    """
    Upload a file to temporary hosting for WaveSpeed submission.
    Tries catbox.moe first (proven working), falls back to uguu.se.
    Returns public URL or None if all services fail.
    """
    url = _upload_to_catbox(file_path)
    if url:
        return url
    print(f"[lipsync] catbox.moe failed, trying uguu.se fallback...")
    return _upload_to_uguu(file_path)


# ---------------------------------------------------------------------------
# Helpers — data URI fallback
# ---------------------------------------------------------------------------

def file_to_data_uri(path: Path, mime_type: str) -> str:
    """Read a file and return a data URI string (fallback only)."""
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


# ---------------------------------------------------------------------------
# Helpers — audio padding (prevents lip sync boundary artifacts)
# ---------------------------------------------------------------------------

LIPSYNC_PAD_START = 0.5  # seconds of silence before speech
LIPSYNC_PAD_END = 0.5    # seconds of silence after speech
# SWITCH_TO_KLING_LIPSYNC_20260524: Kling has no ByteDance 10s training window
# constraint. Raised from 60s to 180s to support Phase B module-level lipsync
# (full meditations can be 90-150s after silcomp).
# (LD LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1 id=400 was ByteDance-specific.)
LIPSYNC_MAX_DURATION_SEC = 180.0


def _find_ffmpeg() -> str | None:
    """Find ffmpeg binary — check Homebrew paths first (macOS), then PATH."""
    candidates = [
        "/opt/homebrew/bin/ffmpeg",   # Apple Silicon Homebrew
        "/usr/local/bin/ffmpeg",      # Intel Homebrew
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    # Fall back to PATH lookup
    try:
        result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _probe_media_duration_sec(ffmpeg: str, media_path: Path) -> float | None:
    """Return format duration in seconds via ffprobe, or None on failure."""
    try:
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(media_path),
             "-show_entries", "format=duration", "-of", "csv=p=0"],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip() or "0")
    except (ValueError, subprocess.SubprocessError):
        return None


def pad_audio_for_lipsync(audio_path: Path) -> Path:
    """
    Add silence padding to start and end of audio before lip sync submission.

    Lip sync models produce artifacts at clip boundaries because they lack
    context. Adding ~0.5s silence at each end lets the model transition
    smoothly from neutral → speaking → neutral.

    Returns path to padded temp file (caller should clean up after submission).
    If ffmpeg is not available, returns original path (graceful fallback).

    LD-400 (LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1): duration is enforced on
    the POST-PAD file. Pre-pad guards elsewhere can pass while padding pushes
    total past ByteDance's 10s training window (beat_04/06 class, #144).
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        print(f"[lipsync] WARNING: ffmpeg not found — skipping audio padding")
        print(f"[lipsync] Install ffmpeg for smoother lip sync edges: brew install ffmpeg")
        return audio_path

    import tempfile
    # py/insecure-temporary-file fix: mktemp() has a TOCTOU race window.
    # mkstemp() atomically creates the file with mode 0600 (owner-only).
    # We immediately close the fd because ffmpeg writes via path string.
    fd, padded_str = tempfile.mkstemp(suffix="_padded.mp3")
    os.close(fd)
    padded = Path(padded_str)

    # ffmpeg: prepend silence + original audio + append silence
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-t", str(LIPSYNC_PAD_START), "-i", "anullsrc=r=44100:cl=mono",
        "-i", str(audio_path),
        "-f", "lavfi", "-t", str(LIPSYNC_PAD_END), "-i", "anullsrc=r=44100:cl=mono",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[out]",
        "-map", "[out]",
        "-codec:a", "libmp3lame", "-q:a", "2",
        str(padded),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        print(f"[lipsync] WARNING: ffmpeg not executable — skipping audio padding")
        if padded.exists():
            padded.unlink()
        return audio_path

    if result.returncode != 0:
        print(f"[lipsync] WARNING: audio padding failed: {result.stderr[:300]}")
        print(f"[lipsync] Falling back to unpadded audio")
        if padded.exists():
            padded.unlink()
        return audio_path  # fall back to original

    # LD-400 post-padding bypass class (#144): measure AFTER concat, not before.
    padded_dur = _probe_media_duration_sec(ffmpeg, padded)
    if padded_dur is not None and padded_dur > LIPSYNC_MAX_DURATION_SEC:
        if padded.exists():
            padded.unlink()
        raise ValueError(
            f"[lipsync] BLOCKED: padded audio is {padded_dur:.2f}s, exceeds "
            f"LIPSYNC_MAX_DURATION_SEC={LIPSYNC_MAX_DURATION_SEC}s "
            f"(LD-400 LIPSYNC_MAX_DURATION_10S_NO_SILENCE_V1). "
            "Pre-pad duration passed but +padding exceeded ByteDance max — "
            "trim audio or use silence-split + passthrough (CLAUDE.md §8.5)."
        )

    orig_size = audio_path.stat().st_size
    pad_size = padded.stat().st_size
    print(f"[lipsync] Padded audio: {orig_size} → {pad_size} bytes "
          f"(+{LIPSYNC_PAD_START}s start, +{LIPSYNC_PAD_END}s end, "
          f"duration={padded_dur:.2f}s)")
    return padded


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LipSyncClient:
    """
    WaveSpeed Kling LipSync client. (SWITCH_TO_KLING_LIPSYNC_20260524)
    Formerly ByteDance LatentSync — switched 2026-05-24.
    Uses curl via subprocess for WaveSpeed API calls because Python's
    urllib hangs on this endpoint (TLS/HTTP version mismatch on macOS).
    curl works instantly on the same machine — confirmed April 16, 2026.
    API contract unchanged: {"video": data_uri, "audio": data_uri}, same polling.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    @staticmethod
    def _resolve_host(host: str) -> str | None:
        """Resolve hostname via public DNS (8.8.8.8 / 1.1.1.1) instead of the
        system resolver, which on Kim's macOS persistently returns a bogus
        ISP-hijacked IP (167.206.37.145 Altice/Optimum) for api.wavespeed.ai
        — causing every POST to time out. Public DNS correctly returns the
        Tencent Cloud LB IP (49.51.190.24) that actually routes to WaveSpeed.
        Discovered 2026-04-21. Returns IPv4 or None.
        """
        import re
        for resolver in ("8.8.8.8", "1.1.1.1"):
            try:
                result = subprocess.run(
                    ["dig", "+short", "+time=3", "+tries=1",
                     f"@{resolver}", host],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", line):
                        return line
            except (subprocess.TimeoutExpired, OSError):
                continue
        # Last-resort fallback: system resolver (may be poisoned, but better
        # than nothing if dig / public DNS are unreachable).
        import socket
        try:
            return socket.gethostbyname(host)
        except OSError:
            return None

    def _curl_json(self, method: str, url: str, body: dict | None = None,
                   timeout: int = 60) -> dict:
        """Make an API call via curl and return parsed JSON.
        Uses a temp file for the body to avoid 'Argument list too long' on large payloads.
        """
        import tempfile
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        cmd = [
            "curl", "-s", "-S",  # silent but show errors
            "--http1.1",  # macOS curl hangs on WaveSpeed HTTP/2 handshake (2026-04-21)
            "-m", str(timeout),
            "-X", method,
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "Content-Type: application/json",
        ]

        # Pre-resolve the hostname via Python socket (reliable) and force curl
        # to that IP with --resolve. Works around a macOS DNS issue where
        # api.wavespeed.ai intermittently resolves to a non-routable ISP IP
        # (167.206.37.145 Altice/Optimum) instead of the real Tencent Cloud LB
        # (49.51.190.24), causing curl POST to time out after 6-10s.
        resolved_ip = self._resolve_host(host) if host else None
        if resolved_ip:
            cmd += ["--resolve", f"{host}:{port}:{resolved_ip}"]

        tmp_file = None
        try:
            if body is not None:
                # Write body to temp file to avoid shell argument length limits
                tmp_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                )
                json.dump(body, tmp_file)
                tmp_file.close()
                cmd += ["-d", f"@{tmp_file.name}"]

            cmd.append(url)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)

            if result.returncode != 0:
                raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr[:500]}")

            if not result.stdout.strip():
                raise RuntimeError(f"curl returned empty response, stderr: {result.stderr[:500]}")

            return json.loads(result.stdout)

        finally:
            if tmp_file and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)

    def submit(self, video_path: Path, audio_path: Path) -> str:
        """
        Submit a lip sync job.

        Uses data URIs (base64-encoded files in JSON body) via curl.
        This works because:
        - curl handles the WaveSpeed TLS connection fine (urllib doesn't)
        - Data URIs avoid the "connection aborted" error that WaveSpeed
          gets when trying to download from catbox.moe/uguu.se
        - A 3.8MB video → ~5.1MB base64 is fine for curl

        Returns:
            job_id for polling
        """
        video_size = video_path.stat().st_size
        audio_size = audio_path.stat().st_size
        print(f"[lipsync] Submitting: video={video_path.name} ({video_size} bytes), "
              f"audio={audio_path.name} ({audio_size} bytes)")

        # SWITCH_TO_KLING_LIPSYNC_20260524: Kling lipsync has no ByteDance 10s training
        # window constraint (LIPSYNC_MAX_DURATION_SEC raised to 60s).
        # Soft guard only — warn rather than hard-block.
        result = subprocess.run(
            [_find_ffmpeg() or "ffmpeg", "-v", "error", "-i", str(video_path),
             "-show_entries", "format=duration", "-of", "csv=p=0"],
            capture_output=True, text=True
        )
        try:
            _vid_dur = float(result.stdout.strip() or "0")
        except ValueError:
            _vid_dur = 0.0
        if _vid_dur > LIPSYNC_MAX_DURATION_SEC:
            # Log a warning but don't hard-block — Kling's API enforces its
            # own duration limit. Our LIPSYNC_MAX_DURATION_SEC is a soft
            # ceiling; if Kling rejects it, the caller gets a real API error.
            print(
                f"[lipsync] WARN: video is {_vid_dur:.2f}s, exceeds soft ceiling "
                f"LIPSYNC_MAX_DURATION_SEC={LIPSYNC_MAX_DURATION_SEC}s — "
                "submitting anyway; Kling will enforce its own limit.",
                flush=True,
            )

        # SWITCH_TO_KLING_LIPSYNC_20260524: pad_audio_for_lipsync was a ByteDance-specific
        # boundary artifact fix (silence at start/end). Not needed for Kling — use audio_path directly.

        # Build data URIs — embed files directly in the request
        print(f"[lipsync] Encoding video as data URI...")
        video_uri = file_to_data_uri(video_path, "video/mp4")
        print(f"[lipsync] Encoding audio as data URI...")
        audio_uri = file_to_data_uri(audio_path, "audio/mpeg")

        body = {"video": video_uri, "audio": audio_uri}
        body_size = len(json.dumps(body))
        print(f"[lipsync] Payload size: {body_size / 1024 / 1024:.1f} MB (data URIs via curl)")

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                payload = self._curl_json("POST", LIPSYNC_SUBMIT_URL, body, timeout=120)
                break
            except Exception as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF[attempt]
                    print(f"[lipsync] Attempt {attempt+1} failed: {exc}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"WaveSpeed submit failed after {MAX_RETRIES} attempts: {last_error}"
                    )

        # Extract job_id from response
        # Response shape: {"code":200, "data":{"id":"...", ...}}
        job_id = (
            (payload.get("data") or {}).get("id")
            or payload.get("id")
            or payload.get("task_id")
        )
        if not job_id:
            raise RuntimeError(f"WaveSpeed response missing job id: {payload}")

        # Also extract poll URL if provided
        poll_url = (payload.get("data") or {}).get("urls", {}).get("get")
        if poll_url:
            print(f"[lipsync] Poll URL from response: {poll_url}")

        print(f"[lipsync] Submitted successfully, job_id={job_id}")
        return job_id

    def poll(self, job_id: str) -> dict:
        """
        Poll for job status via curl.
        Uses shared predictions endpoint (confirmed by WaveSpeed urls.get).

        Returns:
            dict with {status, outputs, raw}
        """
        # Preflight 107 (2026-04-19): timeout raised 15 -> 60. Same class
        # of false-timeout as the WaveSpeed poll — ByteDance LipSync can
        # respond in the 30-45s range under load, so 15s was guaranteed
        # to hit urlopen error timed out on slow-but-alive cycles. 60s
        # gives the API time to respond; poll_until_done's outer loop
        # re-polls at POLL_INTERVAL=10s anyway, and total budget is bounded
        # by POLL_TIMEOUT=600s.
        payload = self._curl_json("GET", lipsync_poll_url(job_id), timeout=60)

        # Parse status from nested data or top-level
        data = payload.get("data") or {}
        status = data.get("status") or payload.get("status") or "unknown"

        # Collect output URLs from all known response shapes
        outputs = []
        if data.get("output"):
            # Single output field
            outputs.append(data["output"])
        elif data.get("outputs") and any(data["outputs"]):
            outputs = [o for o in data["outputs"] if o]
        elif payload.get("video"):
            outputs.append(payload["video"])
        elif payload.get("outputs"):
            outputs = payload["outputs"]

        return {"status": status, "outputs": outputs, "raw": payload}

    def poll_until_done(self, job_id: str) -> dict:
        """Poll until completed, failed, or timeout."""
        start = time.time()
        while time.time() - start < POLL_TIMEOUT:
            try:
                result = self.poll(job_id)
            except Exception as exc:
                elapsed = time.time() - start
                print(f"[lipsync] Poll error at {elapsed:.0f}s: {exc}")
                time.sleep(POLL_INTERVAL)
                continue

            status = (result.get("status") or "").lower()

            if status == "completed" and result.get("outputs"):
                print(f"[lipsync] Job {job_id[:12]}... completed ({time.time()-start:.0f}s)")
                return result
            elif status in ("failed", "error"):
                print(f"[lipsync] Job {job_id[:12]}... FAILED: {result.get('raw', {})}")
                return result

            elapsed = time.time() - start
            print(f"[lipsync] Job {job_id[:12]}... status={status} ({elapsed:.0f}s elapsed)")
            time.sleep(POLL_INTERVAL)

        return {"status": "timeout", "outputs": [], "raw": {"error": f"timeout after {POLL_TIMEOUT}s"}}

    def download(self, url: str, dest: Path) -> int:
        """Download a result video to dest via curl."""
        print(f"[lipsync] Downloading to {dest.name}...")
        result = subprocess.run(
            ["curl", "-s", "-S", "--http1.1", "-m", "120", "-o", str(dest), url],
            capture_output=True, text=True, timeout=130,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Download failed: {result.stderr[:500]}")
        size = dest.stat().st_size
        print(f"[lipsync] Downloaded {size} bytes -> {dest.name}")
        return size

    def submit_and_wait(self, video_path: Path, audio_path: Path, dest: Path) -> dict:
        """
        Full pipeline: submit, poll, download.

        Returns:
            dict with {status, file, size_bytes, job_id, cost}
        """
        job_id = self.submit(video_path, audio_path)
        result = self.poll_until_done(job_id)
        status = (result.get("status") or "").lower()

        # SWITCH_TO_KLING_LIPSYNC_20260524: pad_audio_for_lipsync removed; no temp file cleanup needed.

        if status == "completed" and result.get("outputs"):
            url = result["outputs"][0]
            size = self.download(url, dest)
            return {
                "status": "completed",
                "file": dest.name,
                "size_bytes": size,
                "job_id": job_id,
                "cost": COST_PER_LIPSYNC,
            }
        else:
            return {
                "status": status,
                "file": None,
                "size_bytes": 0,
                "job_id": job_id,
                "cost": 0,  # no charge on failure
                "error": str(result.get("raw", {}).get("error", "unknown")),
            }
