#!/usr/bin/env bash
# verify_scope_poll_adopt_durability.sh — SCOPE_POLL_ADOPT_V1
#
# Incident 2026-06-15: ServerRehydrateWatcher syncScopeFromProbe called loadEvent
# on every poll when client/server event_id differed. Two tabs (Event_1 + Event_2)
# ping-ponged event/load → scope_mismatch + Failed to fetch on O3 clip select.
# Fix: polls adopt server pin when tab has no URL/explicit override; never event/load
# from poll when URL/explicit pin overrides server (SCOPE_POLL_NO_HEAL_V2 — two-tab ping-pong).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REHYDRATE="${REPO_ROOT}/Production/tools/storyboard-v2/src/state/serverRehydrate.ts"
AUTHORITY="${REPO_ROOT}/Production/tools/storyboard-v2/src/state/scopeAuthority.ts"
CLIENT="${REPO_ROOT}/Production/tools/storyboard-v2/src/api/client.ts"

fail() { echo "[scope-poll-adopt] FAIL: $1" >&2; exit 1; }

[[ -f "$REHYDRATE" ]] || fail "missing serverRehydrate.ts"
[[ -f "$AUTHORITY" ]] || fail "missing scopeAuthority.ts"
[[ -f "$CLIENT" ]] || fail "missing client.ts"

grep -q 'SCOPE_POLL_ADOPT_V1' "$REHYDRATE" \
  || fail "SCOPE_POLL_ADOPT_V1 marker missing in serverRehydrate.ts"
grep -q 'server-rehydrate-adopt-server-pin' "$REHYDRATE" \
  || fail "adopt-server-pin source missing"
! grep -q 'loadEvent(cur.event_id)' "$REHYDRATE" \
  || fail "serverRehydrate must not loadEvent from poll (ping-pong regression)"

grep -q 'SCOPE_PIN_AUTHORITY_V1' "$AUTHORITY" \
  || fail "SCOPE_PIN_AUTHORITY_V1 marker missing"
grep -q 'clientMayPinServerTo' "$AUTHORITY" \
  || fail "clientMayPinServerTo missing"
grep -q 'clientMayPinServerTo(scope.event_id)' "$CLIENT" \
  || fail "healServerScopeIfAuthorized must gate loadEvent on clientMayPinServerTo"
grep -q 'SCOPE_POLL_NO_HEAL_V2' "$REHYDRATE" \
  || fail "SCOPE_POLL_NO_HEAL_V2 marker missing in serverRehydrate.ts"
! grep -q 'healServerScopeIfAuthorized' "$REHYDRATE" \
  || fail "syncScopeFromProbe must not heal from poll (ping-pong regression)"
grep -q 'clientScopeOverridesServerPin' "$REHYDRATE" \
  || fail "syncScopeFromProbe must skip adopt when URL/explicit pin overrides server"
grep -q 'clientScopeOverridesServerPin' "$AUTHORITY" \
  || fail "clientScopeOverridesServerPin missing in scopeAuthority.ts"
grep -q 'eventIdToDedicatedPort' "$AUTHORITY" \
  || fail "eventIdToDedicatedPort missing (EVENT_DEDICATED_PORT_V1)"
grep -q 'isDedicatedPortForEvent' "$CLIENT" \
  || fail "healServerScopeIfAuthorized must gate dedicated-port tabs"

echo "[scope-poll-adopt] OK — poll adopt + pin authority guards present"
