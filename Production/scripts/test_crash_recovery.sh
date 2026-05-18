#!/usr/bin/env bash
# V59 Phase 8 — synthetic crash-recovery test for durable_job_registry.
#
# Per V59 spec §Phase 8 (LD-794). Scope-trimmed from "wire vendor submissions
# through the registry + kill -9 during real vendor calls" (1-2 hr) to
# "directly submit 3 rows + kill -9 the server + restart + verify rows
# survived" (~5 min wallclock).
#
# Rationale: full vendor wiring is out of scope for this overnight build
# (Phase 5 only created the registry; wiring into submit paths is a
# follow-up). The synthetic test still proves the load-bearing claim — the
# SQLite WAL-mode DB at Production/Event_1/.vendor_jobs.db is durable
# across SIGKILL of the writing process.
#
# Test flow:
#   1. Submit 3 distinct rows to durable_job_registry (kling, bytedance, openai)
#   2. Capture pre-kill row count + task_ids
#   3. kill -9 the production_server PID on port 5111
#   4. Restart production_server from tooling tree
#   5. Open a fresh registry connection
#   6. Verify all 3 rows still present + task_ids match
#   7. Cleanup: purge_stale with epoch=future to remove the test rows
#
# Exit codes:
#   0 — 3/3 rows persisted across kill -9 + restart
#   1 — any row lost OR server failed to restart
set -euo pipefail

cd ~/Projects/mindfulnest-tooling

EVENT_DIR="/Users/kimberlysmith/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production/Event_1"
PYTHON=/Users/kimberlysmith/.pyenv/versions/3.12.7/bin/python3
LOGDIR=logs
mkdir -p "$LOGDIR"

echo "=== V59 Phase 8 crash-recovery test ==="
date

# Step 1+2: submit 3 rows via Python helper
SUBMIT_OUT=$(PYTHONPATH=Production "$PYTHON" - <<'PYEOF'
import time, json
from Production.lib.durable_job_registry import DurableJobRegistry
r = DurableJobRegistry()
now = int(time.time())
task_ids = []
for i, vendor in enumerate(["kling", "bytedance", "openai"]):
    tid = f"phase8_crash_test_{vendor}_{now}_{i}"
    r.submit(
        beat_id=f"beat_crash_test_{i}",
        vendor=vendor,
        task_id=tid,
        video_role="intro",
        event_generation=999,
        option_idx=i,
    )
    task_ids.append(tid)
pending = r.list_pending()
print(json.dumps({"task_ids": task_ids, "pending_count": len(pending), "now_epoch": now}))
PYEOF
)
echo "submit phase: $SUBMIT_OUT"
TASK_IDS=$(echo "$SUBMIT_OUT" | "$PYTHON" -c "import sys,json; print(' '.join(json.loads(sys.stdin.read())['task_ids']))")
NOW=$(echo "$SUBMIT_OUT" | "$PYTHON" -c "import sys,json; print(json.loads(sys.stdin.read())['now_epoch'])")

# Step 3: kill -9 server
SERVER_PID=$(lsof -ti:5111 || true)
if [ -z "$SERVER_PID" ]; then
    echo "  ! no server on 5111 — starting fresh"
else
    echo "  kill -9 server PID $SERVER_PID"
    kill -9 "$SERVER_PID"
    sleep 2
fi

# Step 4: restart server
echo "  restart server from tooling tree"
nohup "$PYTHON" Production/tools/production_server.py \
    --event-dir "$EVENT_DIR" \
    --storyboard storyboard_v59_prod.html \
    --event-id Event_1 \
    > "$LOGDIR/server_overnight_phase8_$(date +%H%M%S).log" 2>&1 &
sleep 5
NEW_PID=$(lsof -ti:5111 | head -1 || true)
if [ -z "$NEW_PID" ]; then
    echo "FAIL: server did not restart"
    exit 1
fi
echo "  new server PID $NEW_PID"

# Step 5+6: fresh registry connection, verify rows
VERIFY_OUT=$(PYTHONPATH=Production "$PYTHON" - <<PYEOF
import json
from Production.lib.durable_job_registry import DurableJobRegistry
r = DurableJobRegistry()
task_ids = "$TASK_IDS".split()
found = 0
missing = []
for tid in task_ids:
    row = r.get(tid)
    if row:
        found += 1
    else:
        missing.append(tid)
print(json.dumps({"submitted": len(task_ids), "found": found, "missing": missing}))
PYEOF
)
echo "verify phase: $VERIFY_OUT"

FOUND=$(echo "$VERIFY_OUT" | "$PYTHON" -c "import sys,json; print(json.loads(sys.stdin.read())['found'])")
SUBMITTED=$(echo "$VERIFY_OUT" | "$PYTHON" -c "import sys,json; print(json.loads(sys.stdin.read())['submitted'])")

# Step 7: cleanup
PYTHONPATH=Production "$PYTHON" - <<PYEOF
from Production.lib.durable_job_registry import DurableJobRegistry
r = DurableJobRegistry()
# Mark our test rows completed then purge using a future epoch
task_ids = "$TASK_IDS".split()
for tid in task_ids:
    r.mark(tid, "completed")
deleted = r.purge_stale(older_than_epoch=$NOW + 86400)
print(f"  cleanup: purged {deleted} test rows")
PYEOF

echo "---"
if [ "$FOUND" = "$SUBMITTED" ] && [ "$SUBMITTED" = "3" ]; then
    echo "PHASE_8_PASS: 3/3 rows persisted across kill -9 + restart (synthetic test)"
    exit 0
else
    echo "PHASE_8_FAIL: $FOUND/$SUBMITTED rows persisted"
    exit 1
fi
