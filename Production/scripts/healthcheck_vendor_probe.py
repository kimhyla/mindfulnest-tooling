#!/usr/bin/env python3
"""Phase 0 vendor connectivity probe — cheapest call per vendor (5 probes).

Per V59 spec §0 Phase 0 / Agent A amendment A4. Pings WaveSpeed, OpenAI,
ElevenLabs, BFL FLUX, and Directus; prints PASS/FAIL per vendor and exits 0
only when all five pass.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from Production.lib.directus_admin_client import DirectusAdminClient  # noqa: E402

PROBE_TIMEOUT_S = 5


def _resolve_keys_path() -> Path:
    """Find API_KEYS_MASTER.md across dual-canonical roots (LD-505).

    Tooling tree first (if a copy exists), then Dropbox tree, then env override.
    """
    env_override = os.environ.get("MN_API_KEYS_PATH")
    if env_override:
        p = Path(env_override).expanduser()
        if p.is_file():
            return p
    candidates = [
        ROOT / "API_KEYS_MASTER.md",
        Path.home() / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/API_KEYS_MASTER.md",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


KEYS_PATH = _resolve_keys_path()


def _parse_keys_from_md(filepath: Path) -> dict[str, str]:
    keys: dict[str, str] = {}
    if not filepath.is_file():
        return keys
    content = filepath.read_text(encoding="utf-8")
    for section, key_name in [
        ("WaveSpeed", "wavespeed"),
        ("ElevenLabs", "elevenlabs"),
        ("OpenAI", "openai"),
        ("Flux|BFL|Black Forest", "bfl"),
    ]:
        m = re.search(
            rf"#+\s*(?:{section}).*?(?:Key|Token):\s*`([^`]+)`",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        if not m:
            m = re.search(
                rf"\|\s*\**(?:{section})[^|]*\**[^|]*\|\s*`([^`]+)`",
                content,
                re.IGNORECASE,
            )
        if m and m.group(1):
            keys[key_name] = m.group(1).strip()
    # OpenAI sk-proj in table rows
    if "openai" not in keys:
        for line in content.splitlines():
            if "OpenAI" in line or "sk-proj" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    candidate = parts[2].strip().strip("`").strip()
                    if candidate.startswith(("sk-proj-", "sk-")):
                        keys["openai"] = candidate
                        break
    # BFL alternate table label
    if "bfl" not in keys:
        m = re.search(
            r"\|\s*\*+(?:Flux|BFL|Black\s*Forest)[^|]*\*+[^|]*\|\s*`([^`]+)`",
            content,
            re.IGNORECASE,
        )
        if m:
            keys["bfl"] = m.group(1).strip()
    return keys


def _load_api_keys() -> dict[str, str]:
    try:
        from Production.lib import api_keys as ak  # type: ignore

        if hasattr(ak, "parse_api_keys"):
            keys = ak.parse_api_keys(KEYS_PATH)
            if isinstance(keys, dict):
                return {k: v for k, v in keys.items() if v}
    except Exception:
        pass
    keys = _parse_keys_from_md(KEYS_PATH)
    overlay = {
        "wavespeed": os.environ.get("WAVESPEED_API_KEY"),
        "elevenlabs": os.environ.get("ELEVENLABS_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "bfl": os.environ.get("BFL_API_KEY"),
    }
    for k, v in overlay.items():
        if v:
            keys[k] = v
    return keys


def _http_get(
    url: str,
    headers: dict[str, str],
    *,
    timeout: float = PROBE_TIMEOUT_S,
) -> tuple[int, bytes, int]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return resp.status, body, latency_ms
    except urllib.error.HTTPError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return e.code, e.read(), latency_ms


def _result_line(passed: bool, vendor: str, latency_ms: int, note: str) -> str:
    tag = "PASS" if passed else "FAIL"
    return f"[{tag}] vendor={vendor} latency_ms={latency_ms} note={note}"


def _probe_wavespeed(key: Optional[str]) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "missing_key"
    status, body, latency_ms = _http_get(
        "https://api.wavespeed.ai/api/v3/balance",
        {"Authorization": f"Bearer {key}"},
    )
    if not (200 <= status < 300):
        return False, latency_ms, f"http_{status}"
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return False, latency_ms, "invalid_json"
    if "balance" in data or (isinstance(data.get("data"), dict) and "balance" in data["data"]):
        return True, latency_ms, "balance_ok"
    return False, latency_ms, "no_balance_field"


def _probe_openai(key: Optional[str]) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "missing_key"
    status, _body, latency_ms = _http_get(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {key}"},
    )
    if 200 <= status < 300:
        return True, latency_ms, "models_ok"
    return False, latency_ms, f"http_{status}"


def _probe_elevenlabs(key: Optional[str]) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "missing_key"
    status, body, latency_ms = _http_get(
        "https://api.elevenlabs.io/v1/user",
        {"xi-api-key": key},
    )
    if not (200 <= status < 300):
        return False, latency_ms, f"http_{status}"
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return False, latency_ms, "invalid_json"
    if "subscription" in data:
        return True, latency_ms, "subscription_ok"
    return False, latency_ms, "no_subscription_field"


def _probe_bfl(key: Optional[str]) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "missing_key"
    status, body, latency_ms = _http_get(
        "https://api.bfl.ai/v1/get_result?id=probe_does_not_exist",
        {"x-key": key},
    )
    if status in (401, 403):
        return False, latency_ms, f"auth_fail_{status}"
    # 400/404 both indicate auth worked but ID was rejected (BFL returns
    # 400 "Invalid UUID format" for non-UUID probe ids; 404 for valid-UUID
    # but missing ids). Either proves the key is good.
    if status in (400, 404):
        try:
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, dict) and data:
                return True, latency_ms, f"auth_ok_http_{status}"
        except json.JSONDecodeError:
            pass
        return True, latency_ms, f"auth_ok_http_{status}"
    return False, latency_ms, f"unexpected_http_{status}"


def _probe_directus() -> tuple[bool, int, str]:
    t0 = time.perf_counter()
    try:
        client = DirectusAdminClient()
        rows = client.get_items(
            "prod_locked_decisions",
            filters={"id": {"_eq": 1}},
            fields=["id"],
            limit=1,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if rows is None:
            return False, latency_ms, "null_response"
        return True, latency_ms, f"rows={len(rows)}"
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return False, latency_ms, type(e).__name__


def main() -> int:
    keys = _load_api_keys()
    probes: list[tuple[str, tuple[bool, int, str]]] = [
        ("wavespeed", _probe_wavespeed(keys.get("wavespeed"))),
        ("openai", _probe_openai(keys.get("openai"))),
        ("elevenlabs", _probe_elevenlabs(keys.get("elevenlabs"))),
        ("bfl_flux", _probe_bfl(keys.get("bfl"))),
        ("directus", _probe_directus()),
    ]
    count_pass = 0
    count_fail = 0
    for vendor, (passed, latency_ms, note) in probes:
        print(_result_line(passed, vendor, latency_ms, note))
        if passed:
            count_pass += 1
        else:
            count_fail += 1
    overall = count_fail == 0
    print(
        f"HEALTHCHECK_RESULT: {'PASS' if overall else 'FAIL'} "
        f"count_pass={count_pass} count_fail={count_fail}"
    )
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
