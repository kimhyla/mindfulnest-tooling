#!/usr/bin/env python3
"""One-shot milestone mux warm with step logging (operator diagnostic)."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:5112"
JOB = "milestone_milestone1_arc1_stitch"
EVENT_DIR = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_2"
)
BUILDS = EVENT_DIR / "stitch_artifact_build_jobs"
MILESTONE_STITCH = Path.home() / (
    "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/"
    "Production/Milestones/milestone1_arc1/stitch_state.json"
)


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def request(method: str, path: str, data: dict | None = None, timeout: float = 60.0):
    url = f"{BASE}{path}"
    body = None
    headers = {"Content-Type": "application/json"}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw[:2000]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, {"_raw": raw[:2000]}
    except Exception as exc:
        return 0, {"error": repr(exc)}


def standalone_slot() -> dict:
    status, body = request("GET", f"/api/stitch_editor/job/{JOB}", timeout=120.0)
    if status != 200:
        log(f"GET job failed HTTP {status}: {body!r}")
        return {}
    job = body.get("job") or {}
    return (job.get("slots") or {}).get("standalone") or {}


def latest_builds(n: int = 3) -> list[dict]:
    if not BUILDS.is_dir():
        return []
    rows = []
    for p in sorted(BUILDS.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:n]:
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return rows


def drain_load_job(name: str, label: str, max_s: float = 120.0) -> None:
    log(f"drain {label} ...")
    deadline = time.monotonic() + max_s
    while time.monotonic() < deadline:
        t0 = time.monotonic()
        status, body = request("GET", f"/api/stitch_editor/job/{name}", timeout=300.0)
        elapsed = time.monotonic() - t0
        log(f"  GET {name} HTTP {status} in {elapsed:.1f}s")
        if status != 200:
            break
        job = body.get("job") or {}
        if not job.get("artifact_build_active") and not job.get("active_bake_job_id"):
            log(f"  {label} drain ok")
            return
        time.sleep(2.0)
    log(f"  WARN {label} drain timeout")


def main() -> int:
    log("=== milestone mux diagnostic warm ===")
    slot = standalone_slot()
    log(
        f"before: mux={slot.get('mux_preview_hash')!r} "
        f"ambient={slot.get('ambient_mix_hash')!r} "
        f"video={(slot.get('video_path') or '')[-50:]!r}"
    )

    drain_load_job("Event_2_stitch", "Event_2_stitch")
    drain_load_job(JOB, "milestone job")

    slot = standalone_slot()
    cues = slot.get("sfx_cues") or []
    slot_for_preview = {
        **slot,
        "ambient_bed": slot.get("ambient_bed") or "Intro video ambient bed",
        "ambient_volume": slot.get("ambient_volume")
        if slot.get("ambient_volume") is not None
        else 0.15,
        "sfx_cues": cues,
    }

    status, cur = request("GET", "/api/event/current", timeout=15.0)
    scope_version = (cur.get("event_generation") if isinstance(cur, dict) else None) or 1
    log(f"event_generation={scope_version}")

    builds_before = {p.name for p in BUILDS.glob("*.json")} if BUILDS.is_dir() else set()
    log("POST stitch_editor/preview (timeout 900s) ...")
    t0 = time.monotonic()
    status, body = request(
        "POST",
        "/api/stitch_editor/preview",
        {
            "name": JOB,
            "slot": "standalone",
            "slot_preview": True,
            "transitions": [],
            "slots": [slot_for_preview],
            "scope_event_id": "Event_2",
            "scope_milestone_id": "milestone1_arc1",
            "scope_video_role": "standalone",
            "scope_target_video": "standalone",
            "event_id": "Event_2",
            "scope_version": scope_version,
        },
        timeout=900.0,
    )
    elapsed = time.monotonic() - t0
    log(f"POST preview HTTP {status} in {elapsed:.1f}s")
    if status == 200:
        log(
            f"  response mux={body.get('mux_preview_hash')!r} "
            f"cache_hit={body.get('cache_hit')} "
            f"orchestrator={body.get('orchestrator_code')}"
        )
    else:
        log(f"  error body: {json.dumps(body)[:1500]}")

    new_builds = []
    if BUILDS.is_dir():
        for p in BUILDS.glob("*.json"):
            if p.name not in builds_before:
                try:
                    new_builds.append(json.loads(p.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    pass
    if new_builds:
        for b in new_builds:
            log(
                f"  build {b.get('build_id')}: status={b.get('status')} "
                f"trigger={b.get('trigger')} error={b.get('error')!r}"
            )
            steps = b.get("steps") or []
            for step in steps[-5:]:
                log(f"    step {step.get('kind')}: {step.get('status')} {step.get('error')!r}")
    else:
        log("  no new artifact build job files on disk")

    slot = standalone_slot()
    log(
        f"after GET job: mux={slot.get('mux_preview_hash')!r} "
        f"ambient={slot.get('ambient_mix_hash')!r}"
    )

    if MILESTONE_STITCH.is_file():
        try:
            ms = json.loads(MILESTONE_STITCH.read_text(encoding="utf-8"))
            ms_slot = (
                (ms.get("jobs") or {})
                .get(JOB, {})
                .get("slots", {})
                .get("standalone", {})
            )
            log(
                f"milestone stitch_state.json: mux={ms_slot.get('mux_preview_hash')!r} "
                f"ambient={ms_slot.get('ambient_mix_hash')!r}"
            )
        except (OSError, json.JSONDecodeError) as exc:
            log(f"could not read milestone stitch_state: {exc}")

    for b in latest_builds(2):
        log(f"recent build {b.get('build_id')}: {b.get('status')} {b.get('error')!r}")

    ok = bool((slot.get("mux_preview_hash") or "").strip())
    log("=== RESULT: OK ===" if ok else "=== RESULT: FAIL (no mux_preview_hash) ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
