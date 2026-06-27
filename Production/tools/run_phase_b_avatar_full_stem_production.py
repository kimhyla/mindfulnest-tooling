#!/usr/bin/env python3
"""Phase B Avatar Pro — single full voice-stem job (production route).

Category default for Phase B tab: one WaveSpeed Avatar Pro call on the trimmed
voice stem. No pause-aligned chunk assembly or gap holds.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from kling_startend_pipeline import kling_poll_fresh, load_api_keys, log  # noqa: E402
from lipsync_sender import LipSyncClient  # noqa: E402
from phase_a_chipper_bytedance_lipsync import ffprobe_duration  # noqa: E402
from phase_b_avatar_lipsync import (  # noqa: E402
    PHASE_B_AVATAR_ROUTE_CODE,
    PHASE_B_LIPSYNC_METHOD_AVATAR,
    PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM,
    STATIC_BG_PROMPT,
    estimate_avatar_pro_usd,
    resolve_phase_b_cedric_still,
)
from phase_module_lipsync_delivery import finalize_phase_module_lipsync_delivery  # noqa: E402
from server_handlers.phases import _apply_phase_audio_trim  # noqa: E402


class _HandlerShim:
    """Minimal shim so _apply_phase_audio_trim can run outside HTTP handler."""

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
    p.add_argument("--prompt", default=STATIC_BG_PROMPT)
    args = p.parse_args()

    event_dir = args.event_dir.expanduser().resolve()
    state_path = event_dir / "production_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    audio_name = state.get("phase_b_voice_stem_file")
    if not audio_name:
        raise SystemExit("phase_b_voice_stem_file unset")
    audio_path = event_dir / audio_name
    if not audio_path.is_file():
        raise SystemExit(f"audio missing: {audio_path}")

    still = resolve_phase_b_cedric_still(event_dir.parent)
    ts = _ts()
    shim = _HandlerShim(event_dir, state)
    audio_for_lipsync, audio_duration = _apply_phase_audio_trim(
        shim, audio_path, "b", state, ts,
    )
    est = estimate_avatar_pro_usd(audio_duration)
    log(f"[avatar_full_stem] audio={audio_duration:.3f}s est=${est:.2f}")

    keys = load_api_keys()
    client = LipSyncClient(keys["wavespeed"])
    resume_task_id = (args.resume_task_id or "").strip()
    if resume_task_id:
        task_id = resume_task_id
        log(f"[avatar_full_stem] resume poll task_id={task_id}")
    else:
        task_id = client.submit_avatar_pro(still, audio_for_lipsync, args.prompt)
    result = kling_poll_fresh(task_id, keys["wavespeed"], timeout_s=7200)
    if (result.get("status") or "").lower() != "completed":
        raise SystemExit(f"Avatar full stem failed: {result}")
    url = (result.get("outputs") or [None])[0]
    if not url:
        raise SystemExit(f"Avatar completed with no output: {result}")

    out_name = f"phase_b_lipsync_{ts}.mp4"
    out_path = event_dir / out_name
    client.download(url, out_path)
    delivery = finalize_phase_module_lipsync_delivery(out_path, sharpen=True)
    mtime = int(os.path.getmtime(str(out_path)))

    meta = {
        "code": PHASE_B_AVATAR_ROUTE_CODE,
        "route": PHASE_B_LIPSYNC_METHOD_AVATAR,
        "assembly": "single_full_stem_v1",
        "still": still.name,
        "task_id": task_id,
        "output": out_name,
        "audio_duration_s": round(audio_duration, 3),
        "video_duration_s": round(ffprobe_duration(out_path), 3),
        "estimated_cost_usd": round(est, 2),
        "delivery": delivery,
    }
    if resume_task_id:
        meta["resumed_from_task"] = True
    (event_dir / out_name.replace(".mp4", ".json")).write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.pin_preview:
        backup = event_dir / ".backups" / "state" / f"{ts}_pre_avatar_full_stem_pin.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(state_path, backup)
        state["phase_b_lipsync_file"] = out_name
        state["phase_b_lipsync_mtime"] = mtime
        state["phase_b_lipsync_status"] = "done"
        state["phase_b_lipsync_method"] = PHASE_B_LIPSYNC_METHOD_AVATAR
        state["phase_b_lipsync_requires_regen"] = False
        state["phase_b_lipsync_route"] = PHASE_B_LIPSYNC_ROUTE_SINGLE_FULL_STEM
        state.pop("phase_b_lipsync_segmented_timeline", None)
        state.pop("phase_b_avatar_segmented", None)
        state.pop("phase_b_lipsync_segmented", None)
        nested = state.setdefault("phase_b", {})
        if isinstance(nested, dict):
            for key in (
                "phase_b_voice_stem_file",
                "phase_b_voice_stem_mtime",
                "phase_b_lipsync_file",
                "phase_b_lipsync_mtime",
                "phase_b_lipsync_status",
                "phase_b_lipsync_method",
                "phase_b_lipsync_requires_regen",
                "phase_b_lipsync_route",
            ):
                if key in state:
                    nested[key] = state[key]
            nested["phase_b_lipsync_requires_regen"] = False
            for stale in (
                "phase_b_lipsync_segmented_timeline",
                "phase_b_avatar_segmented",
                "phase_b_lipsync_segmented",
            ):
                nested.pop(stale, None)
        state["_module_version"] = int(state.get("_module_version", 0) or 0) + 1
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        log(f"[avatar_full_stem] pinned preview → {out_name}")

    print(json.dumps(meta), flush=True)
    print(out_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
