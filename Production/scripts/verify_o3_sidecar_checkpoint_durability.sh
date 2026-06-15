#!/usr/bin/env bash
# verify_o3_sidecar_checkpoint_durability.sh — O3 delivery checkpoint + orphan recovery
#
# Regression: Kling finished but persist_o3_delivery_option_checkpoint hit Dropbox errno 11,
# leaving empty option slots until manual recovery.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PIPELINE="${REPO_ROOT}/Production/tools/kling_o3_element_beat_pipeline.py"
HANDLER="${REPO_ROOT}/Production/tools/server_handlers/background.py"
TEST_STUCK="${REPO_ROOT}/Production/tools/tests/test_o3_stuck_job_recovery.py"
TEST_IO="${REPO_ROOT}/Production/tools/tests/test_sidecar_io_durability.py"

fail() { echo "[o3-sidecar-checkpoint-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$PIPELINE" ]] || fail "missing kling_o3_element_beat_pipeline.py"
[[ -f "$HANDLER" ]] || fail "missing background.py"

grep -q 'persist_o3_delivery_option_checkpoint' "$PIPELINE" \
  || fail "pipeline must checkpoint delivery before finalize"
grep -A20 'persist_o3_delivery_option_checkpoint' "$PIPELINE" | grep -q 'recover_orphan_o3_delivery' \
  || fail "checkpoint persist must call recover_orphan_o3_delivery on failure"

grep -q '_finalize_o3_job_after_subprocess_exit' "$HANDLER" \
  || fail "poll handler must finalize with orphan recovery"
grep -q 'delivery_encode' "$HANDLER" \
  || fail "log parser must accept delivery_encode when done is missing"

python3 -m pytest "$TEST_STUCK" "$TEST_IO" -q

echo "[o3-sidecar-checkpoint-durability] OK — source guards + pytest passed"
