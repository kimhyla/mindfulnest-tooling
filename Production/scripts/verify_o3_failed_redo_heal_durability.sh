#!/usr/bin/env bash
# O3_FAILED_REDO_HEAL_V1 — grep gate + pytest for failed regen sidecar heal.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

grep -q 'O3_FAILED_REDO_HEAL_V1' o3_generation_intent.py \
  && grep -q 'restore_last_good_o3_delivery_after_failed_attempt' o3_generation_intent.py \
  && mark 'restore_last_good_o3_delivery_after_failed_attempt present' \
  || err 'missing O3_FAILED_REDO_HEAL_V1 heal function'

grep -q 'restore_last_good_o3_delivery_after_failed_attempt' o3_session_terminal_reconcile.py \
  && mark 'terminal reconcile calls heal on failed' \
  || err 'reconcile missing failed heal'

grep -q 'restore_last_good_o3_delivery_after_failed_attempt' o3_job_status_contract.py \
  && mark 'clear_o3_pointer failed branch uses heal' \
  || err 'clear_o3_pointer missing heal'

python3 -m pytest tests/test_o3_failed_redo_heal.py -q \
  && mark 'pytest test_o3_failed_redo_heal' \
  || err 'pytest test_o3_failed_redo_heal failed'

exit "$fail"
