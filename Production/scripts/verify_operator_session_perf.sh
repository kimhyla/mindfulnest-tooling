#!/usr/bin/env bash
# verify_operator_session_perf.sh — OPERATOR_SESSION_PERF_V1 cold-boot + client debounce markers
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PROVISION="${ROOT}/Production/lib/event_server_provision.py"
BGSTORE="${ROOT}/Production/tools/storyboard-v2/src/state/bgSessionStore.ts"
PHASE="${ROOT}/Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx"
POLL="${ROOT}/Production/tools/storyboard-v2/src/components/BgPollCoordinator.tsx"
WATCHER="${ROOT}/Production/tools/storyboard-v2/src/components/ServerRehydrateWatcher.tsx"
COLD_BOOT_BUDGET_MS="${MN_COLD_BOOT_BUDGET_MS:-8000}"

fail() { echo "[operator-session-perf] FATAL: $1" >&2; exit 1; }

echo "[operator-session-perf] pass 1/4 — cold-boot budget"
grep -q 'DEFAULT_WAIT_SECONDS = 180' "$PROVISION" \
  || fail "provision cold-boot must be 180s (aligned with launchd script)"

echo "[operator-session-perf] pass 2/4 — poll debounce + lazy base clips + focus debounce"
grep -q 'scheduleRefreshBgSession' "$BGSTORE" || fail "bgSessionStore missing debounced refresh"
grep -q 'scheduleRefreshBgSession' "$POLL" || fail "BgPollCoordinator must use debounced refresh"
grep -q 'ensureBaseClipsLoaded' "$PHASE" || fail "PhaseProducer must lazy-load base clips"
grep -q 'CHECK_DEBOUNCE_MS' "$WATCHER" || fail "ServerRehydrateWatcher missing check debounce"
grep -q 'setTimeout' "$PHASE" || fail "PhaseProducer focus handler missing debounce"
python3 <<PY || fail "refreshAll must not eagerly fetch phase_base_clips_list"
from pathlib import Path
text = Path("$PHASE").read_text()
start = text.index("const refreshAll = async")
chunk = text[start:start + 1800]
if "phase_base_clips_list" in chunk:
    raise SystemExit("refreshAll still eagerly fetches phase_base_clips_list")
PY

echo "[operator-session-perf] pass 3/4 — ambient lazy fetch (phase b only)"
grep -q "phase === 'b'" "$PHASE" || fail "PhaseProducer phase guard missing"
grep -q 'phase_b_ambient_preset_list' "$PHASE" || fail "ambient catalog path missing"

echo "[operator-session-perf] pass 4/4 — live cold-path benchmark (optional)"
BASE="${MN_STORYBOARD_BASE:-http://localhost:5111}"
if curl -sf "${BASE}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import time, urllib.request, json, sys
base = "${BASE}"
budget_ms = int("${COLD_BOOT_BUDGET_MS}")
t0 = time.monotonic()
with urllib.request.urlopen(base + "/api/event/current", timeout=10) as resp:
    data = json.loads(resp.read().decode())
elapsed_ms = int((time.monotonic() - t0) * 1000)
print(f"[operator-session-perf] event/current {elapsed_ms}ms ok={data.get('ok')}")
if elapsed_ms > budget_ms:
    sys.exit(f"event/current exceeded budget {budget_ms}ms")
PY
else
  echo "[operator-session-perf] skip live benchmark — server down"
fi

echo "[operator-session-perf] OK"
