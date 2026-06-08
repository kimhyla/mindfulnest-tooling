#!/usr/bin/env python3
"""Batch Chipper Phase A idle + lipsync candidates for Kim review.

Outputs to Event_*/phase_a_idle_candidates/ with manifest JSON.
Does NOT stitch — pick a winner first.

Usage:
  python3 phase_a_chipper_candidate_batch.py --batch wide_v5
  python3 phase_a_chipper_candidate_batch.py --batch beak_v4
  python3 phase_a_chipper_candidate_batch.py --batch tucked_abc
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # noqa: E402
    RULE8_ANTI_LIPSYNC,
    _load_subject_element,
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
    log,
)

_TOOTH_NEG = (
    "teeth, tooth, fangs, fang, dental, toothy, visible teeth, teeth inside beak, "
    "morphing teeth, human teeth, predator teeth"
)
_ANATOMY_NEG = (
    "human hands, fingers, hand-like paws, wing gesticulation, flapping, extra wings"
)
_CAMERA_NEG = (
    "zoom in, push in, dolly in, ken burns, face fill frame, extreme close-up, camera move"
)
_TOOTH_POS = (
    "TOOTH-FREE bird beak — smooth keratin only, never show teeth or fangs."
)

BATCHES: dict[str, dict] = {
    "tucked_abc": {
        "source_still": "phase_a_chipper_closeup_crop_v3.png",
        "note": "Wing-tucked idle variants A/B/C",
        "candidates": (
            {
                "id": "a_tucked_strict",
                "label": "A — tucked strict",
                "positive": (
                    "Chipper on wizard desk, camera-forward. Wings folded tight at sides, "
                    "completely still. " + _TOOTH_POS + " Soft blinks only."
                ),
                "negative_extra": "wing movement, head turn, body sway",
            },
            {
                "id": "b_tucked_calm",
                "label": "B — tucked calm",
                "positive": (
                    "Calm idle Chipper facing camera on desk. Wings down and still. "
                    + _TOOTH_POS + " Gentle breathing, closed beak."
                ),
                "negative_extra": "gesticulation, pacing, mouth open",
            },
            {
                "id": "c_subtle_wings",
                "label": "C — subtle wings",
                "positive": (
                    "Chipper on desk facing camera. Wings mostly folded; micro feather "
                    "rustle only. " + _TOOTH_POS
                ),
                "negative_extra": "flapping, arm gestures, large wing motion",
            },
        ),
    },
    "beak_v4": {
        "source_still": "phase_a_chipper_beak_crop_v4.png",
        "note": "Tighter beak crop — frozen + zoom (deprecated; teeth/zoom issues)",
        "candidates": (
            {
                "id": "d_frozen_zoom_slow",
                "label": "D — frozen beak + slow zoom",
                "positive": (
                    "Very slow subtle zoom toward Chipper's TOOTH-FREE beak. "
                    "Wings frozen at sides. Background still."
                ),
                "negative_extra": _CAMERA_NEG,
            },
            {
                "id": "e_frozen_zoom_micro",
                "label": "E — frozen beak + micro zoom",
                "positive": (
                    "Micro zoom on Chipper beak, TOOTH-FREE. Wings still. "
                    "Minimal motion."
                ),
                "negative_extra": _CAMERA_NEG + ", large motion",
            },
        ),
    },
    "wide_v5": {
        "source_still": "phase_a_chipper_wide_crop_v5.png",
        "note": "Wide locked TOOTH-FREE — no push-in",
        "candidates": (
            {
                "id": "f_wide_locked",
                "label": "F — wide locked, TOOTH-FREE",
                "positive": (
                    "Medium-wide Chipper on wizard desk. " + _TOOTH_POS + " "
                    "Camera LOCKED — NO zoom, field of view constant. Wings folded still."
                ),
                "negative_extra": _CAMERA_NEG + ", head turn, wing twitch",
            },
            {
                "id": "g_wide_static",
                "label": "G — wide static, TOOTH-FREE strict",
                "positive": (
                    "Stable medium shot matching source image. " + _TOOTH_POS + " "
                    "ZERO camera movement. Character frozen except soft blinks."
                ),
                "negative_extra": _CAMERA_NEG + ", locomotion, mouth open",
            },
        ),
    },
}


def _event_dir() -> Path:
    env = os.environ.get("MN_EVENT_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    dropbox = (
        Path.home()
        / "Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production"
    )
    if (dropbox / "Event_1").is_dir():
        return dropbox / "Event_1"
    return HERE.parent / "Event_1"


def _negative(extra: str) -> str:
    return RULE8_ANTI_LIPSYNC + ", " + _TOOTH_NEG + ", " + _ANATOMY_NEG + ", " + extra


def _encode(path: Path) -> str:
    raw = path.read_bytes()
    png, info, _ = ensure_min_dimensions(raw)
    log(f"  still {path.name}: {info}")
    return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"


def _normalize(staging: Path, dest: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(staging),
        "-vf", "scale=1280:960:force_original_aspect_ratio=decrease,"
               "pad=1280:960:(ow-iw)/2:(oh-ih)/2,setsar=1:1,fps=24",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-c:a", "aac", "-ar", "44100", "-ac", "1", "-movflags", "+faststart",
        str(dest),
    ], check=True, timeout=180)


def _lipsync_via_server(
    event: Path, cand_dir: Path, base_id: str, cid: str, ts: str,
    server: str,
) -> dict:
    body = json.dumps({
        "event_id": event.name,
        "scope_video_role": "intro",
        "phase": "a",
        "base_clip_id": base_id,
    }).encode()
    req = urllib.request.Request(
        f"{server}/api/phase_a/lipsync",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        submit = json.loads(resp.read().decode())
    if not submit.get("ok"):
        raise RuntimeError(f"lipsync submit failed: {submit}")

    state_path = event / "production_state.json"
    before = json.loads(state_path.read_text()).get("phase_a_lipsync_mtime")
    for i in range(60):
        time.sleep(15)
        state = json.loads(state_path.read_text())
        st = state.get("phase_a_lipsync_status")
        lm = state.get("phase_a_lipsync_mtime")
        lf = state.get("phase_a_lipsync_file")
        log(f"    lipsync t+{(i + 1) * 15}s status={st}")
        if st and str(st).startswith("error"):
            raise RuntimeError(st)
        if lm and lm != before and st == "done" and lf:
            out_name = f"chipper_lipsync_{cid}_{ts}.mp4"
            out_path = cand_dir / out_name
            shutil.copy2(event / lf, out_path)
            rel = f"Production/{event.name}/phase_a_idle_candidates/{out_name}"
            return {
                "lipsync_file": out_name,
                "preview_url": f"{server}/files?path="
                + urllib.parse.quote(rel, safe="/"),
            }
    raise RuntimeError("lipsync timeout — poll manually via lipsync_sender.py")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--batch", required=True, choices=sorted(BATCHES))
    p.add_argument("--duration", type=int, default=10, choices=(5, 10))
    p.add_argument("--no-element", action="store_true")
    p.add_argument("--skip-lipsync", action="store_true")
    p.add_argument("--server", default="http://127.0.0.1:5111")
    args = p.parse_args()

    spec = BATCHES[args.batch]
    event = _event_dir()
    cand_dir = event / "phase_a_idle_candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)
    bases = event.parent / "assets" / "lipsync_bases"
    bases.mkdir(parents=True, exist_ok=True)

    still = event / spec["source_still"]
    if not still.is_file():
        still = event.parent / "Event_1" / spec["source_still"]
    if not still.is_file():
        log(f"FATAL: missing still {spec['source_still']}")
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    keys = load_api_keys()
    start_uri = _encode(still)
    element = None if args.no_element else _load_subject_element("Chipper")
    manifest = {
        "batch_ts": ts,
        "batch": args.batch,
        "source_still": still.name,
        "note": spec["note"],
        "candidates": [],
    }

    for c in spec["candidates"]:
        log(f"=== {c['label']} idle ===")
        task_id = kling_startend_submit(
            start_uri, None,
            prompt=c["positive"], negative_prompt=_negative(c["negative_extra"]),
            duration=args.duration, api_key=keys["wavespeed"],
            element_entry=element,
        )
        log(f"  task_id={task_id}")
        result = kling_poll_fresh(task_id, keys["wavespeed"], timeout_s=900)
        if result.get("status") != "completed":
            log(f"FATAL idle: {result}")
            return 1
        url = (result.get("outputs") or [None])[0]
        idle_name = f"chipper_idle_{c['id']}_{ts}.mp4"
        idle_path = cand_dir / idle_name
        staging = cand_dir / f"_tmp_{c['id']}.mp4"
        subprocess.run(["curl", "-sSL", "-o", str(staging), url], check=True, timeout=180)
        _normalize(staging, idle_path)
        staging.unlink(missing_ok=True)

        prefix = args.batch.split("_")[0]
        base_id = f"chipper_{args.batch}_{c['id'].split('_')[0]}"
        shutil.copy2(idle_path, bases / f"{base_id}.mp4")

        entry = {
            "id": c["id"],
            "label": c["label"],
            "idle_file": idle_name,
            "idle_url": (
                f"{args.server}/files?path=Production/{event.name}/"
                f"phase_a_idle_candidates/{idle_name}"
            ),
            "base_clip_id": base_id,
        }
        if not args.skip_lipsync:
            log(f"=== {c['label']} lipsync ===")
            entry.update(_lipsync_via_server(event, cand_dir, base_id, c["id"], ts, args.server))
        manifest["candidates"].append(entry)
        log(f"  ✓ {c['id']}")

    mp = cand_dir / f"{args.batch}_manifest_{ts}.json"
    mp.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
