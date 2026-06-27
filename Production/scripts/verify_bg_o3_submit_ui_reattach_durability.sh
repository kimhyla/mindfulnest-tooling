#!/usr/bin/env bash
# verify_bg_o3_submit_ui_reattach_durability.sh — BG_O3_SUBMIT_UI_REATTACH_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BG="${REPO_ROOT}/Production/tools/server_handlers/background.py"
CONTRACT="${REPO_ROOT}/Production/tools/storyboard-v2/src/o3JobStatusContract.ts"
BGTAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/BgTab.tsx"
STORE="${REPO_ROOT}/Production/tools/storyboard-v2/src/state/bgSessionStore.ts"

fail() { echo "[bg-o3-submit-ui-reattach] FAIL: $1" >&2; exit 1; }

[[ -f "$BG" ]] || fail "missing background.py"
[[ -f "$CONTRACT" ]] || fail "missing o3JobStatusContract.ts"
[[ -f "$BGTAB" ]] || fail "missing BgTab.tsx"
[[ -f "$STORE" ]] || fail "missing bgSessionStore.ts"

grep -q '_o3_submit_reattach_response_if_running' "$BG" \
  || fail "server must reattach before intent build"
grep -q 'BG_O3_SUBMIT_UI_REATTACH_V1' "$CONTRACT" \
  || fail "contract must document latch vs stale job_busy"
grep -q 'o3BeatTerminallyIdleForSubmitLatch' "$CONTRACT" \
  || fail "contract must gate latch prune on terminal idle only"
grep -q 'beatO3GenerateInFlight' "$CONTRACT" \
  || fail "contract must expose unified Generate in-flight authority"
grep -q 'tryReattachO3JobFromSession' "$STORE" \
  || fail "session store must reattach from job_busy"
grep -q 'BG_O3_SUBMIT_UI_REATTACH_V1' "$BGTAB" \
  || fail "BgTab must reattach on ambiguous submit"
grep -q 'bg-generate-save-blocked' "$BGTAB" \
  || fail "BgTab must toast when flushSave blocks Generate"

cd "${REPO_ROOT}/Production/tools/storyboard-v2"
node --experimental-strip-types --test src/utils/__tests__/o3JobStatusContract.test.ts \
  || fail "o3JobStatusContract unit tests failed"

cd "${REPO_ROOT}/Production/tools"
python3 -m pytest tests/test_o3_submit_reattach_early.py -q \
  || fail "pytest test_o3_submit_reattach_early failed"

echo "[bg-o3-submit-ui-reattach] OK — latch + reattach category wired"
