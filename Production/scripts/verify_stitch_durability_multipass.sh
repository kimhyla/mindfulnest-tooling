#!/usr/bin/env bash
# verify_stitch_durability_multipass.sh — three-pass deploy + export integrity gate.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

REPO_ROOT="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"

EVENT_ID="${MN_EVENT_ID:-Event_1}"
PORT="${MN_SERVER_PORT:-$(event_id_to_port "$EVENT_ID")}"
EVENT_DIR="${MN_EVENT_DIR:-${DROPBOX}/Production/${EVENT_ID}}"

fail() { echo "[stitch-durability-multipass] FAIL pass=$1: $2" >&2; exit 1; }

echo "[multipass] Pass 1 — source gates + pytest"
bash "$REPO_ROOT/Production/scripts/verify_phase_voice_stem_pin_durability.sh"
bash "$REPO_ROOT/Production/scripts/verify_stitch_slot_audio_extract_durability.sh"
bash "$REPO_ROOT/Production/scripts/verify_stitch_slot_export_full_media_durability.sh"

echo "[multipass] Pass 2 — deploy parity (build-sha + Dropbox storyboard)"
HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
HTML_SHA="$(python3 - <<PY
import re, pathlib
html = pathlib.Path("${EVENT_DIR}/storyboard_v59_prod.html").read_text(encoding="utf-8", errors="replace")
m = re.search(r'name="build-sha" content="([^"]+)"', html)
print(m.group(1) if m else "")
PY
)"
[[ -n "$HTML_SHA" ]] || fail 2 "storyboard missing build-sha meta"
[[ "$HTML_SHA" == "$HEAD_SHA" ]] || fail 2 "build-sha $HTML_SHA != HEAD $HEAD_SHA"
curl -sf "http://localhost:${PORT}/" | python3 -c "
import re, sys
html = sys.stdin.read()
m = re.search(r'name=\"build-sha\" content=\"([^\"]+)\"', html)
live = m.group(1) if m else ''
head = '${HEAD_SHA}'
if live != head:
    raise SystemExit(f'live server build-sha {live!r} != HEAD {head}')
"

echo "[multipass] Pass 3 — live API smoke (slot durations + audio extract parity)"
python3 <<PY
import json, subprocess, urllib.request
from pathlib import Path

event = Path("${EVENT_DIR}")
base = "http://localhost:${PORT}"
job_name = "${EVENT_ID}_stitch"
scope_event = "${EVENT_ID}"

req = urllib.request.Request(f"{base}/api/stitch_editor/job/{job_name}?event_id={scope_event}")
with urllib.request.urlopen(req, timeout=15) as r:
    payload = json.loads(r.read().decode())
job = payload.get("job") or payload
slots = job.get("slots") or {}

def resolve_video(vp: str) -> Path:
    if not vp:
        raise SystemExit("empty video_path")
    p = Path(vp)
    if p.is_file():
        return p
    if "Event_1/" in vp.replace("\\\\", "/"):
        rel = vp.replace("\\\\", "/").split("Event_1/", 1)[1]
        cand = event / rel
        if cand.is_file():
            return cand
    event_name = "${EVENT_ID}"
    if f"{event_name}/" in vp.replace("\\\\", "/"):
        rel = vp.replace("\\\\", "/").split(f"{event_name}/", 1)[1]
        cand = event / rel
        if cand.is_file():
            return cand
    cand = event / p.name
    if cand.is_file():
        return cand
    raise SystemExit(f"cannot resolve video_path: {vp}")

for key in ("intro", "phase_a", "phase_b", "resolution"):
    slot = slots.get(key) or {}
    vp = slot.get("video_path") or ""
    dur = int(slot.get("video_dur_ms") or 0)
    if not vp or dur <= 0:
        raise SystemExit(f"slot {key} missing video_path or video_dur_ms")
    p = resolve_video(vp)
    out = subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(p)],
        text=True,
    ).strip()
    probed = int(float(out)*1000)
    if abs(probed - dur) > 500:
        raise SystemExit(f"{key}: slot dur {dur} != file {probed} ({p.name})")
    print(f"  {key}: {dur}ms OK ({p.name})")

body = json.dumps({
    "scope_event_id": scope_event,
    "scope_video_role": "intro",
    "video_path": slots["phase_a"]["video_path"],
    "ambient_bed": slots["phase_a"].get("ambient_bed") or "ambient bed pretty option2",
    "ambient_volume": 0.15,
    "sfx_cues": [],
}).encode()
req = urllib.request.Request(
    f"{base}/api/stitch_editor/audio_extract",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as r:
    ex = json.loads(r.read().decode())
if abs(int(ex.get("duration_ms") or 0) - int(ex.get("video_dur_ms") or 0)) > 500:
    raise SystemExit("audio extract duration != video_dur_ms")
print("  phase_a audio extract: parity OK")
PY

echo "[stitch-durability-multipass] OK — 3 passes green (sha=${HEAD_SHA})"
