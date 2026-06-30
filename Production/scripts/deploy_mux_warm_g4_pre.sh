#!/usr/bin/env bash
# deploy_mux_warm_g4_pre.sh — DEPLOY_MUX_WARM_G4_PRE_V1 (RC14 warm-path deploy)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PORT="${MN_SERVER_PORT:-5112}"
BASE="${MN_STORYBOARD_BASE:-http://127.0.0.1:${PORT}}"
MARKER="${REPO_ROOT}/Production/.deploy_mux_warm/Event_2_milestone.ok"

fail() { echo "[deploy-mux-warm-g4-pre] FAIL: $1" >&2; exit 1; }

export PYTHONUNBUFFERED=1

STABLE_NEED=3
wait_stable() {
  local label="$1"
  local ok=0
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if curl -sf "${BASE}/api/event/current" >/dev/null 2>&1; then
      ok=$((ok + 1))
      [[ "$ok" -ge "$STABLE_NEED" ]] && return 0
    else
      ok=0
    fi
    sleep 2
  done
  fail "${label} (${ok}/${STABLE_NEED} consecutive /api/event/current OK)"
}

wait_stable "server not reachable at ${BASE}"

# RC14d (optional) — restart only when MN_MUX_WARM_RESTART=1. Default off after RC14e
# deadlock fix; unconditional restart killed in-flight bootstrap POST (~240s).
if [[ "${MN_MUX_WARM_RESTART:-0}" == "1" ]]; then
  echo "[deploy-mux-warm-g4-pre] restart :${PORT} (RC14d stitch cache lock clear) ..."
  RESTART_OK=0
  for _attempt in 1 2 3 4 5; do
    HTTP="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE}/api/server/restart" || true)"
    if [[ "$HTTP" == "200" ]]; then
      RESTART_OK=1
      break
    fi
    sleep 3
    wait_stable "server not stable before restart retry"
  done
  [[ "$RESTART_OK" -eq 1 ]] || fail "server restart POST failed after retries (last HTTP ${HTTP:-none})"
  wait_stable "server not stable after restart"
  sleep 30
fi

python3 "${SCRIPT_DIR}/deploy_mux_warm_g4_pre.py" \
  --base "${BASE}" \
  --marker "${MARKER}" \
  ${MN_MUX_WARM_FORCE:+--force} \
  || fail "mux warm script failed"

[[ -f "${MARKER}" ]] || fail "marker missing after warm: ${MARKER}"
HASH="$(head -1 "${MARKER}")"
[[ "${#HASH}" -ge 8 ]] || fail "marker hash too short: ${HASH}"

echo "[deploy-mux-warm-g4-pre] OK hash=${HASH:0:12}... marker=${MARKER}"
