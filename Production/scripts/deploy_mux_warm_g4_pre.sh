#!/usr/bin/env bash
# deploy_mux_warm_g4_pre.sh — DEPLOY_MUX_WARM_G4_PRE_V1 (RC14 warm-path deploy)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PORT="${MN_SERVER_PORT:-5112}"
BASE="${MN_STORYBOARD_BASE:-http://127.0.0.1:${PORT}}"
MARKER="${REPO_ROOT}/Production/.deploy_mux_warm/Event_2_milestone.ok"

fail() { echo "[deploy-mux-warm-g4-pre] FAIL: $1" >&2; exit 1; }

curl -sf "${BASE}/api/event/current" >/dev/null || fail "server not reachable at ${BASE}"

python3 "${SCRIPT_DIR}/deploy_mux_warm_g4_pre.py" \
  --base "${BASE}" \
  --marker "${MARKER}" \
  ${MN_MUX_WARM_FORCE:+--force} \
  || fail "mux warm script failed"

[[ -f "${MARKER}" ]] || fail "marker missing after warm: ${MARKER}"
HASH="$(head -1 "${MARKER}")"
[[ "${#HASH}" -ge 8 ]] || fail "marker hash too short: ${HASH}"

echo "[deploy-mux-warm-g4-pre] OK hash=${HASH:0:12}... marker=${MARKER}"
