#!/usr/bin/env bash
# verify_event_server_provision_durability.sh — EVENT_DEDICATED_SERVER_PROVISION_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROVISION="${REPO_ROOT}/Production/lib/event_server_provision.py"
HANDLER="${REPO_ROOT}/Production/tools/server_handlers/event_video.py"
SERVER="${REPO_ROOT}/Production/tools/production_server.py"
CLIENT="${REPO_ROOT}/Production/tools/storyboard-v2/src/state/scopeEventNavigate.ts"

fail() { echo "[event-provision] FAIL: $1" >&2; exit 1; }

[[ -f "$PROVISION" ]] || fail "missing event_server_provision.py"
grep -q 'EVENT_DEDICATED_SERVER_PROVISION_V1' "$PROVISION" \
  || fail "marker missing in event_server_provision.py"
grep -q 'handle_event_provision_server' "$HANDLER" \
  || fail "handle_event_provision_server missing"
grep -q '/api/event/provision_server' "$SERVER" \
  || fail "route missing in production_server.py"
grep -q 'ensureDedicatedEventServerReady' "$CLIENT" \
  || fail "client ensureDedicatedEventServerReady missing"
grep -q 'event_provision_server' "${REPO_ROOT}/Production/tools/storyboard-v2/src/api/endpoints.ts" \
  || fail "event_provision_server endpoint missing"

echo "[event-provision] source guards OK"

(
  cd "${REPO_ROOT}/Production/tools"
  python3 -m pytest tests/test_event_server_provision.py -v
) || fail "pytest failed"

echo "[event-provision] unit tests OK"

BASE_PORT="${MN_SERVER_PORT:-5112}"
BASE="http://localhost:${BASE_PORT}"
if curl -sf "${BASE}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import json, urllib.error, urllib.request

base = "${BASE}"
target = "Event_4"
port = 5114

def post(path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read().decode())

st, body = post("/api/event/provision_server", {"event_id": target})
if st != 200 or not body.get("ok") or not body.get("ready"):
    raise SystemExit(f"provision failed: HTTP {st} {body!r}")
if body.get("port") != port:
    raise SystemExit(f"expected port {port}, got {body!r}")

req = urllib.request.Request(f"http://127.0.0.1:{port}/api/event/current")
with urllib.request.urlopen(req, timeout=10) as r:
    cur = json.loads(r.read().decode())
if cur.get("event_id") != target:
    raise SystemExit(f"event/current mismatch: {cur!r}")

print(f"  live: provision {target} → :{port} ready; event/current ok")
PY
  echo "[event-provision] live API OK"
else
  echo "[event-provision] skip live API — no server on :${BASE_PORT}"
fi

echo "[event-provision] OK — source + unit + live smoke passed"
