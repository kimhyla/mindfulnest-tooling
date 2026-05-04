"""
WaveSpeed poll client — long-lived polling against animation/lipsync endpoints.

Spec v2 §C9 SPLIT + LD-137 POLL_CLIENT_ROOT_CAUSE_HTTP_CLIENT: this client uses http.client directly
(NOT urllib/requests) because long polls hit a TLS session resumption bug that causes connection
hangs after ~30s. The fix is fresh SSL context per call + OP_NO_TICKET + OP_NO_COMPRESSION.

Do NOT use requests or urllib for polling WaveSpeed predictions — they share connection pools and
inherit the hang. Use this client for every `GET /api/v3/predictions/{id}/result` call.

Short-lived WaveSpeed POSTs (submit animation/lipsync job) can use requests/urllib; the hang is
specific to long pollers.

Usage:
    from lib.wavespeed_poll_client import WaveSpeedPollClient
    client = WaveSpeedPollClient(api_key=os.environ["WAVESPEED_API_KEY"])
    result = client.poll_prediction("abc123", max_wait_s=900, poll_interval_s=5)
"""

from __future__ import annotations
import http.client
import json
import ssl
import time
import os
from dataclasses import dataclass
from typing import Optional


WAVESPEED_HOST = "api.wavespeed.ai"
POLL_PATH_TEMPLATE = "/api/v3/predictions/{prediction_id}/result"


@dataclass
class PollResult:
    status: str  # "succeeded" | "failed" | "running" | "queued" | ...
    output: Optional[dict]
    error: Optional[str]
    raw: dict


class WaveSpeedPollError(Exception):
    pass


class WaveSpeedPollClient:
    """
    Long-poll client for WaveSpeed. Fresh SSL context per call prevents TLS session-ticket hangs
    (LD-137 root cause).

    Never share connection objects across polls. Always create HTTPSConnection fresh.
    """

    def __init__(self, api_key: Optional[str] = None, host: str = WAVESPEED_HOST):
        self.api_key = api_key or os.environ.get("WAVESPEED_API_KEY")
        if not self.api_key:
            raise RuntimeError("WaveSpeed API key not found. Set WAVESPEED_API_KEY env.")
        self.host = host

    def _make_ssl_context(self) -> ssl.SSLContext:
        """
        Fresh SSL context per call per LD-137. Key options:
        - OP_NO_TICKET: disables TLS session tickets (prevents server-side state reuse that causes hangs)
        - OP_NO_COMPRESSION: disables TLS compression (CRIME attack + reduces state)
        """
        ctx = ssl.create_default_context()
        ctx.options |= ssl.OP_NO_TICKET
        ctx.options |= ssl.OP_NO_COMPRESSION
        return ctx

    def get_prediction_result(self, prediction_id: str, timeout_s: float = 30.0) -> PollResult:
        """
        Single GET against prediction result endpoint. Fresh connection, fresh SSL context.
        Returns PollResult with parsed status/output.
        """
        conn = http.client.HTTPSConnection(self.host, timeout=timeout_s, context=self._make_ssl_context())
        try:
            path = POLL_PATH_TEMPLATE.format(prediction_id=prediction_id)
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Connection": "close",  # explicit: don't pool
            }
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode()
            if resp.status >= 400:
                raise WaveSpeedPollError(f"HTTP {resp.status}: {body[:200]}")
            data = json.loads(body).get("data", {})
            return PollResult(
                status=data.get("status", "unknown"),
                output=data.get("output"),
                error=data.get("error"),
                raw=data,
            )
        finally:
            conn.close()

    def poll_prediction(
        self,
        prediction_id: str,
        max_wait_s: float = 900.0,
        poll_interval_s: float = 5.0,
        timeout_per_call_s: float = 30.0,
    ) -> PollResult:
        """
        Poll prediction_id until status is terminal (succeeded | failed | canceled) OR max_wait_s elapses.

        Terminal statuses return immediately. Non-terminal statuses sleep poll_interval_s then retry.
        Each call uses a fresh HTTPS connection (LD-137 safety).
        """
        start = time.monotonic()
        terminal = {"succeeded", "completed", "failed", "canceled", "cancelled", "error"}

        while True:
            result = self.get_prediction_result(prediction_id, timeout_s=timeout_per_call_s)
            if result.status.lower() in terminal:
                return result
            elapsed = time.monotonic() - start
            if elapsed >= max_wait_s:
                raise WaveSpeedPollError(
                    f"Prediction {prediction_id} did not reach terminal status within {max_wait_s}s "
                    f"(last status: {result.status})"
                )
            time.sleep(poll_interval_s)


if __name__ == "__main__":
    # Smoke test: verify fresh SSL context creation.
    # OP_NO_TICKET must be explicitly set (off by default).
    # OP_NO_COMPRESSION may be 0x0 on modern Python (OpenSSL built without compression — already disabled
    # at the library level). If it's non-zero we check the bit is set; if 0x0 we note compression is
    # already unavailable.
    client = WaveSpeedPollClient(api_key="smoke-test-key")
    ctx = client._make_ssl_context()
    assert ctx.options & ssl.OP_NO_TICKET, "OP_NO_TICKET not set"
    if ssl.OP_NO_COMPRESSION != 0:
        assert ctx.options & ssl.OP_NO_COMPRESSION, "OP_NO_COMPRESSION not set"
        compression_note = "explicitly disabled"
    else:
        compression_note = "already unavailable at OpenSSL build level (0x0)"
    print(f"SSL context smoke test: OK (OP_NO_TICKET set; compression {compression_note})")
