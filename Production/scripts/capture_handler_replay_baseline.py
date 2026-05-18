#!/usr/bin/env python3
"""Capture handler replay baseline — V59 Phase 4-prep.

For every route in openapi yaml, probe with a stub payload and record:
  - status
  - body sha256
  - body length
  - content-type
  - latency_ms

Output: Production/tests/handler_replay_baseline.json (single dict keyed by
'METHOD path'; each value has the response fingerprint).

Used by replay_handler_diff.py to verify byte-equivalence after handler
extraction in Phase 4.

Stub bodies are deterministic. Endpoints that need real state (e.g.,
beat_id) use 'beat_99' (won't exist) — we expect 4xx; that's still a valid
fingerprint as long as it's reproducible.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = ROOT / "openapi" / "production_server.yaml"
BASELINE_PATH = ROOT / "tests" / "handler_replay_baseline.json"
BASE_URL = "http://localhost:5111"
PROBE_TIMEOUT_S = 5.0

POST_PROFILES: dict[str, dict[str, Any]] = {
    "/api/beat/animate": {"beat_id": "beat_99", "audio_delay": 0.0},
    "/api/beat/done_toggle": {"beat_id": "beat_99"},
    "/api/beat/use_as_final": {"beat_id": "beat_99", "role": "intro"},
    "/api/beat/use_still_as_final": {"beat_id": "beat_99"},
    "/api/beat/trim": {"beat_id": "beat_99", "trim_start": 0.0, "trim_end": 1.0},
    "/api/beat/regen_bc": {"beat_id": "beat_99"},
    "/api/cr/library": {"_stub": True},
    "/api/cr/full_image": {"_stub": True},
    "/api/cr/library_delete": {"asset_id": 999999},
    "/api/bg/": {"beat_id": "beat_99", "_stub": True},
    "/api/lipsync/": {"beat_id": "beat_99", "_stub": True},
    "/api/phase_a/": {"beat_id": "beat_99", "_stub": True},
    "/api/phase_b/": {"beat_id": "beat_99", "_stub": True},
    "/api/stitch": {"_stub": True},
    "/api/event/load": {"event_id": "Event_99"},
    "/api/video/create": {"video_role": "test_role_99"},
    "/api/video/set_active": {"video_role": "intro"},
    "/api/admin/": {"_stub": True},
    "/api/v2/beat/": {"beat_id": "beat_99", "_stub": True},
    "/api/v2/": {"_stub": True},
    "/api/patch_health": {"patch_id": "TEST_PATCH_99"},
    "/api/state_snapshot": {"_stub": True},
    "/api/magic/": {"_stub": True},
    "/api/milestones": {"_stub": True},
    "/api/voice/": {"_stub": True},
}

SKIP_ENDPOINTS: dict[tuple[str, str], str] = {
    ("POST", "/api/event/create"): "mutates Event_* directory creation",
    ("POST", "/api/event/load"): "switches active event (mutates server state)",
    ("POST", "/api/video/create"): "mutates state.json",
    ("POST", "/api/admin/drain_start"): "flips drain flag (server-wide)",
    ("POST", "/api/admin/drain_end"): "flips drain flag",
}

_PATH_BLOCK_RE = re.compile(
    r"^  (/[^\n:]+):\n((?:    [^\n]+\n)*)",
    re.MULTILINE,
)


def route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def parse_key(key: str) -> tuple[str, str]:
    method, _, path = key.partition(" ")
    return method.upper(), path


def load_openapi_routes(yaml_path: Path | None = None) -> list[tuple[str, str]]:
    """Return (METHOD, path_template) pairs from OpenAPI, sorted for stability."""
    path = yaml_path or OPENAPI_PATH
    text = path.read_text(encoding="utf-8")
    routes = _parse_routes_yaml(text)
    if not routes:
        routes = _parse_routes_regex(text)
    routes.sort(key=lambda r: (r[1], r[0]))
    return routes


def _parse_routes_yaml(text: str) -> list[tuple[str, str]]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return []
    try:
        doc = yaml.safe_load(text)
    except Exception:
        return []
    paths = doc.get("paths") or {}
    routes: list[tuple[str, str]] = []
    for path_template, spec in paths.items():
        if not isinstance(spec, dict):
            continue
        if "get" in spec:
            routes.append(("GET", path_template))
        if "post" in spec:
            routes.append(("POST", path_template))
    return routes


def _parse_routes_regex(text: str) -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for m in _PATH_BLOCK_RE.finditer(text):
        path_template = m.group(1)
        block = m.group(2)
        if re.search(r"^    get:\s*$", block, re.MULTILINE):
            routes.append(("GET", path_template))
        if re.search(r"^    post:\s*$", block, re.MULTILINE):
            routes.append(("POST", path_template))
    return routes


def substitute_path_params(path_template: str) -> str:
    return (
        path_template.replace("{beat_id}", "beat_99")
        .replace("{id}", "99")
        .replace("{fname}", "nonexistent.bin")
        .replace("{param}", "placeholder")
    )


def post_body_for_path(path_template: str) -> dict[str, Any]:
    for prefix in sorted(POST_PROFILES.keys(), key=len, reverse=True):
        if path_template.startswith(prefix):
            return dict(POST_PROFILES[prefix])
    return {"_stub": True}


def skipped_fingerprint(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": reason}


def probe_route(
    method: str,
    path_template: str,
    *,
    base_url: str = BASE_URL,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Probe one route; return fingerprint or skipped/error record."""
    method = method.upper()
    skip_reason = SKIP_ENDPOINTS.get((method, path_template))
    if skip_reason:
        return skipped_fingerprint(skip_reason)

    path = substitute_path_params(path_template)
    url = f"{base_url.rstrip('/')}{path}"
    started = time.perf_counter()

    try:
        if method == "GET":
            req = urllib.request.Request(url, method="GET")
        elif method == "POST":
            payload = json.dumps(post_body_for_path(path_template), sort_keys=True).encode(
                "utf-8"
            )
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            return {
                "status": "error",
                "reason": f"unsupported method {method}",
                "latency_ms": 0,
            }

        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = resp.read()
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            body = exc.read()
            status = exc.code
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""

        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "status": status,
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "body_len": len(body),
            "content_type": content_type,
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001 — probe harness records all failures
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "status": "error",
            "reason": str(exc),
            "latency_ms": latency_ms,
        }


def collect_fingerprints(
    routes: list[tuple[str, str]] | None = None,
    *,
    base_url: str = BASE_URL,
    timeout_s: float = PROBE_TIMEOUT_S,
) -> dict[str, dict[str, Any]]:
    if routes is None:
        routes = load_openapi_routes()
    out: dict[str, dict[str, Any]] = {}
    for method, path_template in routes:
        key = route_key(method, path_template)
        out[key] = probe_route(method, path_template, base_url=base_url, timeout_s=timeout_s)
    return dict(sorted(out.items()))


def summarize(fingerprints: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {"routes": len(fingerprints), "2xx": 0, "4xx": 0, "5xx": 0, "errors": 0, "skipped": 0}
    for fp in fingerprints.values():
        status = fp.get("status")
        if status == "skipped":
            counts["skipped"] += 1
        elif status == "error":
            counts["errors"] += 1
        elif isinstance(status, int):
            if 200 <= status < 300:
                counts["2xx"] += 1
            elif 400 <= status < 500:
                counts["4xx"] += 1
            elif 500 <= status < 600:
                counts["5xx"] += 1
        else:
            counts["errors"] += 1
    return counts


def write_baseline(
    fingerprints: dict[str, dict[str, Any]],
    out_path: Path | None = None,
) -> Path:
    dest = out_path or BASELINE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return dest


def main() -> int:
    routes = load_openapi_routes()
    fingerprints = collect_fingerprints(routes)
    write_baseline(fingerprints)
    stats = summarize(fingerprints)
    print(
        "BASELINE_CAPTURED "
        f"routes={stats['routes']} "
        f"2xx={stats['2xx']} "
        f"4xx={stats['4xx']} "
        f"5xx={stats['5xx']} "
        f"errors={stats['errors']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
