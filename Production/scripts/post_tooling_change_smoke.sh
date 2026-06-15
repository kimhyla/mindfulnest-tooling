#!/usr/bin/env bash
# Autonomous post-tooling-change smoke — operator-free QA loop (Kim does not run terminal).
#
# Runs in dependency order:
#   1) O3/intro contract pytest
#   2) Deploy-backup beat_generator contract
#   3) Rsync tooling → Dropbox (critical dirs)
#   4) Dual-root sha256 parity
#   5) Restart production_server.py
#   6) HTTP + O3 capability + beat_07 sidecar spot-check
#
# Usage:
#   bash Production/scripts/post_tooling_change_smoke.sh
#   MN_DEPLOY_SKIP_BUILD=1 bash Production/scripts/post_tooling_change_smoke.sh

set -euo pipefail

SRC_TOOLING="${MN_TOOLING_ROOT:-/Users/kimberlysmith/Projects/mindfulnest-tooling}"
DEST_DROPBOX="${MN_DROPBOX_ROOT:-/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
EVENT_DIR="${MN_EVENT_DIR:-Production/Event_1}"
SERVER_PORT="${MN_SERVER_PORT:-5111}"
EVENT_ABS="$DEST_DROPBOX/$EVENT_DIR"
LOG_FILE="$EVENT_ABS/post_tooling_smoke_server.log"

echo "=== [1/6] O3/intro contract pytest ==="
bash "$SRC_TOOLING/Production/scripts/verify_o3_intro_contract.sh"

echo "=== [2/6] Deploy-backup beat_generator contract ==="
python3 "$SRC_TOOLING/Production/scripts/verify_deploy_backup_contract.py" \
  --beat-generator "$SRC_TOOLING/Production/tools/beat_generator.py"

echo "=== [3/6] Rsync tooling → Dropbox (tools/lib/scripts) ==="
for sub in Production/tools Production/lib Production/scripts; do
  rsync -a --delete \
    --exclude 'stitch_editor_state.json' \
    "$SRC_TOOLING/$sub/" \
    "$DEST_DROPBOX/$sub/"
  echo "  mirrored: $sub"
done

echo "=== [4/6] Dual-root parity ==="
MN_TOOLING_ROOT="$SRC_TOOLING" MN_DROPBOX_ROOT="$DEST_DROPBOX" \
  python3 "$SRC_TOOLING/Production/scripts/verify_tooling_dropbox_parity.py"

echo "=== [5/6] Restart production_server.py ==="
lsof -ti:"$SERVER_PORT" | xargs kill -9 2>/dev/null || true
pkill -f "production_server.py" 2>/dev/null || true
sleep 2
cd "$DEST_DROPBOX"
nohup env PRODUCTION_SERVER_SINGLE_MACHINE=1 python3 "$DEST_DROPBOX/Production/tools/production_server.py" \
  --event-dir "$EVENT_DIR" \
  --storyboard "storyboard_v59_prod.html" \
  --event-id "$(basename "$EVENT_DIR")" \
  >> "$LOG_FILE" 2>&1 &
sleep 4

echo "=== [6/6] HTTP + capability + beat_07 spot-check ==="
HOME_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${SERVER_PORT}/")
if [[ "$HOME_CODE" != "200" ]]; then
  echo "FATAL: GET / returned $HOME_CODE" >&2
  tail -30 "$LOG_FILE" >&2 || true
  exit 1
fi
echo "  GET / → $HOME_CODE"

CAP_JSON=$(curl -sS --max-time 15 \
  "http://localhost:${SERVER_PORT}/api/bg/session-state?scope_event_id=Event_1&scope_video_role=intro")
O3_OK=$(printf '%s' "$CAP_JSON" | python3 -c "
import sys, json
c = json.load(sys.stdin).get('capabilities') or {}
print('ok' if c.get('update_beat_locked') and c.get('sidecar_file_lock') else 'fail')
")
if [[ "$O3_OK" != "ok" ]]; then
  echo "FATAL: O3 capabilities check failed (got $O3_OK)" >&2
  printf '%s\n' "$CAP_JSON" | python3 -m json.tool 2>/dev/null | head -20 >&2 || true
  exit 1
fi
echo "  O3 capabilities → ok"

SIDECAR="$DEST_DROPBOX/Production/beat_generator_state.json"
python3 - <<PY
import json, sys
from pathlib import Path
sys.path.insert(0, "$DEST_DROPBOX/Production/tools")
import beat_generator as bg
sidecar = json.loads(Path("$SIDECAR").read_text(encoding="utf-8"))
_, b = bg.find_beat(sidecar, "bg_arc1_event1_pre_beat_07")
if not b:
    raise SystemExit("FATAL: beat_07 missing from sidecar")
opts = b.get("kling_o3_options") or []
print("  beat_07 status:", b.get("status"))
print("  beat_07 error:", b.get("kling_o3_voice_fix_error"))
print("  beat_07 options:", len(opts), [o.get("label") for o in opts])
if b.get("kling_o3_voice_fix_error"):
    raise SystemExit("FATAL: beat_07 still has kling_o3_voice_fix_error")
PY

echo "=== post_tooling_change_smoke: ALL PASSED ==="
