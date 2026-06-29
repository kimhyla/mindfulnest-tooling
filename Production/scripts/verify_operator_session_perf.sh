#!/usr/bin/env bash
# verify_operator_session_perf.sh — OPERATOR_SESSION_PERF_V1 cold-boot + client debounce markers
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PROVISION="${ROOT}/Production/lib/event_server_provision.py"
BGSTORE="${ROOT}/Production/tools/storyboard-v2/src/state/bgSessionStore.ts"
PHASE="${ROOT}/Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx"
POLL="${ROOT}/Production/tools/storyboard-v2/src/components/BgPollCoordinator.tsx"

fail() { echo "[operator-session-perf] FATAL: $1" >&2; exit 1; }

echo "[operator-session-perf] pass 1/3 — cold-boot budget"
grep -q 'DEFAULT_WAIT_SECONDS = 180' "$PROVISION" \
  || fail "provision cold-boot must be 180s (aligned with launchd script)"

echo "[operator-session-perf] pass 2/3 — poll debounce + lazy base clips"
grep -q 'scheduleRefreshBgSession' "$BGSTORE" || fail "bgSessionStore missing debounced refresh"
grep -q 'scheduleRefreshBgSession' "$POLL" || fail "BgPollCoordinator must use debounced refresh"
grep -q 'ensureBaseClipsLoaded' "$PHASE" || fail "PhaseProducer must lazy-load base clips"
grep -q "phase_base_clips_list" "$PHASE" || fail "base clip fetch path missing"
python3 <<PY || fail "refreshAll must not eagerly fetch phase_base_clips_list"
from pathlib import Path
text = Path("$PHASE").read_text()
start = text.index("const refreshAll = async")
chunk = text[start:start + 1800]
if "phase_base_clips_list" in chunk:
    raise SystemExit("refreshAll still eagerly fetches phase_base_clips_list")
PY

echo "[operator-session-perf] pass 3/3 — ambient lazy fetch (phase b only)"
grep -q "phase === 'b'" "$PHASE" || fail "PhaseProducer phase guard missing"
grep -q 'phase_b_ambient_preset_list' "$PHASE" || fail "ambient catalog path missing"

echo "[operator-session-perf] OK"
