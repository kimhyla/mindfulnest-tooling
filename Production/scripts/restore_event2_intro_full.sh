#!/usr/bin/env bash
# restore_event2_intro_full.sh — restore Event_2 intro beats from snapshot + merge + stitch order.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
SNAP="${REPO_ROOT}/Production/.production_snapshots/archive/20260624T140024Z/global/beat_generator_state.json"
LOG="/tmp/event2_intro_restore_$(date +%Y%m%dT%H%M%S).log"

exec > >(tee -a "$LOG") 2>&1
echo "[restore-event2-intro] start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[restore-event2-intro] log=$LOG"

[[ -f "$SNAP" ]] || { echo "FATAL: missing snapshot $SNAP"; exit 1; }

export MN_SIDECAR_ALLOW_FULL_REPLACE=1
export PYTHONPATH="${TOOLS}:${REPO_ROOT}/Production:${PYTHONPATH:-}"
export REPO_ROOT SNAP_PATH="$SNAP"

python3 <<'PY'
import json
import os
import sys
from pathlib import Path

repo = Path(os.environ["REPO_ROOT"])
tools = repo / "Production" / "tools"
sys.path[:0] = [str(tools), str(repo / "Production")]

import beat_generator as bg  # noqa: E402
from lib.paths import dropbox_root  # noqa: E402

snap_path = Path(os.environ["SNAP_PATH"])
event_dir = dropbox_root() / "Production" / "Event_2"
restored = json.loads(snap_path.read_text(encoding="utf-8"))
pre_seg = restored["arcs"]["arc_1"]["segments"].get("event_2_pre", {})
pre_n = len(pre_seg.get("beats") or [])
print(f"[restore-event2-intro] snapshot event_2_pre beats={pre_n}")

bg.init_bg_paths(event_dir)
bg.write_sidecar(restored)
bg.flush_sidecar_mirror_export()
live = bg.read_sidecar()
live_pre = len(live["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"])
print(f"[restore-event2-intro] after snapshot import event_2_pre beats={live_pre}")
PY

bash "${SCRIPT_DIR}/merge_event2_recovered_beats.py" 2>/dev/null || python3 "${SCRIPT_DIR}/merge_event2_recovered_beats.py"
python3 "${SCRIPT_DIR}/restore_event2_intro_from_stitch_export.py"

python3 <<'PY'
import json
import os
import sys
import urllib.request
from pathlib import Path

repo = Path(os.environ["REPO_ROOT"])
tools = repo / "Production" / "tools"
sys.path[:0] = [str(tools), str(repo / "Production")]
import beat_generator as bg  # noqa: E402
from lib.paths import dropbox_root  # noqa: E402

event_dir = dropbox_root() / "Production" / "Event_2"
bg.init_bg_paths(event_dir)
sc = bg.read_sidecar()
pre = sc["arcs"]["arc_1"]["segments"]["event_2_pre"]["beats"]
ids = [b.get("beat_id") for b in pre]
print(json.dumps({"event_2_pre_count": len(ids), "first": ids[0] if ids else None, "last": ids[-1] if ids else None}, indent=2))

req = urllib.request.Request(
    "http://localhost:5112/api/event/load",
    data=json.dumps({"event_id": "Event_2"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    print("event/load", r.read().decode()[:200])

url = "http://localhost:5112/api/bg/session-state?scope_event_id=Event_2&scope_video_role=intro&scope_arc_number=1&scope_phase=pre"
with urllib.request.urlopen(url, timeout=60) as r:
    st = json.loads(r.read().decode())
beats = st.get("beats") or []
api_ids = [b.get("beat_id") for b in beats]
print(json.dumps({"api_intro_count": len(api_ids), "first": api_ids[0] if api_ids else None, "last": api_ids[-1] if api_ids else None}, indent=2))
if not api_ids or not str(api_ids[0]).startswith("bg_arc1_event2_pre"):
    raise SystemExit("VERIFY FAIL: Event_2 intro API beats not restored")
print("[restore-event2-intro] VERIFY OK")
PY

echo "[restore-event2-intro] done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
