#!/usr/bin/env python3
"""Register waveform cue UI + preview + export lock-ins in Directus. Idempotent."""
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
        "file_path": "Production/docs/LESSONS_LEARNED_20260528_PHASE_B_WAVEFORM_CUE_UI_V1.md",
        "doc_title": "Lessons Learned — Phase B Waveform Cue UI (2026-05-28)",
        "doc_category": "lessons_learned",
        "status": "active",
        "is_current": True,
        "doc_version": "1",
        "chain_id": "phase_b_waveform_cue_ui",
        "has_locked_decisions": True,
        "notes": "Dual handle drag, pointerup commit, preview veryfast, export payload fix.",
    },
]

LOCKS = [
    (
        "WAVEFORM_CUE_DUAL_HANDLE_V1",
        "Waveform cue blocks — dual resize handles (left start + right end)",
        "Phase B/A waveform red cue rectangles MUST expose left and right drag handles. "
        "Left adjusts offset_ms with fixed end; right adjusts duration_ms with fixed start. "
        "Implementation: WaveformTimeline.tsx wc_v14 dual-handle.",
        "Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx,"
        "Production/tools/storyboard-v2/src/app.css",
    ),
    (
        "WAVEFORM_CUE_DRAG_COMMIT_ON_POINTERUP_V1",
        "Waveform cue drag — persist on pointerup only (no per-move patch)",
        "Cue range edits MUST use local dragDraft during pointermove and call "
        "onCueRangeChange/persistCues only on pointerup. Prevents HTTP 0 fetch storms "
        "during preview ffmpeg load.",
        "Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx,"
        "Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx",
    ),
    (
        "PREVIEW_OVERLAY_FAST_ENCODER_V1",
        "Phase B preview overlay — veryfast encoder preset on cache miss",
        "handle_phase_b_preview MUST pass PREVIEW_OVERLAY_ENCODER_ARGS (veryfast) to "
        "render_watercolor_overlay. LD-284 slow preset remains for final bake/normalize only.",
        "Production/tools/server_handlers/phases.py,"
        "Production/tools/credentials_lib/ffmpeg_stitch.py",
    ),
    (
        "EXPORT_TO_STITCHER_PAYLOAD_V1",
        "Export to Stitcher — correct stitch_save_job payload (LD-466)",
        "PhaseProducer export MUST POST stitch_save_job with name + slots dict "
        "(not job_name/slot/video_path shorthand). Server accepts dict-keyed slots.",
        "Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx,"
        "Production/tools/server_handlers/stitch_editor.py",
    ),
]


def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def auth():
    return _req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})["data"]["access_token"]


def upsert_ref(token, fields, payload):
    filtered = {k: v for k, v in payload.items() if k in fields}
    q = urllib.parse.quote(payload["file_path"])
    rows = _req("GET", f"/items/prod_reference_docs?filter[file_path][_eq]={q}&limit=1", token).get("data", [])
    if rows:
        rid = rows[0]["id"]
        _req("PATCH", f"/items/prod_reference_docs/{rid}", token, body=filtered)
        print(f"  PATCH prod_reference_docs/{rid}")
        return rid
    row = _req("POST", "/items/prod_reference_docs", token, body=filtered)["data"]
    print(f"  POST prod_reference_docs/{row['id']}")
    return row["id"]


def lock_ld(key, name, text, related):
    cmd = [
        sys.executable, str(_HERE / "lock_decision.py"), "lock",
        "--key", key, "--name", name, "--text", text,
        "--severity", "high", "--task-category", "architectural",
        "--enforcement-type", "lockfile",
        "--related-files", related,
        "--keyword-synonyms", "waveform,cue,preview,export,stitcher,PhaseProducer,WaveformTimeline",
        "--source-document", "LESSONS_LEARNED_20260528_PHASE_B_WAVEFORM_CUE_UI_V1.md",
    ]
    subprocess.run(cmd, check=True, cwd=str(_REPO))


def main():
    token = auth()
    fields = {f["field"] for f in _req("GET", "/fields/prod_reference_docs", token)["data"]}
    for doc in DOCS:
        p = dict(doc)
        p["updated_at"] = NOW
        upsert_ref(token, fields, p)
    for key, name, text, related in LOCKS:
        print(f"Locking {key}...")
        lock_ld(key, name, text, related)
    subprocess.run([sys.executable, str(_HERE / "lock_decision.py"), "rebuild-cache"], check=True, cwd=str(_REPO))
    print("Done.")


if __name__ == "__main__":
    main()
