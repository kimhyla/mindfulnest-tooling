#!/usr/bin/env python3
"""Register stitcher canonical job + overlay export lock-ins in Directus. Idempotent."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))

BASE = "https://directus-production-3460.up.railway.app"
EMAIL = "kimhyla11@gmail.com"
PASSWORD = "directus11$"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

DOCS = [
    {
        "file_path": "Production/docs/LESSONS_LEARNED_20260528_STITCHER_CANONICAL_JOB_V1.md",
        "doc_title": "Lessons Learned — Stitcher Canonical Job (2026-05-28)",
        "doc_category": "lessons_learned",
        "status": "active",
        "is_current": True,
        "doc_version": "1",
        "chain_id": "stitcher_canonical_job_v1",
        "has_locked_decisions": True,
        "notes": "Canonical Event_stitch job, overlay export, legacy migration.",
    },
]

LOCKS = [
    (
        "STITCH_CANONICAL_EVENT_JOB_V1",
        "Stitcher — one canonical {eventId}_stitch job accumulates all slots",
        "scene_assemble, phase export, and stitch_save_job(merge_slots) MUST upsert into "
        "{eventId}_stitch via stitch_upsert_event_slot. Never replace the full slots dict "
        "when updating a single producer output. Legacy auto_* / phase_* jobs migrate on load.",
        "Production/tools/server_handlers/stitch_editor.py,"
        "Production/tools/production_server.py,"
        "Production/tools/storyboard-v2/src/components/StitcherTab.tsx",
    ),
    (
        "PHASE_B_EXPORT_OVERLAY_BAKE_V1",
        "Phase B Export to Stitcher — bake watercolor overlays before slot write",
        "POST /api/phase/export_stitcher MUST render via _phase_ensure_overlay_mp4 (same cache "
        "as preview) and write composited MP4 to phase_b slot with overlay_baked=true. "
        "Raw lipsync_file alone is forbidden for stitch export.",
        "Production/tools/server_handlers/phases.py,"
        "Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx",
    ),
    (
        "STITCH_SAVE_MERGE_SLOTS_V1",
        "Stitcher UI saves — merge_slots preserves unrelated slots",
        "StitcherTab stitch_save_job calls MUST pass merge_slots=true so trim/ambient/SFX "
        "edits on one slot never wipe intro/resolution/phase paths collected from other tabs.",
        "Production/tools/server_handlers/stitch_editor.py,"
        "Production/tools/storyboard-v2/src/components/StitcherTab.tsx",
    ),
]


def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    try:
        auth = _req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
        token = auth["data"]["access_token"]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
        print(f"Directus login failed: {exc}", file=sys.stderr)
        return 1

    for doc in DOCS:
        fp = _REPO / doc["file_path"]
        if not fp.is_file():
            print(f"Missing doc: {fp}", file=sys.stderr)
            return 1
        content = fp.read_text(encoding="utf-8")
        payload = {**doc, "content": content, "updated_at": NOW}
        try:
            existing = _req("GET", f"/items/docs?filter[chain_id][_eq]={doc['chain_id']}", token=token)
            items = (existing.get("data") or [])
            if items:
                _req("PATCH", f"/items/docs/{items[0]['id']}", token=token, body=payload)
                print(f"Updated doc: {doc['chain_id']}")
            else:
                payload["created_at"] = NOW
                _req("POST", "/items/docs", token=token, body=payload)
                print(f"Created doc: {doc['chain_id']}")
        except urllib.error.HTTPError as exc:
            print(f"Doc upsert failed for {doc['chain_id']}: {exc}", file=sys.stderr)
            return 1

    for lock_id, title, body_text, files in LOCKS:
        payload = {
            "lock_id": lock_id,
            "title": title,
            "body": body_text,
            "files": files,
            "status": "locked",
            "updated_at": NOW,
        }
        try:
            existing = _req("GET", f"/items/locked_decisions?filter[lock_id][_eq]={lock_id}", token=token)
            items = (existing.get("data") or [])
            if items:
                _req("PATCH", f"/items/locked_decisions/{items[0]['id']}", token=token, body=payload)
                print(f"Updated lock: {lock_id}")
            else:
                payload["created_at"] = NOW
                _req("POST", "/items/locked_decisions", token=token, body=payload)
                print(f"Created lock: {lock_id}")
        except urllib.error.HTTPError as exc:
            print(f"Lock upsert failed for {lock_id}: {exc}", file=sys.stderr)
            return 1

    verify = subprocess.run(
        [sys.executable, str(_HERE / "verify_stitcher_lockin_20260528.py")],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
    )
    print(verify.stdout, end="")
    if verify.returncode != 0:
        print(verify.stderr, file=sys.stderr)
        return verify.returncode
    print("Stitcher lock-in registration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
