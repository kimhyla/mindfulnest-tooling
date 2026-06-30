#!/usr/bin/env python3
"""Phase A Avatar Pro — single full voice-stem job (production route).

Category default for Phase A tab: one WaveSpeed Avatar Pro call on the trimmed
voice stem + canonical Arlo wizard-desk still. No ByteDance base-clip loop.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from kling_startend_pipeline import kling_poll_fresh, load_api_keys, log  # noqa: E402
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_avatar_lipsync import (  # noqa: E402
    ARLO_WIZARD_DESK_PROMPT,
    PHASE_A_AVATAR_NEGATIVE_PROMPT,
    PHASE_A_AVATAR_ROUTE_CODE,
    PHASE_A_LIPSYNC_METHOD_AVATAR,
    PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
    estimate_avatar_pro_usd,
    resolve_phase_a_arlo_avatar_still,
)
from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402
from phase_module_lipsync_delivery import finalize_phase_module_lipsync_delivery  # noqa: E402
from server_handlers.phases import _apply_phase_audio_trim  # noqa: E402


class _HandlerShim:
    class _App:
        def __init__(self, event_dir: Path):
            self.event_dir = event_dir

    def __init__(self, event_dir: Path, state: dict):
        self.app = self._App(event_dir)
        self._state = state

    def read_state(self):
        return dict(self._state)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--event-dir", type=Path, required=True)
    p.add_argument("--pin-preview", action="store_true")
    p.add_argument(
        "--resume-task-id",
        default="",
        help="Poll an existing Avatar Pro task id (skip submit; no double billing).",
    )
    p.add_argument("--prompt", default=ARLO_WIZARD_DESK_PROMPT)
    args = p.parse_args()

    event_dir = args.event_dir.expanduser().resolve()
    state_path = event_dir / "production_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    audio_name = state.get("phase_a_voice_stem_file")
    if not audio_name:
        raise SystemExit("phase_a_voice_stem_file unset")
    audio_path = event_dir / audio_name
    if not audio_path.is_file():
        raise SystemExit(f"audio missing: {audio_path}")

    still = resolve_phase_a_arlo_avatar_still(event_dir, event_dir.parent)
    ts = _ts()
    shim = _HandlerShim(event_dir, state)
    audio_for_lipsync, audio_duration = _apply_phase_audio_trim(
        shim, audio_path, "a", state, ts,
    )
    est = estimate_avatar_pro_usd(audio_duration)
    log(f"Phase A Avatar Pro stem={audio_duration:.1f}s est=${est:.2f} still={still.name}")

    api_key = load_api_keys()["wavespeed"]
    client = LipSyncClient(api_key)
    out_name = f"phase_a_lipsync_{ts}.mp4"
    out_path = event_dir / out_name

    if args.resume_task_id:
        task_id = args.resume_task_id.strip()
        log(f"resume poll task_id={task_id}")
    else:
        task_id = client.submit_avatar_pro(
            still, audio_for_lipsync, args.prompt,
            negative_prompt=PHASE_A_AVATAR_NEGATIVE_PROMPT,
        )
        log(f"submitted task_id={task_id}")

    result = kling_poll_fresh(client, task_id)
    if result.get("status") != "completed":
        raise SystemExit(f"Avatar Pro failed: {result}")

    raw_path = event_dir / f"_tmp_phase_a_avatar_raw_{ts}.mp4"
    client.download(result["outputs"][0], raw_path)
    delivery = finalize_phase_module_lipsync_delivery(raw_path, dest_path=out_path)
    log(f"delivery {delivery.get('width')}x{delivery.get('height')} → {out_path.name}")

    if args.pin_preview:
        state["phase_a_lipsync_file"] = out_name
        state["phase_a_lipsync_status"] = "done"
        state["phase_a_lipsync_method"] = PHASE_A_LIPSYNC_METHOD_AVATAR
        state["phase_a_lipsync_route"] = PHASE_A_LIPSYNC_ROUTE_SINGLE_FULL_STEM
        state["phase_a_avatar_route_code"] = PHASE_A_AVATAR_ROUTE_CODE
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        log(f"pinned {out_name} in production_state.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
