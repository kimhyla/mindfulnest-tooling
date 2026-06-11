#!/usr/bin/env python3
"""Install approved calm-clone beat_10 into Beat Gen sidecar for Kim smoke."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROD = Path(__file__).resolve().parent.parent
BEAT_ID = "bg_arc1_event1_pre_beat_10"
SRC = PROD / "Event_1/kling_o3_clips/arlo_bound_voice_smoke/20260610T234526Z/bg_arc1_event1_pre_beat_10_arlo_bound_voice.mp4"
CLIPS = PROD / "Event_1/kling_o3_clips"


def _probe(path: Path) -> dict:
    raw = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
        text=True,
    )
    s = json.loads(raw)["streams"][0]
    return {"width": int(s["width"]), "height": int(s["height"])}


def _find_beat(obj, bid):
    if isinstance(obj, dict):
        if obj.get("beat_id") == bid:
            return obj
        for v in obj.values():
            r = _find_beat(v, bid)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_beat(v, bid)
            if r:
                return r
    return None


def main() -> int:
    if not SRC.is_file():
        raise SystemExit(f"Missing source clip: {SRC}")

    sys_path = PROD / "tools"
    import sys
    sys.path.insert(0, str(PROD))
    from video_delivery import encode_delivery_video

    CLIPS.mkdir(parents=True, exist_ok=True)
    master = CLIPS / f"{BEAT_ID}_g6_element_o3_master.mp4"
    delivery = CLIPS / f"{BEAT_ID}_arlo_element_o3_delivery.mp4"
    shutil.copy2(SRC, master)
    encode_delivery_video(master, delivery, include_audio=True, sharpen=False)

    raw = _probe(master)
    deliv = _probe(delivery)
    now = datetime.now(timezone.utc).isoformat()

    sidecar_path = PROD / "beat_generator_state.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    beat = _find_beat(sidecar, BEAT_ID)
    if not beat:
        raise SystemExit(f"Beat not found: {BEAT_ID}")

    beat["kling_o3_generation"] = 6
    beat["kling_o3_video_path"] = str(delivery)
    beat["kling_o3_status"] = "approved"
    beat["status"] = "approved"
    beat["kling_o3_completed_at"] = now
    beat["kling_o3_mode"] = "o3_element_native_voice"
    beat["kling_o3_voice_fix_status"] = "approved"
    beat["kling_o3_voice_fix_phase"] = "finalize"
    beat["kling_o3_voice_fix_completed_at"] = now
    beat["o3_element_quality"] = {
        "speaker": "Arlo",
        "method": "O3 Pro reference-to-video + Element create-voice (installed calm clone)",
        "raw_master_path": str(master),
        "delivery_path": str(delivery),
        "raw_master": raw,
        "delivery": deliv,
        "applied_at": now,
    }
    beat["kling_o3_options"] = [{
        "key": f"{BEAT_ID}_o3_video_installed",
        "label": "calm Element clone (Kim approved)",
        "video_path": str(delivery),
        "source": "kling_o3_element_native_voice",
        "active": True,
        "created_at": now,
    }]
    sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    print(json.dumps({"beat_id": BEAT_ID, "master": str(master), "delivery": str(delivery), "raw": raw, "delivery_size": deliv}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
