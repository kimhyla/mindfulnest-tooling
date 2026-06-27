#!/usr/bin/env bash
# verify_scope_restart_reconcile_durability.sh — SCOPE_RESTART_RECONCILE_V1
#
# Category package: restart scope reconcile, dedicated-port retry, fail-closed
# snapshot, deduped scope UI, server 503 until scope_ready.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
SERVER_PORT="${MN_SERVER_PORT:-5111}"

fail() { echo "[scope-restart-reconcile] FAIL: $1" >&2; exit 1; }

cd "${TOOLS}"
python3 -m pytest tests/test_scope_restart_reconcile_contract.py -v \
  || fail "pytest contract tests failed"

CLIENT="${TOOLS}/storyboard-v2/src/api/client.ts"
RECONCILE="${TOOLS}/storyboard-v2/src/state/scopeReconcile.ts"
EVENT_CURRENT="${TOOLS}/storyboard-v2/src/state/scopeEventCurrent.ts"
ERROR_BOUNDARY="${TOOLS}/storyboard-v2/src/api/errorBoundary.ts"
SERVER="${TOOLS}/production_server.py"
EVENT_VIDEO="${TOOLS}/server_handlers/event_video.py"

for f in "$CLIENT" "$RECONCILE" "$EVENT_CURRENT" "$ERROR_BOUNDARY" "$SERVER" "$EVENT_VIDEO"; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'SCOPE_SNAPSHOT_FAIL_CLOSED_V1' "$CLIENT" \
  || fail "fail-closed snapshot marker missing"
grep -q 'fetchEventCurrentWithRetry' "$CLIENT" \
  || fail "dedicated-port retry missing in client.ts"
grep -q 'reconcileScopeAfterRestart' "$RECONCILE" \
  || fail "reconcileScopeAfterRestart missing"
grep -q 'SCOPE_ERROR_DEDUPE_V1' "$ERROR_BOUNDARY" \
  || fail "scope error dedupe missing"
grep -q 'self.scope_ready' "$SERVER" \
  || fail "app.scope_ready missing in production_server.py"
grep -q 'SCOPE_NOT_READY' "$EVENT_VIDEO" \
  || fail "SCOPE_NOT_READY missing in event_video.py"

echo "[scope-restart-reconcile] source guards OK"

if curl -sf "http://localhost:${SERVER_PORT}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import json, urllib.request

base = "http://localhost:${SERVER_PORT}"
with urllib.request.urlopen(base + "/api/event/current", timeout=30) as r:
    body = json.loads(r.read().decode())
    if r.status != 200:
        raise SystemExit(f"expected 200 when scope_ready, got {r.status}")
    if not body.get("ok"):
        raise SystemExit(f"expected ok:true, got {body!r}")
    if not body.get("event_id"):
        raise SystemExit(f"expected event_id on running server, got {body!r}")
print("  live API: event/current 200 with event_id when server up")
PY
  echo "[scope-restart-reconcile] OK — pytest + source + live API smoke passed"
else
  echo "[scope-restart-reconcile] OK — pytest + source guards passed (server not reachable)"
fi
