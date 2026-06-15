#!/usr/bin/env python3
"""Phase A sitting zoom — delegates to Ken Burns smooth zoom in phase_a_av_post."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase_a_av_post import apply_smooth_zoom  # noqa: E402

DEFAULT_ZOOM_START = 1.0
DEFAULT_ZOOM_END = 1.08
DEFAULT_RAMP_SEC = 14.0
DEFAULT_RAMP_DELAY_SEC = 1.0
DEFAULT_FOCAL_X = 0.5
DEFAULT_FOCAL_Y = 0.47


def log(msg: str) -> None:
    print(f"[phase_a_slow_zoom] {msg}", flush=True)


def apply_slow_zoom(
    src: Path,
    dst: Path | None = None,
    *,
    zoom_start: float = DEFAULT_ZOOM_START,
    zoom_end: float = DEFAULT_ZOOM_END,
    ramp_sec: float = DEFAULT_RAMP_SEC,
    ramp_delay_sec: float = DEFAULT_RAMP_DELAY_SEC,
    focal_x: float = DEFAULT_FOCAL_X,
    focal_y: float = DEFAULT_FOCAL_Y,
    fps: int = 24,
) -> Path:
    """Backward-compatible alias for apply_smooth_zoom."""
    return apply_smooth_zoom(
        src,
        dst,
        zoom_start=zoom_start,
        zoom_end=zoom_end,
        ramp_sec=ramp_sec,
        ramp_delay_sec=ramp_delay_sec,
        focal_x=focal_x,
        focal_y=focal_y,
        fps=fps,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--zoom-start", type=float, default=DEFAULT_ZOOM_START)
    ap.add_argument("--zoom-end", type=float, default=DEFAULT_ZOOM_END)
    ap.add_argument("--ramp-sec", type=float, default=DEFAULT_RAMP_SEC)
    ap.add_argument("--ramp-delay-sec", type=float, default=DEFAULT_RAMP_DELAY_SEC)
    ap.add_argument("--focal-x", type=float, default=DEFAULT_FOCAL_X)
    ap.add_argument("--focal-y", type=float, default=DEFAULT_FOCAL_Y)
    args = ap.parse_args()

    try:
        out = apply_slow_zoom(
            args.input,
            args.output,
            zoom_start=args.zoom_start,
            zoom_end=args.zoom_end,
            ramp_sec=args.ramp_sec,
            ramp_delay_sec=args.ramp_delay_sec,
            focal_x=args.focal_x,
            focal_y=args.focal_y,
        )
        sidecar = out.with_suffix(".json")
        sidecar.write_text(
            json.dumps({
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "pipeline": "phase_a_smooth_zoom",
                "source": args.input.name,
                "output": out.name,
                "zoom_end": args.zoom_end,
                "ramp_sec": args.ramp_sec,
                "ramp_delay_sec": args.ramp_delay_sec,
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"ok": True, "output": out.name}, indent=2))
        return 0
    except Exception as exc:
        log(f"FATAL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
