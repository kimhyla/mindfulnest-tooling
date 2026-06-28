#!/usr/bin/env bash
# verify_scope_client_authority_durability.sh — SCOPE_CLIENT_AUTHORITY_V1 + BUILD_SHA_DRIFT_V1
#
# Category fix for library drop scope_mismatch on dedicated port with stale activeScope
# and stale JS bundle after deploy. See Production/docs/SCOPE_CLIENT_AUTHORITY_SPEC_v1.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${REPO_ROOT}/Production/tools/storyboard-v2"
CLIENT="${SB}/src/api/client.ts"
RESOLVER="${SB}/src/state/resolveAuthoritativeClientScope.ts"
DRIFT="${SB}/src/state/buildShaDrift.ts"
AUTH="${SB}/src/state/scopeAuthority.ts"
SERVER_PORT="${MN_SERVER_PORT:-5112}"

fail() { echo "[scope-client-authority] FAIL: $1" >&2; exit 1; }

[[ -f "$CLIENT" ]] || fail "missing client.ts"
[[ -f "$RESOLVER" ]] || fail "missing resolveAuthoritativeClientScope.ts"
[[ -f "$DRIFT" ]] || fail "missing buildShaDrift.ts"
[[ -f "$AUTH" ]] || fail "missing scopeAuthority.ts"

grep -q 'SCOPE_CLIENT_AUTHORITY_V1' "$CLIENT" \
  || fail "SCOPE_CLIENT_AUTHORITY_V1 marker missing in client.ts"
grep -q 'BUILD_SHA_DRIFT_V1' "$CLIENT" \
  || fail "BUILD_SHA_DRIFT_V1 marker missing in client.ts"
grep -q 'syncAuthoritativeClientScope' "$CLIENT" \
  || fail "syncAuthoritativeClientScope not wired in client.ts"
grep -q 'readDedicatedPortEventId' "$AUTH" \
  || fail "readDedicatedPortEventId missing in scopeAuthority.ts"
grep -q 'readAuthoritativeEventId' "$RESOLVER" \
  || fail "readAuthoritativeEventId missing in resolver"
grep -q 'checkBuildShaDrift' "$DRIFT" \
  || fail "checkBuildShaDrift missing in buildShaDrift.ts"
grep -q 'initBundledBuildSha' "${SB}/src/app.tsx" \
  || fail "initBundledBuildSha not wired in app.tsx"
grep -q 'checkBuildShaDrift' "${SB}/src/components/ServerRehydrateWatcher.tsx" \
  || fail "checkBuildShaDrift not wired in ServerRehydrateWatcher.tsx"

grep -q 'shouldInjectMilestoneScope' "${SB}/src/state/scope.ts" \
  || fail "shouldInjectMilestoneScope missing in scope.ts"
grep -q 'PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1' "${SB}/src/components/ProjectSelector.tsx" \
  || fail "PROJECT_SELECTOR_DEDICATED_PORT_NAV_V1 marker missing in ProjectSelector.tsx"
grep -q 'navigateToDedicatedPortEvent' "${SB}/src/state/scopeEventNavigate.ts" \
  || fail "navigateToDedicatedPortEvent missing in scopeEventNavigate.ts"
grep -q 'buildDedicatedPortEventUrl' "${SB}/src/state/scopeAuthorityResolve.ts" \
  || fail "buildDedicatedPortEventUrl missing in scopeAuthorityResolve.ts"
grep -q 'readDedicatedPortEventId' "${SB}/src/state/scopeReconcile.ts" \
  || fail "DEDICATED_PORT_SCOPE_TRUTH: readDedicatedPortEventId missing in scopeReconcile.ts"
grep -q 'readAuthoritativeEventId' "${SB}/src/state/scopeReconcile.ts" \
  || fail "DEDICATED_PORT_SCOPE_TRUTH: readAuthoritativeEventId missing in scopeReconcile.ts"
grep -q 'DEDICATED_PORT_PIN_IMMUTABLE' "${REPO_ROOT}/Production/tools/server_handlers/event_video.py" \
  || fail "DEDICATED_PORT_SCOPE_TRUTH: server event/load guard missing in event_video.py"

echo "[scope-client-authority] source guards OK"

# Node unit tests
(
  cd "$SB"
  node --experimental-strip-types --test \
    src/state/__tests__/resolveAuthoritativeClientScope.test.ts \
    src/state/__tests__/scopeEventNavigate.test.ts \
    src/state/__tests__/buildShaDrift.test.ts \
    src/state/__tests__/resolveMilestonePartition.test.ts \
    src/state/__tests__/scopeInjection.test.ts
) || fail "unit tests failed"

echo "[scope-client-authority] unit tests OK"

if curl -sf "http://localhost:${SERVER_PORT}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import json, urllib.error, urllib.request

base = "http://localhost:${SERVER_PORT}"

def post(path, body):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

def get(path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

_, cur = get("/api/event/current")
event_id = cur.get("event_id")
if not event_id:
    raise SystemExit(f"no event_id on dedicated port server: {cur!r}")

# Correct scope must not 409 on scoped READ.
try:
    status_ok, body_ok = get(
        f"/api/bg/session-state?scope_event_id={event_id}"
        "&scope_milestone_id=milestone1_arc1&scope_type=milestone"
        "&scope_video_role=standalone&scope_arc_number=1&scope_phase=full"
        if cur.get("scope_type") == "milestone"
        else f"/api/bg/session-state?scope_event_id={event_id}&scope_video_role=intro"
    )
except urllib.error.HTTPError as e:
    status_ok = e.code
    body_ok = json.loads(e.read().decode())

if status_ok == 409 and body_ok.get("error_message") == "scope_mismatch":
    raise SystemExit(f"scoped READ 409 with matching scope_event_id: {body_ok!r}")

# Wrong scope must 409 (cross-event v2 state guard).
wrong = "Event_1" if event_id != "Event_1" else "Event_99"
try:
    get(f"/api/v2/event/{wrong}/state")
    raise SystemExit("expected 409 for wrong scope_event_id")
except urllib.error.HTTPError as e:
    if e.code != 409:
        raise SystemExit(f"expected 409, got HTTP {e.code}") from e
    body = json.loads(e.read().decode())
    if body.get("error_message") != "scope_mismatch":
        raise SystemExit(f"expected scope_mismatch, got {body!r}")

# Dedicated port must reject event/load away from CLI pin (409, not silent swap).
wrong = "Event_1" if event_id != "Event_1" else "Event_99"
try:
    post("/api/event/load", {"event_id": wrong})
    raise SystemExit(f"expected 409 for event/load to {wrong} on dedicated port")
except urllib.error.HTTPError as e:
    if e.code != 409:
        raise SystemExit(f"expected 409 for event/load drift, got HTTP {e.code}") from e
    body = json.loads(e.read().decode())
    if body.get("error_code") != "DEDICATED_PORT_PIN_IMMUTABLE":
        raise SystemExit(f"expected DEDICATED_PORT_PIN_IMMUTABLE, got {body!r}")

print(f"  live API on :${SERVER_PORT}: event={event_id} scoped mutate not 409; wrong scope 409; event/load drift blocked")
PY
  echo "[scope-client-authority] OK — source + unit + live API smoke passed"
else
  echo "[scope-client-authority] OK — source + unit passed (server :${SERVER_PORT} not reachable)"
fi
