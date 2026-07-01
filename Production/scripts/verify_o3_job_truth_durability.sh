#!/usr/bin/env bash
# O3_JOB_TRUTH_STACK_V1 — single resolver gate + pytest matrix smoke.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

test -f o3_job_truth.py \
  && grep -q 'resolve_beat_o3_truth' o3_job_truth.py \
  && grep -q 'O3_JOB_TRUTH_STACK_V1' o3_job_truth.py \
  && mark 'o3_job_truth.py authority module' \
  || err 'missing o3_job_truth.py'

grep -q 'resolve_beat_o3_truth' server_handlers/background.py \
  && mark 'O3 poll uses truth resolver' \
  || err 'background poll missing truth resolver'

grep -q 'resolve_beat_o3_truth_for_session_compose' o3_session_terminal_reconcile.py \
  && mark 'session GET compose uses truth resolver' \
  || err 'compose_session_terminal_view missing truth resolver'

# Phase 1 gate: session GET compose uses truth. Full voice_fix read allowlist — Phase 7.
grep -q 'if session_read_only:' server_handlers/background.py \
  && grep -q 'resolve_o3_current_job_id' server_handlers/background.py \
  && mark 'session_read_only enrich busy-only path' \
  || err 'session_read_only enrich contract missing'

python3 -m pytest tests/test_o3_job_truth.py -q \
  && mark 'pytest test_o3_job_truth' \
  || err 'pytest test_o3_job_truth failed'

exit "$fail"
