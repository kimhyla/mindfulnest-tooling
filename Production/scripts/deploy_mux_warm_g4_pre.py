#!/usr/bin/env python3
"""DEPLOY_MUX_WARM_G4_PRE_V1 — pre-bake Event_2 milestone standalone mux before Playwright.

Cold ffmpeg mux inside Playwright beforeAll exceeded 600s (RC14). This script runs
the same bootstrap as stitch_sfx_playback_truth_live.spec.ts ensureMuxPreviewReady,
writes Production/.deploy_mux_warm/Event_2_milestone.ok, and lets live E2E assert only.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

JOB_NAME = "milestone_milestone1_arc1_stitch"
EVENT_STITCH_JOB = "Event_2_stitch"
DEFAULT_PREVIEW_TIMEOUT_S = float(
    __import__("os").environ.get("MN_MUX_WARM_PREVIEW_TIMEOUT_S", "900"),
)
DEFAULT_JOB_POST_TIMEOUT_S = float(
    __import__("os").environ.get("MN_MUX_WARM_JOB_POST_TIMEOUT_S", "600"),
)
DEFAULT_POLL_TIMEOUT_S = float(
    __import__("os").environ.get("MN_MUX_WARM_POLL_TIMEOUT_S", "900"),
)
MILESTONE_ASSEMBLED_DIR = Path(
    "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
    "Claude Mindfulnest Project Files/Production/Milestones/milestone1_arc1/assembled"
)
CANONICAL_CUE = {
    "id": "test_cue_79000",
    "source_path": (
        "/Users/kimberlysmith/Library/CloudStorage/Dropbox/"
        "Claude Mindfulnest Project Files/Production/assets/sound_library/sfx/magic_sound.mp3"
    ),
    "name": "magic_sound.mp3",
    "offset_ms": 79000,
    "duration_ms": 3000,
    "volume": 1,
    "fadein_ms": 50,
    "fadeout_ms": 50,
}


def _request(
    base: str,
    method: str,
    path: str,
    *,
    data: dict | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict | str]:
    url = f"{base.rstrip('/')}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"{method} {path} timed out after {timeout}s") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(f"{method} {path} timed out after {timeout}s") from exc
        raise


def _drain_event_stitch_load_job(base: str) -> None:
    """STITCH_LIVE_E2E_EVENT_WARM_V1 — Event_2 load_job auto-bake blocks milestone POST/GET."""
    print(f"[g4-pre] drain {EVENT_STITCH_JOB} load_job (may bake once, up to 300s) ...")
    status, payload = _request(
        base,
        "GET",
        f"/api/stitch_editor/job/{EVENT_STITCH_JOB}",
        timeout=300.0,
    )
    if status != 200:
        raise RuntimeError(f"{EVENT_STITCH_JOB} load_job drain failed HTTP {status}: {payload!r}")
    print(f"[g4-pre] {EVENT_STITCH_JOB} load_job drain ok")


def _standalone_slot(base: str) -> dict | None:
    status, payload = _request(base, "GET", f"/api/stitch_editor/job/{JOB_NAME}", timeout=300.0)
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"load_job failed HTTP {status}: {payload!r}")
    job = payload.get("job") or {}
    slots = job.get("slots") or {}
    standalone = slots.get("standalone")
    return standalone if isinstance(standalone, dict) else None


def _post_standalone(base: str, slot: dict) -> dict:
    status, cur = _request(base, "GET", "/api/event/current", timeout=30.0)
    if status != 200 or not isinstance(cur, dict):
        raise RuntimeError(f"event/current failed HTTP {status}")
    scope_version = cur.get("event_generation") or 1
    status, body = _request(
        base,
        "POST",
        "/api/stitch_editor/job",
        data={
            "name": JOB_NAME,
            "merge_slots": True,
            "slots": {"standalone": slot},
            "transitions": [],
            "scope_event_id": "Event_2",
            "scope_milestone_id": "milestone1_arc1",
            "scope_video_role": "standalone",
            "scope_target_video": "standalone",
            "event_id": "Event_2",
            "scope_version": scope_version,
        },
        timeout=DEFAULT_JOB_POST_TIMEOUT_S,
    )
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"stitch_save failed HTTP {status}: {body!r}")
    if not body.get("job_persisted"):
        raise RuntimeError(f"job_persisted false: {body!r}")
    saved = (body.get("saved_slots") or {}).get("standalone") or {}
    video_path = str(body.get("saved_video_path") or saved.get("video_path") or "").strip()
    if video_path:
        saved = {**saved, "video_path": video_path}
    if not str(saved.get("video_path") or "").strip():
        raise RuntimeError(f"stitch_save returned no standalone video_path: {body!r}")
    return saved


def _bootstrap_video(base: str) -> dict:
    if not MILESTONE_ASSEMBLED_DIR.is_dir():
        raise RuntimeError(f"milestone assembled dir missing: {MILESTONE_ASSEMBLED_DIR}")
    candidates = sorted(
        [p.name for p in MILESTONE_ASSEMBLED_DIR.glob("standalone_*.mp4")],
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("no standalone_*.mp4 in milestone assembled dir")
    video_path = f"Production/Milestones/milestone1_arc1/assembled/{candidates[0]}"
    return _post_standalone(
        base,
        {
            "video_path": video_path,
            "ambient_bed": "Intro video ambient bed",
            "ambient_volume": 0.15,
            "sfx_cues": [],
        },
    )


def _ensure_video(base: str) -> dict:
    slot = _standalone_slot(base)
    if slot and str(slot.get("video_path") or "").strip():
        return slot
    return _bootstrap_video(base)


def _restore_canonical_cue(base: str) -> None:
    slot = _ensure_video(base)
    cues = slot.get("sfx_cues") or []
    if not isinstance(cues, list):
        cues = []
    if any(str(c.get("id")) == CANONICAL_CUE["id"] for c in cues if isinstance(c, dict)):
        return
    video_path = str(slot.get("video_path") or "").strip()
    patch = {
        **slot,
        "sfx_cues": [*cues, CANONICAL_CUE],
    }
    if video_path:
        patch["video_path"] = video_path
    _post_standalone(base, patch)


def _poll_mux_hash(base: str, *, exclude: str = "", timeout_s: float = 600.0) -> str:
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        slot = _standalone_slot(base)
        h = str((slot or {}).get("mux_preview_hash") or "").strip()
        last = h
        if len(h) >= 8 and (not exclude or h != exclude):
            return h
        time.sleep(2.0)
    raise RuntimeError(f"mux_preview_hash not ready after {timeout_s}s (last={last!r})")


def warm_mux(base: str, marker_path: Path, *, force: bool = False) -> str:
    print(f"[g4-pre] warming mux on {base} ...")
    status, cur = _request(base, "GET", "/api/event/current", timeout=15.0)
    if status != 200:
        raise RuntimeError(f"server unreachable at {base} (HTTP {status})")
    if isinstance(cur, dict) and cur.get("event_id") not in (None, "Event_2"):
        print(f"[g4-pre] WARN event_id={cur.get('event_id')} (expected Event_2 on :5112)")

    _drain_event_stitch_load_job(base)

    print("[g4-pre] drain milestone load_job ...")
    _standalone_slot(base)

    slot = _ensure_video(base)
    mux_hash = str(slot.get("mux_preview_hash") or "").strip()
    if len(mux_hash) >= 8 and not force:
        print(f"[g4-pre] mux already warm hash={mux_hash[:12]}...")
        _restore_canonical_cue(base)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(f"{mux_hash}\n{int(time.time())}\n", encoding="utf-8")
        return mux_hash

    cues = slot.get("sfx_cues") or []
    if not isinstance(cues, list):
        cues = []
    slot_for_preview = {
        **slot,
        "sfx_cues": cues
        if any(str(c.get("id")) == CANONICAL_CUE["id"] for c in cues if isinstance(c, dict))
        else [*cues, CANONICAL_CUE],
    }

    print(
        f"[g4-pre] POST stitch_editor/preview "
        f"(timeout={DEFAULT_PREVIEW_TIMEOUT_S:.0f}s, may take several minutes) ..."
    )
    status, cur = _request(base, "GET", "/api/event/current", timeout=30.0)
    scope_version = (cur.get("event_generation") if isinstance(cur, dict) else None) or 1
    last_err = ""
    for attempt in range(3):
        status, body = _request(
            base,
            "POST",
            "/api/stitch_editor/preview",
            data={
                "name": JOB_NAME,
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
            timeout=DEFAULT_PREVIEW_TIMEOUT_S,
        )
        if status == 200:
            break
        last_err = repr(body)
        print(f"[g4-pre] preview attempt {attempt + 1} failed HTTP {status}: {last_err}")
        time.sleep(5.0)
    else:
        raise RuntimeError(f"preview bootstrap failed: {last_err}")

    mux_hash = _poll_mux_hash(base, timeout_s=DEFAULT_POLL_TIMEOUT_S)
    _restore_canonical_cue(base)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(f"{mux_hash}\n{int(time.time())}\n", encoding="utf-8")
    print(f"[g4-pre] OK mux_preview_hash={mux_hash[:12]}... marker={marker_path}")
    return mux_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:5112",
        help="Storyboard base URL (Event_2 milestone port)",
    )
    parser.add_argument(
        "--marker",
        type=Path,
        help="Marker file path (default: Production/.deploy_mux_warm/Event_2_milestone.ok)",
    )
    parser.add_argument("--force", action="store_true", help="Re-bake even when hash present")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    marker = args.marker or repo_root / "Production" / ".deploy_mux_warm" / "Event_2_milestone.ok"
    try:
        warm_mux(args.base, marker, force=args.force)
    except Exception as exc:
        print(f"[g4-pre] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
