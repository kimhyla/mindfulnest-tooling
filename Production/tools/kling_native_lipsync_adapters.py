#!/usr/bin/env python3
"""Provider adapters for isolated Kling-compatible lipsync experiments.

These adapters are deliberately separate from the production O3 approval path.
They record public request/response metadata, never secrets, and always require
raw downloaded output to be measured by the experiment runner before promotion.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lipsync_sender import LipSyncClient, upload_to_hosting  # noqa: E402
from kling_startend_pipeline import load_api_keys  # noqa: E402


class RouteBlocked(RuntimeError):
    """Raised when a route cannot run in this environment."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class SubmitResult:
    provider: str
    route_id: str
    endpoint: str
    job_id: str
    request_shape_public: dict[str, Any]
    raw_response_public: dict[str, Any]
    output_url: str | None = None


@dataclass
class PollResult:
    status: str
    raw_response_public: dict[str, Any]
    output_url: str | None = None
    error: str | None = None


def _env_first(names: tuple[str, ...]) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _api_keys_master_path() -> Path | None:
    if str(HERE.parent.parent) not in sys.path:
        sys.path.insert(0, str(HERE.parent.parent))
    try:
        from lib.paths import API_KEYS_MASTER_PATH  # type: ignore

        path = Path(API_KEYS_MASTER_PATH)
        return path if path.is_file() else None
    except Exception:
        return None


def _parse_api_keys_master_value(label: str) -> str:
    path = _api_keys_master_path()
    if not path:
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    pattern = rf"\|\s*\**{re.escape(label)}[^|]*\**[^|]*\|\s*`([^`]+)`"
    match = re.search(pattern, content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    pattern = rf"\|\s*{re.escape(label)}\s*\|\s*`([^`]+)`"
    match = re.search(pattern, content, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_api_keys_master_fal_key() -> str:
    path = _api_keys_master_path()
    if not path:
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in content.splitlines():
        if "fal.ai" in line.lower() and "`" in line:
            match = re.search(r"`([^`]+)`", line)
            if match:
                return match.group(1).strip()
    return ""


def _resolve_fal_key() -> str:
    key = _env_first(("FAL_KEY", "FAL_API_KEY"))
    if key:
        return key
    return _parse_api_keys_master_fal_key()


def _resolve_runcomfy_key() -> str:
    return _env_first(("RUNCOMFY_API_KEY", "RUNCOMFY_KEY"))


def _resolve_kling_direct_credentials() -> tuple[str, str, str, str]:
    base_url = _env_first(("KLING_NATIVE_BASE_URL", "KLING_COMPAT_BASE_URL"))
    static_key = _env_first(("KLING_NATIVE_API_KEY", "KLING_COMPAT_API_KEY"))
    access_key = _env_first(("KLING_ACCESS_KEY",))
    secret_key = _env_first(("KLING_SECRET_KEY",))
    if not access_key:
        access_key = _parse_api_keys_master_value("Access Key")
    if not secret_key:
        secret_key = _parse_api_keys_master_value("Secret Key")
    if not base_url:
        base_url = "https://api-singapore.klingai.com"
    return base_url.rstrip("/"), access_key, secret_key, static_key


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _kling_jwt_token(access_key: str, signing_key: str) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(
        json.dumps({"iss": access_key, "exp": now + 1800, "nbf": now - 5}, separators=(",", ":")).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    # Kling API requires HMAC-SHA256 JWT signing (not password hashing).
    signature = _b64url(hmac.new(signing_key.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def _audio_duration_ms(path: Path) -> int:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    seconds = float((probe.stdout or "0").strip() or 0)
    return max(1, int(round(seconds * 1000)))


def _video_duration_ms(path: Path) -> int:
    return _audio_duration_ms(path)


def _raise_if_provider_error(payload: dict, *, provider: str) -> None:
    detail = payload.get("detail")
    if detail:
        detail_text = detail if isinstance(detail, str) else json.dumps(detail, sort_keys=True)
        code = "provider_billing_or_auth_error"
        if "invalid token" in detail_text.lower():
            code = "provider_auth_error"
        raise RouteBlocked(code, f"{provider}: {detail_text}")
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        lower = message.lower()
        if any(token in lower for token in ("error", "invalid", "locked", "denied", "unauthorized", "forbidden")):
            raise RouteBlocked("provider_failed", f"{provider}: {message}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for err_key in ("error", "error_message", "fail_reason"):
        err_val = data.get(err_key) or payload.get(err_key)
        if err_val:
            raise RouteBlocked("provider_failed", f"{provider}: {err_val}")
    code = payload.get("code")
    if code not in (None, 0, "0", 200, "200") and not _first_output(payload):
        message = payload.get("message")
        detail = f" provider code={code}"
        if message:
            detail += f" message={message}"
        billing_codes = {1102, 1103, "1102", "1103"}
        if code in billing_codes or (isinstance(message, str) and "balance" in message.lower()):
            raise RouteBlocked("provider_billing_or_auth_error", f"{provider}:{detail}")
        raise RouteBlocked("provider_failed", f"{provider}:{detail}")


def _curl_json(
    method: str,
    url: str,
    *,
    api_key: str,
    body: dict | None = None,
    timeout: int = 120,
    auth_scheme: str = "Bearer",
) -> dict:
    import tempfile

    cmd = [
        "curl", "-s", "-S", "--http1.1",
        "-m", str(timeout),
        "-X", method,
        "-H", f"Authorization: {auth_scheme} {api_key}",
        "-H", "Content-Type: application/json",
    ]
    tmp_name = None
    try:
        if body is not None:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(body, tmp)
            tmp.close()
            tmp_name = tmp.name
            cmd += ["-d", f"@{tmp_name}"]
        cmd.append(url)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed ({result.returncode}): {result.stderr[:500]}")
        if not result.stdout.strip():
            raise RuntimeError(f"empty response from {url}")
        return json.loads(result.stdout)
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _public_response(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "code": payload.get("code"),
        "message": payload.get("message"),
        "status": data.get("status") or payload.get("status"),
        "model": data.get("model") or payload.get("model"),
        "error": data.get("error") or payload.get("error"),
        "has_id": bool(data.get("id") or payload.get("id") or payload.get("task_id") or payload.get("request_id")),
        "output_count": len(data.get("outputs") or payload.get("outputs") or []),
    }


def _first_output(payload: dict) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    outputs = data.get("outputs") or payload.get("outputs") or []
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("video_url")
        if isinstance(first, str):
            return first
    task_result = data.get("task_result") if isinstance(data.get("task_result"), dict) else {}
    videos = task_result.get("videos") or []
    if isinstance(videos, list) and videos:
        first = videos[0]
        if isinstance(first, dict):
            url = first.get("url") or first.get("video_url")
            if url:
                return url
    video = data.get("video") or payload.get("video")
    if isinstance(video, dict):
        return video.get("url")
    if isinstance(video, str):
        return video
    output = data.get("output") or payload.get("output")
    if isinstance(output, str):
        return output
    return None


TERMINAL_SUCCESS = {"completed", "succeeded", "success", "done", "succeed"}
TERMINAL_FAILURE = {"failed", "error", "canceled", "cancelled"}


class KlingNativeLipSyncAdapter:
    route_id = ""
    provider = ""
    endpoint = ""

    def validate_credentials(self) -> dict:
        raise NotImplementedError

    def describe_schema(self) -> dict:
        raise NotImplementedError

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        raise NotImplementedError

    def poll(self, job_id: str) -> PollResult:
        raise NotImplementedError

    def download(self, output_url: str, dest: Path) -> Path:
        result = subprocess.run(
            ["curl", "-L", "-s", "-S", "--http1.1", "-m", "180", "-o", str(dest), output_url],
            capture_output=True,
            text=True,
            timeout=190,
        )
        if result.returncode != 0:
            raise RuntimeError(f"download failed: {result.stderr[:500]}")
        return dest


class WaveSpeedKlingLipSyncBaselineAdapter(KlingNativeLipSyncAdapter):
    route_id = "wavespeed_kling_lipsync_baseline"
    provider = "wavespeed"
    endpoint = "https://api.wavespeed.ai/api/v3/kwaivgi/kling-lipsync/audio-to-video"

    def __init__(self) -> None:
        self.client: LipSyncClient | None = None

    def _client(self) -> LipSyncClient:
        if self.client is None:
            keys = load_api_keys()
            if not keys.get("wavespeed"):
                raise RouteBlocked("blocked_missing_credentials", "WaveSpeed API key is not configured")
            self.client = LipSyncClient(keys["wavespeed"])
        return self.client

    def validate_credentials(self) -> dict:
        keys = load_api_keys()
        return {"ok": bool(keys.get("wavespeed")), "provider": self.provider, "route_id": self.route_id}

    def describe_schema(self) -> dict:
        return {
            "provider": self.provider,
            "route_id": self.route_id,
            "endpoint": self.endpoint,
            "request_fields": ["video", "audio"],
            "expected_gate": "known current wrapper failure: raw output often sub-720",
        }

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        client = self._client()
        video_proof = upload_to_hosting(video_path)
        audio_proof = upload_to_hosting(audio_path)
        body = {"video": video_proof["submitted_url"], "audio": audio_proof["submitted_url"]}
        payload = client._curl_json("POST", self.endpoint, body, timeout=120)
        job_id = (payload.get("data") or {}).get("id") or payload.get("id") or payload.get("task_id")
        if not job_id:
            raise RuntimeError(f"WaveSpeed response missing job id: {_public_response(payload)}")
        public_request = {
            "fields": ["video", "audio"],
            "video_preflight": {k: video_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
            "audio_preflight": {k: audio_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
        }
        return SubmitResult(
            provider=self.provider,
            route_id=self.route_id,
            endpoint=self.endpoint,
            job_id=str(job_id),
            request_shape_public=public_request,
            raw_response_public=_public_response(payload),
        )

    def poll(self, job_id: str) -> PollResult:
        client = self._client()
        result = client.poll(job_id)
        status = str(result.get("status") or "unknown")
        return PollResult(
            status=status,
            raw_response_public=_public_response(result.get("raw") or {}),
            output_url=(result.get("outputs") or [None])[0],
            error=str((result.get("raw") or {}).get("error") or "") or None,
        )


class FalKlingLipSyncAdapter(KlingNativeLipSyncAdapter):
    route_id = "fal_kling_lipsync_a2v"
    provider = "fal"
    endpoint = "https://fal.run/fal-ai/kling-video/lipsync/audio-to-video"

    def _key(self) -> str:
        key = _resolve_fal_key()
        if not key:
            raise RouteBlocked("blocked_missing_credentials", "FAL_KEY/FAL_API_KEY is not configured")
        return key

    def validate_credentials(self) -> dict:
        return {"ok": bool(_resolve_fal_key()), "provider": self.provider, "route_id": self.route_id}

    def describe_schema(self) -> dict:
        return {
            "provider": self.provider,
            "route_id": self.route_id,
            "endpoint": self.endpoint,
            "request_fields": ["video_url", "audio_url"],
        }

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        api_key = self._key()
        video_proof = upload_to_hosting(video_path)
        audio_proof = upload_to_hosting(audio_path)
        body = {"video_url": video_proof["submitted_url"], "audio_url": audio_proof["submitted_url"]}
        payload = _curl_json("POST", self.endpoint, api_key=api_key, body=body, timeout=180, auth_scheme="Key")
        _raise_if_provider_error(payload, provider=self.provider)
        output_url = _first_output(payload)
        if not output_url:
            raise RouteBlocked("provider_failed", f"{self.provider}: response missing output url: {_public_response(payload)}")
        job_id = payload.get("request_id") or payload.get("id") or payload.get("task_id") or "fal_sync_result"
        return SubmitResult(
            provider=self.provider,
            route_id=self.route_id,
            endpoint=self.endpoint,
            job_id=str(job_id),
            request_shape_public={
                "fields": ["video_url", "audio_url"],
                "video_preflight": {k: video_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
                "audio_preflight": {k: audio_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
            },
            raw_response_public=_public_response(payload),
            output_url=output_url,
        )

    def poll(self, job_id: str) -> PollResult:
        raise RouteBlocked("blocked_unsupported_schema", "Fal sync route does not require polling")


class RunComfyKlingLipSyncAdapter(KlingNativeLipSyncAdapter):
    route_id = "runcomfy_kling_lipsync_a2v"
    provider = "runcomfy"
    endpoint = "https://model-api.runcomfy.net/v1/models/kling/kling/lipsync/audio-to-video"

    def _key(self) -> str:
        key = _resolve_runcomfy_key()
        if not key:
            raise RouteBlocked("blocked_missing_credentials", "RUNCOMFY_API_KEY/RUNCOMFY_KEY is not configured")
        return key

    def validate_credentials(self) -> dict:
        return {"ok": bool(_resolve_runcomfy_key()), "provider": self.provider, "route_id": self.route_id}

    def describe_schema(self) -> dict:
        return {
            "provider": self.provider,
            "route_id": self.route_id,
            "endpoint": self.endpoint,
            "request_fields": ["video_url", "audio_url"],
        }

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        api_key = self._key()
        video_proof = upload_to_hosting(video_path)
        audio_proof = upload_to_hosting(audio_path)
        body = {"video_url": video_proof["submitted_url"], "audio_url": audio_proof["submitted_url"]}
        payload = _curl_json("POST", self.endpoint, api_key=api_key, body=body, timeout=180)
        job_id = payload.get("request_id") or payload.get("id") or payload.get("task_id")
        if not job_id:
            raise RuntimeError(f"RunComfy response missing request id: {_public_response(payload)}")
        return SubmitResult(
            provider=self.provider,
            route_id=self.route_id,
            endpoint=self.endpoint,
            job_id=str(job_id),
            request_shape_public={
                "fields": ["video_url", "audio_url"],
                "video_preflight": {k: video_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
                "audio_preflight": {k: audio_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
            },
            raw_response_public=_public_response(payload),
        )

    def poll(self, job_id: str) -> PollResult:
        url = f"https://model-api.runcomfy.net/v1/requests/{urllib.parse.quote(job_id)}/result"
        payload = _curl_json("GET", url, api_key=self._key(), timeout=120)
        output_url = _first_output(payload)
        status = str(payload.get("status") or ("completed" if output_url else "processing"))
        return PollResult(status=status, raw_response_public=_public_response(payload), output_url=output_url)


class NativeKlingLipSyncA2VAdapter(KlingNativeLipSyncAdapter):
    """Direct Kling /v1/videos/lip-sync — same API WaveSpeed/Fal wrap for Beat Gen."""

    route_id = "native_kling_lip_sync_a2v"
    provider = "native_kling_compatible"

    def __init__(self) -> None:
        base_url, access_key, secret_key, static_key = _resolve_kling_direct_credentials()
        self.base_url = base_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.api_key = static_key
        self.lipsync_path = os.environ.get("KLING_LIP_SYNC_PATH", "/v1/videos/lip-sync")
        self.result_path = os.environ.get("KLING_LIP_SYNC_RESULT_PATH", "/v1/videos/lip-sync/{task_id}")

    def _auth_token(self) -> str:
        if self.api_key:
            return self.api_key
        if self.access_key and self.secret_key:
            return _kling_jwt_token(self.access_key, self.secret_key)
        return ""

    def _ensure(self) -> None:
        if not self.base_url or not self._auth_token():
            raise RouteBlocked(
                "blocked_missing_credentials",
                "Configure KLING_NATIVE_BASE_URL + KLING_NATIVE_API_KEY or KLING_ACCESS_KEY + KLING_SECRET_KEY",
            )

    def validate_credentials(self) -> dict:
        auth_mode = "missing"
        if self.api_key:
            auth_mode = "static_bearer"
        elif self.access_key and self.secret_key:
            auth_mode = "jwt"
        return {
            "ok": bool(self.base_url and self._auth_token()),
            "provider": self.provider,
            "route_id": self.route_id,
            "base_url_present": bool(self.base_url),
            "auth_mode": auth_mode,
        }

    def _curl_native(self, method: str, url: str, *, body: dict | None = None, timeout: int = 180) -> dict:
        self._ensure()
        payload = _curl_json(method, url, api_key=self._auth_token(), body=body, timeout=timeout)
        _raise_if_provider_error(payload, provider=self.provider)
        return payload

    def describe_schema(self) -> dict:
        return {
            "provider": self.provider,
            "route_id": self.route_id,
            "endpoint": f"{self.base_url}{self.lipsync_path}" if self.base_url else self.lipsync_path,
            "request_fields": [
                "input.video_url",
                "input.mode",
                "input.audio_type",
                "input.audio_url",
            ],
            "notes": "Beat Gen production lipsync API shape (WaveSpeed kwaivgi/kling-lipsync/audio-to-video equivalent).",
        }

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        self._ensure()
        video_proof = upload_to_hosting(video_path)
        audio_proof = upload_to_hosting(audio_path)
        lipsync_url = f"{self.base_url}{self.lipsync_path}"
        body = {
            "input": {
                "video_url": video_proof["submitted_url"],
                "mode": "audio2video",
                "audio_type": "url",
                "audio_url": audio_proof["submitted_url"],
            },
        }
        model_name = (os.environ.get("KLING_LIP_SYNC_MODEL_NAME") or "").strip()
        if model_name:
            body["input"]["model_name"] = model_name
        return self._submit_body(
            lipsync_url=lipsync_url,
            body=body,
            video_proof=video_proof,
            audio_proof=audio_proof,
            request_fields=["input.video_url", "input.mode", "input.audio_type", "input.audio_url"],
        )

    def _submit_body(
        self,
        *,
        lipsync_url: str,
        body: dict,
        video_proof: dict,
        audio_proof: dict,
        request_fields: list[str],
    ) -> SubmitResult:
        payload = self._curl_native("POST", lipsync_url, body=body, timeout=180)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        job_id = data.get("task_id") or data.get("id") or payload.get("task_id") or payload.get("id")
        if not job_id:
            raise RuntimeError(f"lip-sync response missing task id: {_public_response(payload)}")
        return SubmitResult(
            provider=self.provider,
            route_id=self.route_id,
            endpoint=lipsync_url,
            job_id=str(job_id),
            request_shape_public={
                "fields": request_fields,
                "video_preflight": {k: video_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
                "audio_preflight": {k: audio_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
            },
            raw_response_public=_public_response(payload),
        )

    def poll(self, job_id: str) -> PollResult:
        self._ensure()
        url = f"{self.base_url}{self.result_path.replace('{task_id}', urllib.parse.quote(job_id))}"
        payload = self._curl_native("GET", url, timeout=120)
        self._last_poll_payload = payload
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        status = str(data.get("task_status") or data.get("status") or payload.get("status") or "unknown").lower()
        if status == "succeed":
            status = "completed"
        output_url = _first_output(payload)
        error = None
        if status in TERMINAL_FAILURE:
            error = str(data.get("task_status_msg") or data.get("fail_reason") or payload.get("message") or "")
        return PollResult(status=status, raw_response_public=_public_response(payload), output_url=output_url, error=error)


class NativeKlingLipSyncA2VFileAdapter(NativeKlingLipSyncA2VAdapter):
    """Same as URL route but sends audio via base64 file transport per Kling docs."""

    route_id = "native_kling_lip_sync_a2v_b64"

    def describe_schema(self) -> dict:
        schema = super().describe_schema()
        schema["route_id"] = self.route_id
        schema["request_fields"] = [
            "input.video_url",
            "input.mode",
            "input.audio_type",
            "input.audio_file",
        ]
        schema["notes"] = "Native lip-sync with audio_type=file (base64) instead of audio_url."
        return schema

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        self._ensure()
        video_proof = upload_to_hosting(video_path)
        audio_bytes = audio_path.read_bytes()
        if len(audio_bytes) > 5 * 1024 * 1024:
            raise RouteBlocked("blocked_input_too_large", "audio_file base64 transport max 5MB")
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        lipsync_url = f"{self.base_url}{self.lipsync_path}"
        body = {
            "input": {
                "video_url": video_proof["submitted_url"],
                "mode": "audio2video",
                "audio_type": "file",
                "audio_file": audio_b64,
            },
        }
        audio_proof = {
            "host": "inline_base64",
            "bytes": len(audio_bytes),
            "sha256": hashlib.sha256(audio_bytes).hexdigest(),
            "content_type": "audio/mpeg",
            "status": 200,
        }
        return self._submit_body(
            lipsync_url=lipsync_url,
            body=body,
            video_proof=video_proof,
            audio_proof=audio_proof,
            request_fields=["input.video_url", "input.mode", "input.audio_type", "input.audio_file"],
        )


class NativeKlingAdvancedLipSyncAdapter(KlingNativeLipSyncAdapter):
    route_id = "native_kling_identify_face_advanced_lipsync"
    provider = "native_kling_compatible"

    def __init__(self) -> None:
        base_url, access_key, secret_key, static_key = _resolve_kling_direct_credentials()
        self.base_url = base_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.api_key = static_key
        self.identify_path = os.environ.get("KLING_IDENTIFY_FACE_PATH", "/v1/videos/identify-face")
        self.lipsync_path = os.environ.get("KLING_ADVANCED_LIPSYNC_PATH", "/v1/videos/advanced-lip-sync")
        self.result_path = os.environ.get("KLING_TASK_RESULT_PATH", "/v1/videos/advanced-lip-sync/{task_id}")

    def _auth_token(self) -> str:
        if self.api_key:
            return self.api_key
        if self.access_key and self.secret_key:
            return _kling_jwt_token(self.access_key, self.secret_key)
        return ""

    def _ensure(self) -> None:
        if not self.base_url or not self._auth_token():
            raise RouteBlocked(
                "blocked_missing_credentials",
                "Configure KLING_NATIVE_BASE_URL + KLING_NATIVE_API_KEY or KLING_ACCESS_KEY + KLING_SECRET_KEY",
            )

    def validate_credentials(self) -> dict:
        auth_mode = "missing"
        if self.api_key:
            auth_mode = "static_bearer"
        elif self.access_key and self.secret_key:
            auth_mode = "jwt"
        return {
            "ok": bool(self.base_url and self._auth_token()),
            "provider": self.provider,
            "route_id": self.route_id,
            "base_url_present": bool(self.base_url),
            "auth_mode": auth_mode,
        }

    def _curl_native(self, method: str, url: str, *, body: dict | None = None, timeout: int = 180) -> dict:
        self._ensure()
        payload = _curl_json(method, url, api_key=self._auth_token(), body=body, timeout=timeout)
        _raise_if_provider_error(payload, provider=self.provider)
        return payload

    def describe_schema(self) -> dict:
        return {
            "provider": self.provider,
            "route_id": self.route_id,
            "identify_endpoint": f"{self.base_url}{self.identify_path}" if self.base_url else self.identify_path,
            "lipsync_endpoint": f"{self.base_url}{self.lipsync_path}" if self.base_url else self.lipsync_path,
            "request_fields": ["video_url", "session_id", "face_choose[].face_id", "face_choose[].sound_file"],
        }

    @staticmethod
    def _extract_session_and_face(payload: dict) -> tuple[str, str]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        session_id = str(data.get("session_id") or data.get("sessionId") or "")
        faces = data.get("face_infos") or data.get("faces") or data.get("face_data") or data.get("face_list") or []
        face_id = ""
        if isinstance(faces, list) and faces:
            first = faces[0]
            if isinstance(first, dict):
                face_id = str(first.get("face_id") or first.get("faceId") or first.get("id") or "")
        if not face_id and isinstance(data.get("face_id"), str):
            face_id = data["face_id"]
        if not session_id or not face_id:
            raise RuntimeError(f"identify-face response missing session/face: {_public_response(payload)}")
        return session_id, face_id

    def submit(self, *, video_path: Path, audio_path: Path, work_dir: Path) -> SubmitResult:
        self._ensure()
        video_proof = upload_to_hosting(video_path)
        audio_proof = upload_to_hosting(audio_path)
        identify_url = f"{self.base_url}{self.identify_path}"
        lipsync_url = f"{self.base_url}{self.lipsync_path}"
        identify_payload = self._curl_native(
            "POST",
            identify_url,
            body={"video_url": video_proof["submitted_url"]},
            timeout=180,
        )
        session_id, face_id = self._extract_session_and_face(identify_payload)
        sound_end_time = min(_audio_duration_ms(audio_path), _video_duration_ms(video_path))
        body = {
            "session_id": session_id,
            "face_choose": [{
                "face_id": face_id,
                "sound_file": audio_proof["submitted_url"],
                "sound_start_time": 0,
                "sound_end_time": sound_end_time,
                "sound_insert_time": 0,
                "sound_volume": 1,
                "original_audio_volume": 0,
            }],
        }
        payload = self._curl_native("POST", lipsync_url, body=body, timeout=180)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        job_id = data.get("task_id") or data.get("id") or payload.get("task_id") or payload.get("id")
        if not job_id:
            raise RuntimeError(f"advanced-lip-sync response missing task id: {_public_response(payload)}")
        return SubmitResult(
            provider=self.provider,
            route_id=self.route_id,
            endpoint=lipsync_url,
            job_id=str(job_id),
            request_shape_public={
                "identify_fields": ["video_url"],
                "lipsync_fields": ["session_id", "face_choose", "face_choose[].sound_end_time"],
                "video_preflight": {k: video_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
                "audio_preflight": {k: audio_proof.get(k) for k in ("host", "bytes", "sha256", "content_type", "status")},
            },
            raw_response_public={
                "identify": _public_response(identify_payload),
                "lipsync": _public_response(payload),
            },
        )

    def poll(self, job_id: str) -> PollResult:
        self._ensure()
        url = f"{self.base_url}{self.result_path.replace('{task_id}', urllib.parse.quote(job_id))}"
        payload = self._curl_native("GET", url, timeout=120)
        self._last_poll_payload = payload
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        status = str(data.get("task_status") or data.get("status") or payload.get("status") or "unknown").lower()
        if status == "succeed":
            status = "completed"
        output_url = _first_output(payload)
        return PollResult(status=status, raw_response_public=_public_response(payload), output_url=output_url)


def get_route_registry() -> dict[str, KlingNativeLipSyncAdapter]:
    return {
        "wavespeed_kling_lipsync_baseline": WaveSpeedKlingLipSyncBaselineAdapter(),
        "fal_kling_lipsync_a2v": FalKlingLipSyncAdapter(),
        "runcomfy_kling_lipsync_a2v": RunComfyKlingLipSyncAdapter(),
        "native_kling_lip_sync_a2v": NativeKlingLipSyncA2VAdapter(),
        "native_kling_lip_sync_a2v_b64": NativeKlingLipSyncA2VFileAdapter(),
        "native_kling_identify_face_advanced_lipsync": NativeKlingAdvancedLipSyncAdapter(),
    }


def route_statuses() -> list[dict]:
    statuses = []
    for route_id, adapter in get_route_registry().items():
        try:
            credential = adapter.validate_credentials()
        except Exception as exc:
            credential = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        statuses.append({
            "route_id": route_id,
            "provider": adapter.provider,
            "schema": adapter.describe_schema(),
            "credential": credential,
        })
    return statuses


def wait_for_result(adapter: KlingNativeLipSyncAdapter, job_id: str, *, timeout_s: int = 900, interval_s: int = 15) -> PollResult:
    deadline = time.time() + timeout_s
    last = PollResult(status="unknown", raw_response_public={})
    while time.time() < deadline:
        last = adapter.poll(job_id)
        status = (last.status or "").lower()
        if status in TERMINAL_SUCCESS and last.output_url:
            return last
        if status in TERMINAL_FAILURE:
            return last
        time.sleep(interval_s)
    return PollResult(
        status="timeout",
        raw_response_public=last.raw_response_public,
        output_url=last.output_url,
        error=f"timeout after {timeout_s}s",
    )

