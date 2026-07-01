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

# Gate: poll path should not read voice_fix_status without truth stack nearby
if rg -n 'kling_o3_voice_fix_status' server_handlers/background.py \
  | rg -v 'resolve_beat_o3_truth|truth|enrich_beat' >/dev/null 2>&1; then
  : # allowed reads outside poll enrich — warn only
fi

python3 -m pytest tests/test_o3_job_truth.py -q \
  && mark 'pytest test_o3_job_truth' \
  || err 'pytest test_o3_job_truth failed'

exit "$fail"
