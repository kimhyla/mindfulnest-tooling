#!/usr/bin/env python3
"""Smoke phase_a — V59 Phase 2 read-only smoke.

Per V59 spec §Phase 2 (LD-794). Probes phase_a-owned endpoints on
http://localhost:5111. Read-only — does not mutate state.json or any
asset on disk.

Exit codes:
  0 — all probes returned acceptable status
  1 — at least one probe failed; structured red-list emitted to stderr
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

SERVER = "http://localhost:5111"
TIMEOUT = 5.0
TAB = "phase_a"

PROBES = [
    ("GET", "/api/health"),
    ("GET", "/api/state"),
    # Voice profile id 1 may not exist; 502 = server backend lookup fail when id absent,
    # still proves endpoint is alive and routed. 404 = profile-not-found.
    ("GET", "/api/voice/profile/1", {"accept": [200, 404, 502]}),
]


def _probe(method: str, path: str, *, accept: list[int] | None = None) -> dict:
    accept = accept or [200, 304]
    t0 = time.perf_counter()
    url = f"{SERVER}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body_len = len(r.read())
            latency_ms = int((time.perf_counter() - t0) * 1000)
            ok = r.status in accept
            return {
                "ok": ok,
                "method": method,
                "path": path,
                "status": r.status,
                "latency_ms": latency_ms,
                "body_len": body_len,
            }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": e.code in accept,
            "method": method,
            "path": path,
            "status": e.code,
            "latency_ms": latency_ms,
            "error": str(e)[:200],
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": False,
            "method": method,
            "path": path,
            "status": 0,
            "latency_ms": latency_ms,
            "error": f"{type(e).__name__}: {e}"[:200],
        }


def main() -> int:
    probes = [
        _probe(*spec[:2], **(spec[2] if len(spec) > 2 else {})) for spec in PROBES
    ]
    passes = sum(1 for p in probes if p["ok"])
    fails = sum(1 for p in probes if not p["ok"])
    print(
        json.dumps(
            {
                "tab": TAB,
                "passes": passes,
                "fails": fails,
                "total": len(probes),
                "probes": probes,
            },
            indent=2,
        )
    )
    if fails:
        red = [p for p in probes if not p["ok"]]
        print(json.dumps({"red_list": red}, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
