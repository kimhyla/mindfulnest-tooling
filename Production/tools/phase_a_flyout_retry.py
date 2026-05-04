#!/usr/bin/env python3
"""Phase A fly-out retry — horizontal cross-screen exit.

Kim April 20 2026: first fly-out was glitchy + too vertical ("unnatural for
a bird"). Rerun with a horizontal cross-screen flight path.
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
    RULE8_ANTI_LIPSYNC,
    log,
)

EVENT_DIR = HERE.parent / "Event_1"
CHIPPER_ON_DESK = EVENT_DIR / "phase_a_chipper_on_desk_wide.png"
EMPTY_DESK = EVENT_DIR / "phase_a_empty_desk.png"

# New prompt: horizontal cross-screen flight. Describe the arc so Kling
# interpolates a natural trajectory between the two frames instead of
# lifting straight up.
FLYOUT_PROMPT_V2 = (
    "A small cartoon bird lifts off from the wooden desk in the warm firelit "
    "wizard office and flies gracefully across the room from left to right in "
    "a natural horizontal arc, wings flapping steadily, finally exiting the "
    "frame past the right edge. Soft candlelight, cozy fireplace glow, gentle "
    "camera hold on the room. Beak closed, no dialogue in video."
)

DURATION = 5


def png_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    safe_bytes, info, _ = ensure_min_dimensions(raw)
    log(f"  {path.name}: {info}")
    return "data:image/png;base64," + base64.b64encode(safe_bytes).decode()


def download_mp4(url: str, dst: Path) -> None:
    from urllib.request import urlopen
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


def main() -> int:
    keys = load_api_keys()
    api_key = keys["wavespeed"]
    log("=== FLYOUT V2 (horizontal cross-screen) ===")
    start_uri = png_to_data_uri(CHIPPER_ON_DESK)
    end_uri = png_to_data_uri(EMPTY_DESK)
    log("  submitting to Kling v3.0 Pro (cfg=0.5, sound=false, 5s)...")
    task_id = kling_startend_submit(
        start_b64_uri=start_uri, end_b64_uri=end_uri,
        prompt=FLYOUT_PROMPT_V2, negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=DURATION, api_key=api_key,
    )
    log(f"  task_id: {task_id}")
    result = kling_poll_fresh(task_id, api_key, timeout_s=900)
    status = (result.get("status") or "").lower()
    if status != "completed":
        sys.exit(f"kling failed: status={status} data={result}")
    outputs = result.get("outputs") or []
    if not outputs:
        sys.exit(f"kling completed but no outputs: {result}")
    video_url = outputs[0]
    ts = datetime.now().strftime("%Y%m%dT%H%M%SZ")
    dst = EVENT_DIR / f"phase_a_flyout_v2_{ts}.mp4"
    download_mp4(video_url, dst)
    log("=== DONE ===")
    log(json.dumps({
        "flyout_v2_mp4": str(dst.relative_to(HERE.parent.parent)),
        "size_mb": round(dst.stat().st_size / 1024 / 1024, 2),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
