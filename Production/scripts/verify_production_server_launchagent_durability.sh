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

# EVENT_DEDICATED_PORT_V1 — launchd passes --port; Event_N → 5110+N.
grep -q '<string>--port</string>' "$INSTALL" \
  || fail "install script must pass --port for dedicated event servers"
grep -q 'MN_EVENT_PIN_IGNORE' "$INSTALL" \
  || fail "install script must set MN_EVENT_PIN_IGNORE=1 on launchd agent"
grep -q 'lipsync_public_host.py' "$INSTALL" \
  || fail "install script must inject R2 env from lipsync_public_host.py --shell-export"

# event_server_port: Event_2 → :5112 (not shared :5111).
PORT_SH="${REPO_ROOT}/Production/scripts/event_server_port.sh"
[[ -f "$PORT_SH" ]] || fail "missing event_server_port.sh"
(
  # shellcheck source=/dev/null
  source "$PORT_SH"
  p="$(event_id_to_port Event_2)"
  [[ "$p" == "5112" ]] || fail "event_id_to_port Event_2 must be 5112, got ${p}"
  url="$(event_storyboard_url Event_2)"
  [[ "$url" == "http://localhost:5112/?event=Event_2" ]] \
    || fail "event_storyboard_url Event_2 wrong: ${url}"
)

echo "[launchagent-durability] OK — launch agent sync script wired into deploy"
