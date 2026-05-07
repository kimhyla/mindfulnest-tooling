#!/usr/bin/env python3
"""Phase A M1 Chipper fly-in + fly-out.

Runs TWO Kling v3.0 Pro start-end submissions:
  1. fly_in:  phase_a_empty_desk.png → phase_a_chipper_on_desk_wide.png
  2. fly_out: phase_a_chipper_on_desk_wide.png → phase_a_empty_desk.png

Per Rule 8 (safeguards on) and Kim's clarification that reversed fly-in looks
weird (wings + motion direction wrong), we spend the extra $0.45 for a
purpose-generated fly-out instead of reversing the fly-in.

Outputs:
  Production/Event_1/phase_a_flyin_<ts>.mp4
  Production/Event_1/phase_a_flyout_<ts>.mp4

Duration per clip: 5 s.
"""
from __future__ import annotations

import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kling_startend_pipeline import (  # type: ignore
    load_api_keys,
    kling_startend_submit,
    kling_poll_fresh,
    ensure_min_dimensions,
    robust_https_request,
    RULE8_ANTI_LIPSYNC,
    log,
)

EVENT_DIR = HERE.parent / "Event_1"
EMPTY_DESK = EVENT_DIR / "phase_a_empty_desk.png"
CHIPPER_ON_DESK = EVENT_DIR / "phase_a_chipper_on_desk_wide.png"

FLYIN_PROMPT = (
    "A small cartoon bird flies in from the upper right edge of the frame, "
    "wings flapping naturally. The bird descends gently and lands softly on "
    "the wooden desk in the warm firelit wizard office. Soft candlelight, "
    "cozy fireplace glow. Beak closed, no dialogue in video."
)

FLYOUT_PROMPT = (
    "A small cartoon bird gently lifts off from the wooden desk in the warm "
    "firelit wizard office, wings spreading and flapping naturally. The bird "
    "flies up and out of the frame to the upper right. Soft candlelight, cozy "
    "fireplace glow. Beak closed, no dialogue in video."
)

DURATION = 5  # seconds per clip


def png_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    safe_bytes, info, (w, h) = ensure_min_dimensions(raw)
    log(f"  {path.name}: {info}")
    return "data:image/png;base64," + base64.b64encode(safe_bytes).decode()


def download_mp4(url: str, dst: Path) -> None:
    import urllib.parse as up
    from urllib.request import urlopen
    parsed = up.urlparse(url)
    # Use robust connection: one-shot GET to CDN
    for attempt in range(3):
        try:
            with urlopen(url, timeout=120) as r:
                dst.write_bytes(r.read())
            log(f"  downloaded {dst.name} ({dst.stat().st_size/1024/1024:.1f} MB)")
            return
        except Exception as e:
            log(f"  dl attempt {attempt+1} failed: {e}")
            time.sleep(3 * (2 ** attempt))
    sys.exit(f"download failed: {url}")


def run_one(tag: str, start_path: Path, end_path: Path, prompt: str,
            api_key: str) -> Path:
    log(f"=== {tag.upper()} ===")
    log(f"  start: {start_path.name}")
    log(f"  end:   {end_path.name}")
    start_uri = png_to_data_uri(start_path)
    end_uri = png_to_data_uri(end_path)
    log(f"  submitting to Kling v3.0 Pro (cfg=0.5, sound=false, {DURATION}s)...")
    task_id = kling_startend_submit(
        start_b64_uri=start_uri,
        end_b64_uri=end_uri,
        prompt=prompt,
        negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=DURATION,
        api_key=api_key,
    )
    log(f"  task_id: {task_id}")
    result = kling_poll_fresh(task_id, api_key, timeout_s=900)
    status = (result.get("status") or "").lower()
    if status != "completed":
        sys.exit(f"{tag} kling failed: status={status} data={result}")
    outputs = result.get("outputs") or []
    if not outputs:
        sys.exit(f"{tag} kling completed but no outputs: {result}")
    video_url = outputs[0]
    log(f"  video_url: {video_url[:80]}...")
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    dst = EVENT_DIR / f"phase_a_{tag}_{ts}.mp4"
    download_mp4(video_url, dst)
    return dst


def main() -> int:
    if not EMPTY_DESK.is_file():
        sys.exit(f"missing: {EMPTY_DESK}")
    if not CHIPPER_ON_DESK.is_file():
        sys.exit(f"missing: {CHIPPER_ON_DESK}")
    keys = load_api_keys()
    api_key = keys["wavespeed"]

    flyin_mp4 = run_one(
        "flyin", EMPTY_DESK, CHIPPER_ON_DESK, FLYIN_PROMPT, api_key,
    )
    flyout_mp4 = run_one(
        "flyout", CHIPPER_ON_DESK, EMPTY_DESK, FLYOUT_PROMPT, api_key,
    )

    summary = {
        "flyin_mp4": str(flyin_mp4.relative_to(HERE.parent.parent)),
        "flyout_mp4": str(flyout_mp4.relative_to(HERE.parent.parent)),
        "flyin_size_mb": round(flyin_mp4.stat().st_size / 1024 / 1024, 2),
        "flyout_size_mb": round(flyout_mp4.stat().st_size / 1024 / 1024, 2),
    }
    log("=== DONE ===")
    log(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
