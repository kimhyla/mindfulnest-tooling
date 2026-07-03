#!/usr/bin/env bash
# O3_JOB_TRUTH_STACK_V1 — live session GET beat fields on Event_4 (beat 15 class).
set -euo pipefail
PORT="${MN_LIVE_PORT:-5114}"
BASE="http://localhost:${PORT}"
BEAT_ID="${O3_LIVE_TRUTH_BEAT_ID:-bg_arc1_event4_pre_beat_15}"
SCOPE_QS="scope_type=project&event_id=Event_4&scope_event_id=Event_4&scope_arc_number=1&scope_video_role=intro"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

curl -sf "${BASE}/api/health" >/dev/null \
  && mark "live server health :${PORT}" \
  || { err "live server down :${PORT}"; exit 1; }

session_json="$(curl -sf "${BASE}/api/bg/session-state?${SCOPE_QS}")"
export SESSION_JSON="$session_json" BEAT_ID="$BEAT_ID"
python3 - <<'PY'
import json, os, sys
session = json.loads(os.environ["SESSION_JSON"])
beat_id = os.environ["BEAT_ID"]
rows = session.get("beats") or []
session_beat = next((b for b in rows if b.get("beat_id") == beat_id), None)
if not session_beat:
    print("  FAIL no session beat", beat_id)
    sys.exit(1)
status = str(session_beat.get("kling_o3_status") or "")
path = str(session_beat.get("kling_o3_video_path") or "")
if not path.endswith(".mp4"):
    print("  FAIL beat missing mp4 path:", path)
    sys.exit(1)
print("  OK  live session beat", beat_id, "status=", status, "path=", path[-48:])
PY

exit "$fail"
