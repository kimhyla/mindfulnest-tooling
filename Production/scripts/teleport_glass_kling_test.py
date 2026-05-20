#!/usr/bin/env python3
"""Manual Kling start-end test: Chipper's mirror → teleport-glass light engulfing.

==============================================================================
SUPERSEDED 2026-05-16 by Production/tools/teleport_glass_inserter.py
   (per LD-pending TELEPORT_GLASS_INSERTER_TOOL_V1 — promotes this hardcoded
   beat_19 script into a reusable --beat / --event / --video CLI tool.)

This script is retained for backward-compat and historical reference. Prefer
the inserter tool for all new teleport-glass insertions.
==============================================================================


Kim's request 2026-05-16: she needs a recurring "teleport glass" transition that
emits from Chipper's mirror and engulfs the screen with magical light, used as
the cut into Phase A videos. This script does ONE Kling submission with two
hand-picked frames to see if it works.

Inputs (hardcoded):
  START: Production/Guide_Bird/poses/chipper mirror arc1.png
  END:   Production/Guide_Bird/poses/chipper in woods with mirror face forward final.png

No lipsync, no beat state, no audio. Output is a raw Kling MP4 placed at:
  Production/Event_1/preserved_winners/teleport_glass_test_<TS>.mp4

Rule 8 compliant: beak closed, no speech, no dialogue in video.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_THIS = Path(__file__).resolve()
_TOOLS = _THIS.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

# Reuse helpers from the validated start-end pipeline.
# IMPORTANT: do NOT import load_api_keys — it triggers an importlib.exec_module
# on production_server.py, which blocks on network calls at import time and
# hangs in SYN_SENT to altice proxy. We parse the wavespeed key directly below.
from kling_startend_pipeline import (  # type: ignore
    CFG_SCALE_BASELINE,
    PRESERVED,
    RULE8_ANTI_LIPSYNC,
    kling_poll_fresh,
    kling_startend_submit,
    log,
)

import re as _re


def load_wavespeed_key_direct() -> str:
    """Parse the wavespeed key from API_KEYS_MASTER.md without importing the
    production_server. Avoids the import-time network-hang trap."""
    keys_file = PROJ / "Production/API_KEYS_MASTER.md"
    content = keys_file.read_text(encoding="utf-8")
    m = _re.search(
        r"\|\s*\*+WaveSpeed[^|]*\*+[^|]*\|\s*`([0-9a-fA-F]{32,})`",
        content,
    )
    if not m:
        sys.exit("FATAL: could not parse wavespeed key from API_KEYS_MASTER.md")
    return m.group(1).strip()

PROJ = _THIS.parent.parent.parent  # Claude Mindfulnest Project Files
START_IMG = PROJ / "Production/Guide_Bird/poses/chipper in woods with mirror face forward final.png"
END_IMG = PROJ / "Production/Event_1/_temp_images/_tmp_white_end_frame.png"

# V2: amped magic prompt + white end frame for guaranteed whiteout transition.
# End image is a near-pure white frame with subtle warm glow at center — Kling
# HARD-locks to the end_image pixels so the clip is structurally guaranteed to
# fade to white by the final frame. Combined with this amped prompt, the
# transition should read as a full magic-engulfs-screen explosion.
POSITIVE_PROMPT = (
    "Cinematic teleport magic transition: blue bird holds a glowing mirror. "
    "Brilliant golden-white magical light EXPLODES outward from the mirror's "
    "surface in radiating waves of pure energy, growing blindingly bright. "
    "The light expands rapidly outward, engulfing the entire frame, dissolving "
    "every forest detail into pure radiant whiteout. By the end the screen is "
    "completely filled with pure white light, all environment elements have "
    "dissolved into the brilliant glow, total magical whiteout transformation. "
    "Cinematic 4:3 composition. Beak at rest, no dialogue in video. "
    "Silent magical light explosion, natural interpolation between the two provided frames."
)

DURATION_S = 5  # 5s plenty for a transition; 10s would be too long


def main() -> int:
    TS = datetime.now().strftime("%Y%m%d-%H%M%S")

    log("=" * 70)
    log(f"Teleport-glass Kling test — TS {TS}")
    log("=" * 70)

    if not START_IMG.is_file():
        sys.exit(f"FATAL: start image not found: {START_IMG}")
    if not END_IMG.is_file():
        sys.exit(f"FATAL: end image not found: {END_IMG}")

    log(f"  START: {START_IMG.relative_to(PROJ)}")
    log(f"  END:   {END_IMG.relative_to(PROJ)}")
    log(f"  duration: {DURATION_S}s")
    log(f"  cfg_scale: {CFG_SCALE_BASELINE}")

    wavespeed_key = load_wavespeed_key_direct()
    log(f"  wavespeed key loaded (length={len(wavespeed_key)})")

    start_bytes = START_IMG.read_bytes()
    end_bytes = END_IMG.read_bytes()
    log(f"  start bytes: {len(start_bytes):,}  end bytes: {len(end_bytes):,}")

    start_uri = f"data:image/png;base64,{base64.b64encode(start_bytes).decode('ascii')}"
    end_uri = f"data:image/png;base64,{base64.b64encode(end_bytes).decode('ascii')}"

    log("\n[1/3] Submit to Kling v3.0 Pro (start + end_image)")
    task_id = kling_startend_submit(
        start_uri, end_uri,
        prompt=POSITIVE_PROMPT,
        negative_prompt=RULE8_ANTI_LIPSYNC,
        duration=DURATION_S,
        api_key=wavespeed_key,
    )
    log(f"  task_id: {task_id}")

    log("\n[2/3] Poll for completion (timeout 15 min)")
    t0 = time.monotonic()
    result = kling_poll_fresh(task_id, wavespeed_key)
    log(f"  done in {time.monotonic() - t0:.1f}s")

    if result.get("status") != "completed":
        log(f"  FATAL: Kling status={result.get('status')} full={result!r}")
        return 1

    clip_url = (result.get("outputs") or [None])[0]
    if not clip_url:
        log(f"  FATAL: completed but no output URL: {result!r}")
        return 1
    log(f"  CDN URL: {clip_url[:90]}...")

    PRESERVED.mkdir(exist_ok=True)
    out_path = PRESERVED / f"teleport_glass_test_{TS}.mp4"
    log(f"\n[3/3] Downloading → {out_path.name}")
    subprocess.run(["curl", "-sSL", "-o", str(out_path), clip_url],
                   check=True, capture_output=True, timeout=180)
    log(f"  saved {out_path.stat().st_size:,} bytes")
    log(f"  full path: {out_path}")
    log(f"  open with: open -a 'QuickTime Player' '{out_path}'")
    # Auto-open for Kim
    subprocess.run(["open", "-a", "QuickTime Player", str(out_path)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
