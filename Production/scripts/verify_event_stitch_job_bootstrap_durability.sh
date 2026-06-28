#!/usr/bin/env bash
# verify_event_stitch_job_bootstrap_durability.sh — EVENT_STITCH_JOB_BOOTSTRAP_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
EVENT_VIDEO="${REPO_ROOT}/Production/tools/server_handlers/event_video.py"
SERVER="${REPO_ROOT}/Production/tools/production_server.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_event_stitch_job_bootstrap.py"

fail() { echo "[event-stitch-bootstrap] FAIL: $1" >&2; exit 1; }

grep -q 'EVENT_STITCH_JOB_BOOTSTRAP_V1' "$EDITOR" || fail "server marker missing"
grep -q 'def ensure_event_stitch_job_registered' "$EDITOR" || fail "ensure helper missing"
grep -q 'EVENT_STITCH_JOB_BOOTSTRAP_V1' "$EVENT_VIDEO" || fail "event_create hook missing"
grep -q 'ensure_event_stitch_job_registered' "$SERVER" || fail "startup hook missing"

LOAD_BLOCK="$(sed -n '/def handle_stitch_load_job/,/^def handle_stitch_serve_module_final/p' "$EDITOR")"
echo "$LOAD_BLOCK" | grep -q 'ensure_event_stitch_job_registered' \
  || fail "load_job must bootstrap Event_N_stitch"
echo "$LOAD_BLOCK" | grep -q 'hydrate_stitch_canonical_slots_from_disk(h, state, event_id)' \
  && fail "load_job must not persist event disk hydrate"

python3 -m pytest "$TEST" -q
echo "[event-stitch-bootstrap] OK — source guards + pytest passed"
