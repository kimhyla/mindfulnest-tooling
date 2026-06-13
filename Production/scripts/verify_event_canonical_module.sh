#!/usr/bin/env bash
# verify_event_canonical_module.sh — EVENT_1_CANONICAL_MODULE_V1 pin integrity.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PIN="${REPO_ROOT}/Production/tools/pin_event_canonical_module.py"
EVENT_DIR="${MN_EVENT_DIR:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1}"
STATE="${EVENT_DIR}/production_state.json"

fail() { echo "[event-canonical-module] FAIL: $1" >&2; exit 1; }

[[ -f "$PIN" ]] || fail "missing pin_event_canonical_module.py"
[[ -f "$STATE" ]] || fail "missing production_state.json"

python3 <<PY
import json, os, hashlib, subprocess, sys
from pathlib import Path

event_dir = Path("${EVENT_DIR}")
state_path = event_dir / "production_state.json"
st = json.loads(state_path.read_text(encoding="utf-8"))
if not st.get("EVENT_1_CANONICAL_MODULE_V1"):
    sys.exit("EVENT_1_CANONICAL_MODULE_V1 not set in production_state")
name = st.get("canonical_module_final_file") or ""
if not name:
    sys.exit("canonical_module_final_file missing")
canonical = event_dir / name
if not canonical.is_file():
    sys.exit(f"canonical file missing: {canonical}")
mtime = int(os.path.getmtime(canonical))
if st.get("canonical_module_final_mtime") and abs(mtime - int(st["canonical_module_final_mtime"])) > 2:
    sys.exit(f"mtime drift: disk={mtime} state={st['canonical_module_final_mtime']}")
expected = st.get("canonical_module_final_sha256") or ""
if expected:
    h = hashlib.sha256()
    with canonical.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    if h.hexdigest() != expected:
        sys.exit("sha256 mismatch — canonical file changed since pin")
dur = subprocess.check_output(
    ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(canonical)],
    text=True,
).strip()
dur_ms = int(float(dur)*1000)
state_dur = int(st.get("canonical_module_final_duration_ms") or 0)
if state_dur and abs(dur_ms - state_dur) > 500:
    sys.exit(f"duration drift: disk={dur_ms}ms state={state_dur}ms")
print(f"OK canonical={name} dur_ms={dur_ms} sha256={expected[:12]}...")
PY

echo "[event-canonical-module] OK — canonical pin matches disk"
