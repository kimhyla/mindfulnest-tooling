#!/usr/bin/env python3
"""One-off: wire existing Event_3 June 27 Phase A lipsync into production_state.

No paid lipsync. Prefer June 27 take + matching June 27 stem.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("PRODUCTION_SERVER_SINGLE_MACHINE", "1")

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
sys.path.insert(0, str(TOOLS))

from production_server import StateManager  # noqa: E402

EVENT = Path(
    r"C:\Users\ECDS Clinical\Dropbox\Claude Mindfulnest Project Files"
    r"\Production\Event_3"
)
LIP = "phase_a_lipsync_20260627-180353.mp4"
STEM = "phase_a_voice_stem_20260627-180248.mp3"
METHOD = "base_clip_bytedance_tight_v1"
BASE = "arlo_idle_wizard_desk_v7"
STATUS = "needs_manual_visual_review"

CLEAR_KEYS = [
    "phase_a_lipsync_job_id",
    "phase_a_lipsync_route",
    "phase_a_lipsync_chunk_count",
    "phase_a_lipsync_estimated_cost_usd",
    "phase_a_lipsync_task_id",
    "phase_a_lipsync_started_at",
    "phase_a_lipsync_pending_output",
    "phase_a_lipsync_pending_audio",
    "phase_a_lipsync_reliability_note",
    # Preview prefers fresh stitched over lipsync — must clear layered-era stitch
    # or Phase A UI keeps showing July 22 instead of June 27 lipsync.
    "phase_a_stitched_file",
    "phase_a_stitched_mtime",
]


def main() -> int:
    lip_path = EVENT / LIP
    stem_path = EVENT / STEM
    if not lip_path.is_file():
        raise SystemExit(f"missing lipsync: {lip_path}")
    if not stem_path.is_file():
        raise SystemExit(f"missing stem: {stem_path}")

    backup = EVENT / (
        f"production_state.pre_restore_june27_"
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    shutil.copy2(EVENT / "production_state.json", backup)
    print(f"backup -> {backup.name}")

    sidecar = {
        "pipeline": "phase_a_base_clip_bytedance_tight",
        "base_clip": "arlo_idle_wizard_desk_v7.mp4",
        "base_md5": "c5a17509ccae74180bd3a0a19fab62d1",
        "audio_source": STEM,
        "stem_duration_s": 29.04,
        "preroll_added_s": 0.7,
        "lead_trim_s": 0.7,
        "trailing_trim_s": 0.0,
        "stem_floor_pad_s": 0.0,
        "timeline_gaps_preserved": False,
        "chained_chunks": False,
        "single_pass": True,
        "gap_insert_count": 0,
        "gap_clip_count": 0,
        "chunk_count": 1,
        "chain_manifest": None,
        "output": LIP,
        "method": METHOD,
        "zoom": False,
        "upscale_bookend": False,
        "bookend_resolution": "skipped_for_module_delivery_v2",
        "kling_lipsync": False,
        "note": (
            "Restored existing June 27 take — no new paid lipsync; "
            "sidecar synthesized for UI/state parity"
        ),
        "restored_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar_path = EVENT / "phase_a_lipsync_20260627-180353.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    print(f"wrote sidecar {sidecar_path.name}")

    lip_mtime = int(lip_path.stat().st_mtime)
    stem_mtime = int(stem_path.stat().st_mtime)
    set_fields = {
        "phase_a_lipsync_file": LIP,
        "phase_a_lipsync_mtime": lip_mtime,
        "phase_a_lipsync_status": STATUS,
        "phase_a_lipsync_method": METHOD,
        "phase_a_lipsync_requires_regen": False,
        "phase_a_lipsync_manifest_file": sidecar_path.name,
        "phase_a_lipsync_av_gap_s": 0.0,
        "phase_a_chipper_sitting_clip_id": BASE,
        "phase_a_voice_stem_file": STEM,
        "phase_a_voice_stem_mtime": stem_mtime,
    }

    sm = StateManager(EVENT, "Event_3")

    def _apply(st: dict) -> int:
        nested = st.setdefault("phase_a", {})
        if not isinstance(nested, dict):
            nested = {}
            st["phase_a"] = nested
        for key, val in set_fields.items():
            st[key] = val
            nested[key] = val
        for key in CLEAR_KEYS:
            st.pop(key, None)
            nested.pop(key, None)
        st.setdefault(
            "phase_a_lipsync_delivery_recipe",
            "PHASE_MODULE_LIPSYNC_DELIVERY_V2",
        )
        nested.setdefault(
            "phase_a_lipsync_delivery_recipe",
            "PHASE_MODULE_LIPSYNC_DELIVERY_V2",
        )
        st["_module_version"] = int(st.get("_module_version", 0) or 0) + 1
        nested["_restore_note"] = (
            "wired existing June27 ByteDance lipsync for stitcher (no paid re-run)"
        )
        return st["_module_version"]

    ver = sm.mutate_state(_apply)
    print(f"mutated ok module_version={ver}")

    st = sm.read_state()
    print("VERIFY:")
    for key in (
        "phase_a_lipsync_file",
        "phase_a_lipsync_status",
        "phase_a_lipsync_method",
        "phase_a_chipper_sitting_clip_id",
        "phase_a_voice_stem_file",
        "phase_a_lipsync_manifest_file",
    ):
        print(
            f"  {key}={st.get(key)!r} "
            f"nested={st.get('phase_a', {}).get(key)!r}"
        )
    print(
        "  job_id cleared "
        f"top={'phase_a_lipsync_job_id' not in st} "
        f"nested={'phase_a_lipsync_job_id' not in st.get('phase_a', {})}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
