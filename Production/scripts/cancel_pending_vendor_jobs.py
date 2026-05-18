#!/usr/bin/env python3
"""Cancel or mark uncancellable overnight vendor jobs in vendor_calls_overnight.

Per V59 spec §0 Phase 0 / Agent A amendment A4. Queries submitted rows and
attempts vendor-specific cancel; writes summary to prod_activity_log via
try_post_or_queue (Rule 35).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus import try_patch_or_queue, try_post_or_queue  # noqa: E402
from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402

KEYS_PATH = ROOT / "API_KEYS_MASTER.md"
HTTP_TIMEOUT_S = 30


def _load_wavespeed_key() -> Optional[str]:
    key = os.environ.get("WAVESPEED_API_KEY")
    if key:
        return key
    if KEYS_PATH.is_file():
        import re

        content = KEYS_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"#+\s*WaveSpeed.*?(?:Key|Token):\s*`([^`]+)`",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    return None


def _load_bfl_key() -> Optional[str]:
    key = os.environ.get("BFL_API_KEY")
    if key:
        return key
    if KEYS_PATH.is_file():
        import re

        content = KEYS_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"\|\s*\*+(?:Flux|BFL|Black\s*Forest)[^|]*\*+[^|]*\|\s*`([^`]+)`",
            content,
            re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    return None


def _http_post(url: str, headers: dict[str, str], data: Optional[bytes] = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _patch_row(client: DirectusAdminClient, row_id: Any, status: str, *, cancelled: bool) -> None:
    payload: dict[str, Any] = {"status": status}
    if cancelled:
        payload["cancelled_at"] = _now_iso()
    try_patch_or_queue("vendor_calls_overnight", row_id, payload, client=client)


def _try_wavespeed_cancel(vendor_call_id: str, ws_key: str) -> tuple[bool, str]:
    url = f"https://api.wavespeed.ai/api/v3/predictions/{vendor_call_id}/cancel"
    status, body = _http_post(url, {"Authorization": f"Bearer {ws_key}"})
    if 200 <= status < 300:
        return True, "cancel_ok"
    return False, f"http_{status}:{body[:120]!r}"


def _bfl_still_pending(vendor_call_id: str, bfl_key: str) -> tuple[bool, str]:
    url = f"https://api.bfl.ai/v1/get_result?id={vendor_call_id}"
    status, body = _http_get(url, {"x-key": bfl_key})
    if status >= 400:
        return False, f"http_{status}"
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return False, "invalid_json"
    st = data.get("Status") or data.get("status") or ""
    if str(st).lower() == "pending":
        return True, "pending"
    return False, f"status={st!r}"


def _process_row(
    row: dict,
    client: DirectusAdminClient,
    ws_key: Optional[str],
    bfl_key: Optional[str],
) -> tuple[str, str, str, str]:
    """Returns (outcome_tag, vendor, call_id, reason)."""
    vendor = (row.get("vendor") or "").strip().lower()
    call_id = str(row.get("vendor_call_id") or row.get("id") or "")
    row_id = row.get("id")

    if vendor in ("bytedance", "kling", "wavespeed"):
        if not ws_key:
            if row_id is not None:
                _patch_row(client, row_id, "uncancellable", cancelled=False)
            return "UNCANCEL", vendor, call_id, "missing_wavespeed_key"
        ok, reason = _try_wavespeed_cancel(call_id, ws_key)
        if ok and row_id is not None:
            _patch_row(client, row_id, "cancelled", cancelled=True)
            return "CANCEL", vendor, call_id, reason
        if row_id is not None:
            _patch_row(client, row_id, "uncancellable", cancelled=False)
        return "UNCANCEL" if not ok else "FAIL", vendor, call_id, reason

    if vendor == "openai":
        if row_id is not None:
            _patch_row(client, row_id, "uncancellable", cancelled=False)
        return "UNCANCEL", vendor, call_id, "gpt_image_no_cancel_endpoint"

    if vendor == "elevenlabs":
        if row_id is not None:
            _patch_row(client, row_id, "uncancellable", cancelled=False)
        return "UNCANCEL", vendor, call_id, "tts_short_lived"

    if vendor == "bfl_flux":
        if not bfl_key:
            if row_id is not None:
                _patch_row(client, row_id, "uncancellable", cancelled=False)
            return "UNCANCEL", vendor, call_id, "missing_bfl_key"
        pending, reason = _bfl_still_pending(call_id, bfl_key)
        if pending and row_id is not None:
            _patch_row(client, row_id, "uncancellable", cancelled=False)
            return "UNCANCEL", vendor, call_id, "pending_no_cancel_endpoint"
        if row_id is not None:
            _patch_row(client, row_id, "uncancellable", cancelled=False)
        return "UNCANCEL", vendor, call_id, reason or "not_pending"

    # Unknown vendor — try wavespeed cancel, fall back uncancellable
    if ws_key:
        ok, reason = _try_wavespeed_cancel(call_id, ws_key)
        if ok and row_id is not None:
            _patch_row(client, row_id, "cancelled", cancelled=True)
            return "CANCEL", vendor, call_id, reason
    if row_id is not None:
        _patch_row(client, row_id, "uncancellable", cancelled=False)
    return "UNCANCEL", vendor, call_id, "unknown_vendor_fallback"


def cancel_all_pending() -> dict:
    """Run cancel pass; return summary counts dict."""
    client = DirectusAdminClient()
    rows = client.get_items(
        "vendor_calls_overnight",
        filters={"status": {"_eq": "submitted"}},
        limit=-1,
    ) or []

    ws_key = _load_wavespeed_key()
    bfl_key = _load_bfl_key()

    counts = {"CANCEL": 0, "UNCANCEL": 0, "FAIL": 0}
    for row in rows:
        tag, vendor, call_id, reason = _process_row(row, client, ws_key, bfl_key)
        counts[tag] = counts.get(tag, 0) + 1
        print(f"[{tag}] vendor={vendor} call_id={call_id} reason={reason}")

    details = {
        "submitted_rows": len(rows),
        "cancelled": counts.get("CANCEL", 0),
        "uncancellable": counts.get("UNCANCEL", 0),
        "failed": counts.get("FAIL", 0),
        "at": _now_iso(),
    }
    try_post_or_queue(
        "prod_activity_log",
        {
            "action": "OVERNIGHT_VENDOR_JOBS_CANCEL_ATTEMPT",
            "details": details,
            "performed_by": "cancel_pending_vendor_jobs",
        },
        client=client,
    )
    return details


def main() -> int:
    cancel_all_pending()
    return 0


if __name__ == "__main__":
    sys.exit(main())
