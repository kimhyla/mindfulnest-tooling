#!/usr/bin/env bash
# O3_SUBPROCESS_LIFECYCLE_V1 — shutdown interrupt + startup reconcile gates.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

grep -q 'finalize_live_o3_jobs_before_shutdown' o3_generation_intent.py \
  && mark 'shutdown O3 finalize helper' \
  || err 'missing finalize_live_o3_jobs_before_shutdown'

grep -q 'finalize_live_o3_jobs_before_shutdown' production_server.py \
  && mark 'restart path calls O3 finalize' \
  || err 'production_server missing shutdown finalize'

grep -q 'run_blocking_o3_startup_reconcile' server_handlers/background.py \
  && mark 'startup reconcile wired' \
  || err 'missing startup reconcile handler'

exit "$fail"
