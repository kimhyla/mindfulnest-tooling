#!/usr/bin/env python3
"""Register magic path surface lock-ins in Directus. Idempotent."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.parse
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
        "file_path": "Production/docs/LESSONS_LEARNED_20260528_MAGIC_PATH_SURFACE_V1.md",
        "doc_title": "Lessons Learned — Magic Path Surface Lock (2026-05-28)",
        "doc_category": "lessons_learned",
        "status": "active",
        "is_current": True,
        "doc_version": "1",
        "chain_id": "magic_path_surface_v1",
        "has_locked_decisions": True,
        "notes": "Draw surface dim lock, PATH_SURFACE_MISMATCH guard, manual_path persist.",
    },
]

LOCKS = [
    (
        "MAGIC_PATH_SURFACE_DIM_LOCK_V1",
        "Magic on video — path draw surface must match lipsync frame dims",
        "magic_video path_picker, video_frame endpoint, MagicCompositor, and ffmpeg decode "
        "MUST share the same even W×H via _magic_canvas_dims. POST rejects PATH_SURFACE_MISMATCH "
        "when path_authored_against dims differ from source video dims (still crop vs lipsync frame).",
        "Production/tools/server_handlers/background.py,"
        "Production/tools/path_picker.html,"
        "Production/tools/magic_compositor.py",
    ),
    (
        "MAGIC_PATH_POLYLINE_INTERP_V1",
        "Magic manual_path — polyline interpolation matches path_picker",
        "MagicCompositor default path_interp MUST be polyline: straight segments "
        "through each manual_path point in order (matches path_picker.html lineTo). "
        "Bezier smoothing is legacy-only via path_interp='bezier'.",
        "Production/tools/magic_compositor.py,"
        "Production/tools/tests/test_magic_path_polyline.py",
    ),
    (
        "MAGIC_MANUAL_PATH_STATE_PERSIST_V1",
        "Magic render — persist manual_path on beat state",
        "handle_magic_still and handle_magic_video MUST write magic_manual_path and "
        "magic_path_authored_against to the scoped beat partition on success.",
        "Production/tools/server_handlers/background.py",
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
        payload = {**doc, "registered_at": NOW}
        try:
            _req("POST", "/items/reference_docs", token=token, body=payload)
            print(f"Registered doc: {doc['doc_title']}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 400 and "unique" in body.lower():
                print(f"Doc already exists: {doc['doc_title']}")
            else:
                print(f"Doc register failed: {exc.code} {body}", file=sys.stderr)
                return 1

    for key, title, decision_text, files in LOCKS:
        payload = {
            "decision_key": key,
            "title": title,
            "decision_text": decision_text,
            "status": "locked",
            "locked_at": NOW,
            "files_affected": files,
            "notes": "Magic path surface lock-in 2026-05-28 (LD-828/829).",
        }
        try:
            _req("POST", "/items/locked_decisions", token=token, body=payload)
            print(f"Registered lock: {key}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            if exc.code == 400 and "unique" in body.lower():
                print(f"Lock already exists: {key}")
            else:
                print(f"Lock register failed: {exc.code} {body}", file=sys.stderr)
                return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
