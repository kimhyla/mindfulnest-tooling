#!/usr/bin/env bash
# verify_scope_mismatch_auto_heal_durability.sh — SCOPE_MISMATCH_AUTO_HEAL_V1
#
# Incident 2026-06-13: client tab stayed on Event_2 while server pin drifted
# back to Event_1 (server restart / QA durability scripts). BG ref drop → 409
# scope_mismatch banner. Fix: pathappPatch auto-heals via loadEvent + retry.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CLIENT="${REPO_ROOT}/Production/tools/storyboard-v2/src/api/client.ts"
SERVER_PORT="${MN_SERVER_PORT:-5111}"

fail() { echo "[scope-mismatch-auto-heal] FAIL: $1" >&2; exit 1; }

[[ -f "$CLIENT" ]] || fail "missing client.ts"

grep -q 'SCOPE_MISMATCH_AUTO_HEAL_V1' "$CLIENT" \
  || fail "SCOPE_MISMATCH_AUTO_HEAL_V1 marker missing in client.ts"
grep -q 'healServerScopeIfNeeded' "$CLIENT" \
  || fail "healServerScopeIfNeeded missing"
grep -q '_scopeHealRetry' "$CLIENT" \
  || fail "_scopeHealRetry retry flag missing"
grep -q 'suppressScopeDispatch' "$CLIENT" \
  || fail "suppressScopeDispatch missing (snapshot heal must not flash banner)"
grep -q 'READ_SCOPE_HEAL_V1' "$CLIENT" \
  || fail "READ_SCOPE_HEAL_V1 marker missing (apiGet must heal scope on GET 409)"
grep -q 'ensureServerPinnedTo' "$CLIENT" \
  || fail "ensureServerPinnedTo missing (ScopeBoundary pin guard)"

echo "[scope-mismatch-auto-heal] source guards OK"

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

# Pin Event_1 (simulates server drift while client would still be Event_2).
post("/api/event/load", {"event_id": "Event_1"})
_, cur = get("/api/event/current")
if cur.get("event_id") != "Event_1":
    raise SystemExit(f"setup failed: expected Event_1 pin, got {cur!r}")

# BG mutation with Event_2 scope while pinned Event_1 must 409.
try:
    get("/api/v2/event/Event_2/state")
    raise SystemExit("expected 409 for Event_2 v2 state while pinned Event_1")
except urllib.error.HTTPError as e:
    if e.code != 409:
        raise SystemExit(f"expected 409, got HTTP {e.code}") from e
    body = json.loads(e.read().decode())
    if body.get("error_message") != "scope_mismatch":
        raise SystemExit(f"expected scope_mismatch, got {body!r}")

# Auto-heal path (what apiGet / pathappPatch do): load Event_2 then scoped READ succeeds.
post("/api/event/load", {"event_id": "Event_2"})
_, cur2 = get("/api/event/current")
if cur2.get("event_id") != "Event_2":
    raise SystemExit(f"heal load failed: {cur2!r}")

status, _ = get("/api/v2/event/Event_2/state")
if status != 200:
    raise SystemExit(f"post-heal Event_2 v2 state must return 200, got {status}")

print("  live API: 409 on drift pin, 200 v2 state after event/load heal")
PY
  echo "[scope-mismatch-auto-heal] OK — source + live API smoke passed"
else
  echo "[scope-mismatch-auto-heal] OK — source guards passed (server not reachable)"
fi
