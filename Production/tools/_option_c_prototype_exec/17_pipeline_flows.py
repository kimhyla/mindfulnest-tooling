"""Create 4 manual-trigger Flows on prod_storyboard_beats for the E2E pipeline.

Each Flow has a single request operation that POSTs {"beat_id": "<uuid>"}
to the corresponding adapter endpoint. Directus's $trigger.body.keys[0]
template resolves to the currently-selected beat id.

Idempotent: existing Flows with the same name are reused.
"""
from __future__ import annotations
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore


FLOWS = [
    {
        "name": "1. Render TTS (Jessica eleven_v3)",
        "icon": "record_voice_over",
        "color": "#4081E4",
        "description": "Render beat.dialogue_text via ElevenLabs Jessica eleven_v3 (stability 0.5 / style 0.3). Writes to beat.tts_audio.",
        "endpoint": "/tts",
        "template_body": '{"beat_id":"{{$trigger.body.keys[0]}}"}',
        "confirm": "Render TTS for selected beat? (real ElevenLabs spend ~$0.05)",
    },
    {
        "name": "2. Generate Animation (Kling §8.3 start-end)",
        "icon": "animation",
        "color": "#6644FF",
        "description": "§8.3 pipeline: FLUX Kontext end-frame + Kling v3.0 Pro start-end (cfg 0.5). Requires beat.image_override. Writes new prod_video_candidates row + selected_option.",
        "endpoint": "/kling-startend",
        "template_body": '{"beat_id":"{{$trigger.body.keys[0]}}","duration":5}',
        "confirm": "Generate §8.3 start-end animation? (real BFL + Kling spend ~$0.53, ~5 min)",
    },
    {
        "name": "3. Silence Compress (§8.4)",
        "icon": "compress",
        "color": "#CE9518",
        "description": "§8.4: ffmpeg silencedetect (-32dB/150ms) + compress silences >1.0s to 0.8s. Reads beat.tts_audio, writes beat.tts_audio_compressed.",
        "endpoint": "/silcomp",
        "template_body": '{"beat_id":"{{$trigger.body.keys[0]}}","threshold_s":1.0,"target_s":0.8}',
        "confirm": "Run §8.4 silence compression? (free, a few seconds)",
    },
    {
        "name": "4. Lipsync (ByteDance LatentSync)",
        "icon": "voice_chat",
        "color": "#1F8B4C",
        "description": "Submit selected_option video + tts_audio_compressed to ByteDance LatentSync. Writes beat.lipsync_output, lipsync_status=done, status=approved.",
        "endpoint": "/lipsync",
        "template_body": '{"beat_id":"{{$trigger.body.keys[0]}}"}',
        "confirm": "Submit to ByteDance LatentSync? (real spend ~$0.15, ~2-5 min)",
    },
]

ADAPTER_BASE = "http://127.0.0.1:8090"


def upsert_flow(c, spec):
    existing = c._request("GET", "/flows", params={
        "filter[name][_eq]": spec["name"], "limit": 1,
    }).get("data", [])
    if existing:
        flow = existing[0]
        flow_id = flow["id"]
        print(f"  Flow '{spec['name']}' exists id={flow_id}")
    else:
        flow = c._request("POST", "/flows", data={
            "name": spec["name"],
            "icon": spec["icon"],
            "color": spec["color"],
            "description": spec["description"],
            "status": "active",
            "trigger": "manual",
            "accountability": "all",
            "options": {
                "requireConfirmation": True,
                "confirmationDescription": spec["confirm"],
                "collections": ["prod_storyboard_beats"],
                "requireSelection": True,
                "fields": [],
            },
        }).get("data", {})
        flow_id = flow["id"]
        print(f"  created Flow '{spec['name']}' id={flow_id}")

    # Desired operation state
    op_payload = {
        "name": spec["endpoint"],
        "key": f"post_{spec['endpoint'].strip('/').replace('-','_')}",
        "type": "request",
        "position_x": 19, "position_y": 1,
        "options": {
            "method": "POST",
            "url": f"{ADAPTER_BASE}{spec['endpoint']}",
            "headers": [{"header": "Content-Type", "value": "application/json"}],
            "body": spec["template_body"],
        },
        "flow": flow_id,
    }

    # Find existing operation attached to this flow
    ops = c._request("GET", "/operations", params={
        "filter[flow][_eq]": flow_id, "limit": 10,
    }).get("data", [])
    if ops:
        op_id = ops[0]["id"]
        c._request("PATCH", f"/operations/{op_id}", data=op_payload)
        print(f"    patched operation id={op_id} -> {spec['endpoint']}")
    else:
        op = c._request("POST", "/operations", data=op_payload).get("data", {})
        op_id = op["id"]
        print(f"    created operation id={op_id} -> {spec['endpoint']}")

    if flow.get("operation") != op_id:
        c._request("PATCH", f"/flows/{flow_id}", data={"operation": op_id})
        print(f"    linked flow.operation -> {op_id}")

    return flow_id


def main():
    c = local()
    for spec in FLOWS:
        upsert_flow(c, spec)
    # Summary
    all_flows = c._request("GET", "/flows", params={
        "filter[trigger][_eq]": "manual",
        "fields": "id,name,status",
        "sort": "name",
    }).get("data", [])
    print(f"\n  {len(all_flows)} manual-trigger Flows in total:")
    for f in all_flows:
        print(f"    - {f['name']} ({f['status']})")


if __name__ == "__main__":
    main()
