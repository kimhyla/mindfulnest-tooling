#!/usr/bin/env python3
"""One-shot Kling start/end idle from Gate0 openmouth trimmed still + outer choke.

Requires Kim-approved openmouth trimmed still on disk.
Writes IDLE_FROM_TRIMMED_REL (choke_v5). Does NOT wire Phase A Send.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from arlo_green_path_a_assets import (  # noqa: E402
    IDLE_CHOKE_BODY_PX,
    IDLE_CHOKE_TAIL_PX,
    IDLE_FROM_TRIMMED_REL,
    IDLE_NEGATIVE,
    IDLE_PROMPT,
    IDLE_TAIL_X_FRAC,
    KEY_RGB,
    TRIMMED_STILL_REL,
    choke_kling_idle_outline,
    resolve_trimmed_still,
    sha256_file,
)
from kling_startend_pipeline import (  # noqa: E402
    ensure_min_dimensions,
    kling_poll_fresh,
    kling_startend_submit,
    load_api_keys,
)


def _assert_arlo_element(production_root: Path) -> dict:
    from phase_a_arlo_lipsync_base import assert_arlo_element

    return assert_arlo_element(production_root)


def _download(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as resp:
        dest.write_bytes(resp.read())


def _choke_video(src: Path, dest: Path, key_rgb: tuple[int, int, int]) -> None:
    import numpy as np
    from PIL import Image

    work = dest.parent / "_idle_choke_frames"
    if work.exists():
        for p in work.glob("*"):
            p.unlink()
    else:
        work.mkdir(parents=True)

    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vsync",
            "0",
            str(work / "f_%06d.png"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    frames = sorted(work.glob("f_*.png"))
    if not frames:
        raise RuntimeError(f"no frames extracted from {src}")
    for fp in frames:
        rgb = np.asarray(Image.open(fp).convert("RGB"))
        out = choke_kling_idle_outline(
            rgb,
            body_px=IDLE_CHOKE_BODY_PX,
            tail_px=IDLE_CHOKE_TAIL_PX,
            tail_x_frac=IDLE_TAIL_X_FRAC,
            key_rgb=key_rgb,
        )
        Image.fromarray(out).save(fp)
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "24",
            "-i",
            str(work / "f_%06d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "18",
            str(dest),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_idle_once(*, production_root: Path, work: Path) -> dict:
    root = Path(production_root).expanduser().resolve()
    still = resolve_trimmed_still(root)
    if "openmouth" not in still.name.lower():
        raise RuntimeError(f"refusing non-openmouth still for lipsync idle: {still}")
    work = Path(work).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)

    raw = still.read_bytes()
    png, info_s, _ = ensure_min_dimensions(raw)
    uri = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"

    keys = load_api_keys()
    ws = keys.get("wavespeed") or ""
    if not str(ws).startswith("wsk_"):
        # Prefer explicit wsk_ from MD / env if Doppler key is wrong family.
        from credentials_lib.credentials import load_wavespeed_api_key

        ws = load_wavespeed_api_key()
    if not str(ws).startswith("wsk_"):
        raise RuntimeError("WaveSpeed key must start with wsk_ for Kling")

    arlo = _assert_arlo_element(root)
    element = {
        "element_id": str(arlo["element_id"]),
        "element_name": arlo.get("element_name", "Arlo"),
    }

    task_id = kling_startend_submit(
        start_b64_uri=uri,
        end_b64_uri=uri,
        prompt=IDLE_PROMPT,
        negative_prompt=IDLE_NEGATIVE,
        duration=10,
        api_key=ws,
        element_entry=element,
    )
    job = {
        "task_id": task_id,
        "still": str(still),
        "still_sha256": sha256_file(still),
        "prompt": "IDLE_PROMPT mouth_relaxed",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "key_rgb": list(KEY_RGB),
    }
    (work / "idle_job.json").write_text(json.dumps(job, indent=2) + "\n")

    result = kling_poll_fresh(task_id, api_key=ws, timeout_s=900)
    (work / "idle_poll.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    status = (result.get("status") or "").lower() if isinstance(result, dict) else ""
    if status != "completed":
        raise RuntimeError(f"Kling idle not completed: status={status} result={result!r}"[:600])
    url = (result.get("outputs") or [None])[0]
    if not url:
        raise RuntimeError(f"no video url in poll result: {result!r}"[:500])

    raw_mp4 = work / "idle_raw_kling_10s.mp4"
    _download(str(url), raw_mp4)

    out_rel = root / IDLE_FROM_TRIMMED_REL
    out_rel.parent.mkdir(parents=True, exist_ok=True)
    _choke_video(raw_mp4, out_rel, KEY_RGB)

    # Proof frame at ~1s
    proof = root / "Event_6/_proof_arlo_green_path_a"
    proof.mkdir(parents=True, exist_ok=True)
    frame = proof / "gate1_openmouth_idle_choke_v5_frame_1s.png"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "1",
            "-i",
            str(out_rel),
            "-frames:v",
            "1",
            str(frame),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    meta = {
        "status": "ready",
        "idle": str(out_rel),
        "idle_sha256": sha256_file(out_rel),
        "raw_kling": str(raw_mp4),
        "still": str(still),
        "still_rel": TRIMMED_STILL_REL,
        "task_id": task_id,
        "choke": {
            "body_px": IDLE_CHOKE_BODY_PX,
            "tail_px": IDLE_CHOKE_TAIL_PX,
            "tail_x_frac": IDLE_TAIL_X_FRAC,
        },
        "key_rgb": list(KEY_RGB),
        "proof_frame": str(frame),
        "still_prep": info_s,
    }
    (proof / "gate1_openmouth_idle_meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    man_path = root / "NEW STYLE CHARACTERS/ARLO/arlo_layered_assets_v1.json"
    if man_path.is_file():
        man = json.loads(man_path.read_text())
        man.setdefault("assets", {})
        man["assets"]["idle_from_openmouth_trimmed"] = {
            "path": IDLE_FROM_TRIMMED_REL,
            "role": "gesture_idle_openmouth_choke_v5",
            "sha256": meta["idle_sha256"],
            "source_still": TRIMMED_STILL_REL,
        }
        man["gate0_openmouth"] = {
            **(man.get("gate0_openmouth") or {}),
            "status": "kim_approved_2026-08-05",
            "next": "idle_choke_v5_ready_for_offline_lipsync",
        }
        man_path.write_text(json.dumps(man, indent=2) + "\n")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--production-root", required=True)
    ap.add_argument(
        "--work",
        default="/tmp/arlo_idle_from_openmouth",
        help="Scratch dir for raw Kling + job json",
    )
    args = ap.parse_args()
    meta = run_idle_once(
        production_root=Path(args.production_root),
        work=Path(args.work),
    )
    print(json.dumps(meta, indent=2))
    print("IDLE READY — look at:", meta["proof_frame"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
