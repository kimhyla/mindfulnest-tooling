"""Create 'Generate B+C' Flow in local Directus.

Triggered manually on a prod_storyboard_beats row. Posts to the local
adapter which submits to real Kling (or dry-run per PROTOTYPE_DRY_RUN env).
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _clients import local  # type: ignore
from credentials_lib.directus import DirectusError  # type: ignore


ADAPTER_URL = "http://127.0.0.1:8090/animate"
FLOW_NAME = "Generate B+C (Kling)"


def main():
    c = local()

    # Check if Flow already exists (idempotent)
    r = c._request("GET", "/flows", params={
        f"filter[name][_eq]": FLOW_NAME,
        "fields": "id,name,trigger,status,operation",
        "limit": 1,
    })
    existing = r.get("data", [])
    if existing:
        flow_id = existing[0]["id"]
        print(f"  Flow '{FLOW_NAME}' already exists id={flow_id}")
        return flow_id

    # Create Flow (manual trigger scoped to prod_storyboard_beats)
    flow_resp = c._request("POST", "/flows", data={
        "name": FLOW_NAME,
        "icon": "movie_filter",
        "color": "#6644FF",
        "description": "Submits the current beat's image to WaveSpeed Kling. Prototype: dry-run by default.",
        "status": "active",
        "trigger": "manual",
        "accountability": "all",
        "options": {
            "requireConfirmation": True,
            "confirmationDescription": "Submit to Kling? (dry-run unless env PROTOTYPE_DRY_RUN=0)",
            "collections": ["prod_storyboard_beats"],
            "requireSelection": True,
            "fields": [],
        },
    }).get("data", {})
    flow_id = flow_resp["id"]
    print(f"  created Flow '{FLOW_NAME}' id={flow_id}")

    # Create operation: webhook POST to adapter
    # Directus passes the selected row id(s) in $trigger.body.keys
    op_resp = c._request("POST", "/operations", data={
        "name": "POST /animate",
        "key": "post_animate",
        "type": "request",
        "position_x": 19,
        "position_y": 1,
        "options": {
            "method": "POST",
            "url": ADAPTER_URL,
            "headers": [{"header": "Content-Type", "value": "application/json"}],
            "body": '{"beat_id":"{{$trigger.body.keys[0]}}","prompt":"Silent subtle idle movement only. no dialogue in video.","duration":5}',
        },
        "flow": flow_id,
    }).get("data", {})
    print(f"  created operation POST /animate id={op_resp['id']}")

    # Link Flow.operation -> first op
    c._request("PATCH", f"/flows/{flow_id}", data={"operation": op_resp["id"]})
    print(f"  linked flow.operation -> {op_resp['id']}")

    return flow_id


if __name__ == "__main__":
    main()
