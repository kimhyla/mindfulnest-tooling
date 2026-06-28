#!/usr/bin/env bash
# verify_stitch_single_owner_durability.sh — STITCH_SINGLE_OWNER_V1 (pre-deploy)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
TAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_single_owner.py"

fail() { echo "[stitch-single-owner] FAIL: $1" >&2; exit 1; }

grep -q 'STITCH_SINGLE_OWNER_V1' "$EDITOR" || fail "server marker missing"
grep -q 'job_persisted' "$EDITOR" || fail "job_persisted gate missing"
grep -q 'data-stitch-single-owner' "$TAB" || fail "client marker missing"

LOAD_BLOCK="$(sed -n '/def handle_stitch_load_job/,/^def handle_stitch_serve_module_final/p' "$EDITOR")"
echo "$LOAD_BLOCK" | grep -q 'persist_milestone_hydrate' && fail "load_job still persists milestone hydrate"
echo "$LOAD_BLOCK" | grep -q 'bootstrap_milestone_job' && fail "load_job still bootstraps milestone job"
echo "$LOAD_BLOCK" | grep -q 'hydrate_stitch_canonical_slots_from_disk(h, state, event_id)' \
  && fail "load_job still persists event disk hydrate"

python3 -m pytest "$TEST" -q
echo "[stitch-single-owner] OK — source guards + pytest passed"
