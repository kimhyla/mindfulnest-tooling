#!/usr/bin/env bash
# verify_production_server_launchagent_durability.sh — EVENT_LAUNCHAGENT_SYNC_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
INSTALL="${REPO_ROOT}/Production/scripts/install_production_server_launchagent.sh"
DEPLOY="${REPO_ROOT}/Production/scripts/deploy_storyboard_v59.sh"

fail() { echo "[launchagent-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$INSTALL" ]] || fail "missing install_production_server_launchagent.sh"
[[ -x "$INSTALL" ]] || fail "install script not executable"

grep -q 'EVENT_LAUNCHAGENT_SYNC_V1' "$INSTALL" \
  || fail "EVENT_LAUNCHAGENT_SYNC_V1 marker missing"
grep -q 'server_event_pin.json' "$INSTALL" \
  || fail "install script must read server_event_pin.json"
grep -q 'install_production_server_launchagent.sh' "$DEPLOY" \
  || fail "deploy_storyboard_v59.sh must call install_production_server_launchagent.sh"

# Deploy smoke must use deployed event_id, not hardcoded Event_1.
grep -q 'scope_event_id=\${event_id}' "$DEPLOY" \
  || fail "deploy step (h) must use scope_event_id=\${event_id}"

echo "[launchagent-durability] OK — launch agent sync script wired into deploy"
