#!/usr/bin/env python3
"""Lean 800k second-pass delivery encode + canonical pin + Directus for module final."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PROD = TOOLS.parent
if str(PROD) not in sys.path:
    sys.path.insert(0, str(PROD))
if str(TOOLS) not in sys.path:
    sys.path.insert(1, str(TOOLS))

from production_server import _resolve_module_id_for_state  # noqa: E402
from stitch_bake_finalize import (  # noqa: E402
    default_stitch_state_path,
    finalize_stitch_bake,
    resolve_m_and_event_numbers,
)
from video_delivery import (  # noqa: E402
    MODULE_FINAL_LEAN_DELIVERY_V1,
    MODULE_FINAL_LEAN_MAX_BITRATE_BPS,
    _probe_bitrate,
    encode_module_final_lean,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="800k lean delivery re-encode + Directus")
    parser.add_argument("--event-dir", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Master or canonical MP4 to re-encode",
    )
    parser.add_argument("--job-name", default="")
    args = parser.parse_args()

    event_dir = args.event_dir.resolve()
    source = args.source.resolve()
    if not source.is_file() and (event_dir / source).is_file():
        source = (event_dir / source).resolve()
    if not source.is_file():
        raise SystemExit(f"source not found: {source}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    job_name = args.job_name or f"{event_dir.name}_stitch"
    exports_dir = event_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    delivery_path = exports_dir / f"stitch_{job_name}_{ts}_delivery.mp4"

    print(f"[lean] encoding {source.name} → {delivery_path.name}", flush=True)
    encode_module_final_lean(source, delivery_path)
    lean_bitrate = _probe_bitrate(delivery_path)
    if lean_bitrate > MODULE_FINAL_LEAN_MAX_BITRATE_BPS:
        raise SystemExit(
            f"lean bitrate {lean_bitrate:,} exceeds cap {MODULE_FINAL_LEAN_MAX_BITRATE_BPS:,}"
        )

    m_number, event_num = resolve_m_and_event_numbers(event_dir)
    from production_server import StateManager, _resolve_module_id_for_state  # noqa: PLC0415

    module_id = _resolve_module_id_for_state(StateManager(event_dir, event_dir.name))
    result = finalize_stitch_bake(
        event_dir,
        delivery_path,
        module_id=module_id,
        m_number=m_number,
        event_num=event_num,
        stitch_state_path=default_stitch_state_path(event_dir),
        job_name=job_name,
        iteration_notes=(
            f"{MODULE_FINAL_LEAN_DELIVERY_V1} CLI re-encode from {source.name}"
        ),
        notes=(
            f"Lean 800k delivery re-encode {ts} from {source.name} "
            f"({lean_bitrate:,} bps)"
        ),
        approve_feedback=f"Lean 800k module final ({MODULE_FINAL_LEAN_DELIVERY_V1}).",
    )
    result["delivery_profile"] = MODULE_FINAL_LEAN_DELIVERY_V1
    result["lean_bitrate_bps"] = lean_bitrate
    result["delivery_path"] = str(delivery_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
