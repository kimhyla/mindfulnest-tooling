#!/usr/bin/env bash
# verify_event_switch_automation_durability.sh — EVENT_SWITCH_AUTOMATION zero-touch
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SYNC="${ROOT}/Production/lib/event_storyboard_bundle_sync.py"
HANDLER="${ROOT}/Production/tools/server_handlers/event_video.py"
SPEC="${ROOT}/Production/docs/TECH_SPEC_EVENT_SWITCH_AUTOMATION_v1.md"
DRIFT="${ROOT}/Production/tools/storyboard-v2/src/state/buildShaDrift.ts"
WATCHER="${ROOT}/Production/tools/storyboard-v2/src/components/ServerRehydrateWatcher.tsx"
NAV="${ROOT}/Production/tools/storyboard-v2/src/state/scopeEventNavigate.ts"

fail() { echo "[event-switch-auto] FATAL: $1" >&2; exit 1; }

echo "[event-switch-auto] pass 1/4 — spec + sync module"
[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_EVENT_SWITCH_AUTOMATION_v1.md"
grep -q 'EVENT_SWITCH_STORYBOARD_BUNDLE_SYNC_V1' "$SYNC" || fail "sync marker missing"
grep -q 'sync_event_storyboard_bundle' "$HANDLER" || fail "handler must call sync_event_storyboard_bundle"

echo "[event-switch-auto] pass 2/4 — client auto-reload + provision client"
grep -q 'checkBuildShaDriftAndAutoReload' "$DRIFT" || fail "buildShaDrift missing auto reload"
grep -q 'shouldAutoReloadOnBuildShaDrift' "$DRIFT" || fail "webdriver guard missing"
grep -q 'checkBuildShaDriftAndAutoReload' "$WATCHER" || fail "ServerRehydrateWatcher must auto-reload"
grep -q 'ensureDedicatedEventServerReady' "$NAV" || fail "scopeEventNavigate provision missing"

echo "[event-switch-auto] pass 3/4 — pytest bundle sync"
(
  cd "${ROOT}/Production/tools"
  python3 -m pytest tests/test_event_storyboard_bundle_sync.py -q --tb=short
) || fail "bundle sync pytest failed"

echo "[event-switch-auto] pass 4/4 — live provision API smoke (optional)"
BASE_PORT="${MN_SERVER_PORT:-5111}"
BASE="http://localhost:${BASE_PORT}"
if curl -sf "${BASE}/api/event/current" >/dev/null 2>&1; then
  python3 <<PY
import json, urllib.request

base = "${BASE}"
req = urllib.request.Request(
    base + "/api/event/provision_server",
    data=json.dumps({"event_id": "Event_1"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    body = json.loads(resp.read().decode())
assert body.get("ok") is True, body
sync = body.get("storyboard_bundle_sync") or {}
assert sync.get("ok") is True, sync
print("[event-switch-auto] Event_1 provision OK, bundle_sync ok=", sync.get("ok"))
PY
else
  echo "[event-switch-auto] skip live smoke — no server on ${BASE}"
fi

echo "[event-switch-auto] OK"
