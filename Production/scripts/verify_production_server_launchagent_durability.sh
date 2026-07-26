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
grep -q 'LD-505_TOOLING_CODE_ROOT_V1' "$INSTALL" \
  || fail "install script must use tooling code root (LD-505)"
grep -q 'MN_TOOLING_ROOT' "$INSTALL" \
  || fail "install script must set MN_TOOLING_ROOT in launchd env"
grep -q 'production-server-\${EVENT_SLUG}' "$INSTALL" \
  || fail "install script must use event-specific launchd label (one agent per port)"
grep -q 'LEGACY_LABEL' "$INSTALL" \
  || fail "install script must disable legacy generic com.mindfulnest.production-server agent"
grep -q 'MN_LAUNCHD_MANAGED' "$INSTALL" \
  || fail "install script must set MN_LAUNCHD_MANAGED=1 on launchd agent"
grep -q 'EVENT_SERVER_COLD_BOOT_WAIT_V1' "$INSTALL" \
  || fail "install script must document EVENT_SERVER_COLD_BOOT_WAIT_V1"
grep -q 'EVENT_SERVER_BOOT_STAGGER_V1' "$INSTALL" \
  || fail "install script must document EVENT_SERVER_BOOT_STAGGER_V1"
grep -q 'run_launchd_event_server.sh' "$INSTALL" \
  || fail "install script must wrap ProgramArguments with run_launchd_event_server.sh"
WRAPPER="${REPO_ROOT}/Production/scripts/run_launchd_event_server.sh"
[[ -f "$WRAPPER" ]] || fail "missing run_launchd_event_server.sh"
grep -q 'EVENT_SERVER_BOOT_STAGGER_V1' "$WRAPPER" \
  || fail "stagger wrapper must document EVENT_SERVER_BOOT_STAGGER_V1"
grep -q 'kickstart_agent_soft' "$INSTALL" \
  || fail "install script must soft-kickstart before hard -k on cold boot"
grep -q 'EVENT_SERVER_COLD_BOOT_WAIT_V1' "${REPO_ROOT}/Production/scripts/event_server_port.sh" \
  || fail "event_server_port.sh must define EVENT_SERVER_COLD_BOOT_WAIT_V1 wait helpers"

START="${REPO_ROOT}/Production/scripts/start_event_server.sh"
grep -q 'event_server_http_serves_event' "$START" \
  || fail "start_event_server.sh must skip port preemption when event already healthy"

OPTION_B="${REPO_ROOT}/Production/scripts/deploy_option_b.sh"
grep -q 'MN_EVENT_DIR="${DEST_DROPBOX}/Production/${EVENT_ID}"' "$OPTION_B" \
  || fail "deploy_option_b.sh must export absolute MN_EVENT_DIR"

grep -q 'SERVER_LAUNCHD_SINGLE_OWNER_V1' "$INSTALL" \
  || fail "install script must document SERVER_LAUNCHD_SINGLE_OWNER_V1"
grep -q 'plist unchanged' "$INSTALL" \
  || fail "install script must skip reload when plist unchanged (idempotent)"
grep -q 'SERVER_LAUNCHD_SINGLE_OWNER_V1' "$DEPLOY" \
  || fail "deploy must use launchd-only start (SERVER_LAUNCHD_SINGLE_OWNER_V1)"
grep -q 'STORYBOARD_FLEET_RESTART_V1' "$DEPLOY" \
  || fail "deploy must restart all dedicated Event_N servers after fanout (STORYBOARD_FLEET_RESTART_V1)"
grep -q 'restart_storyboard_fleet.sh' "$DEPLOY" \
  || fail "deploy must call restart_storyboard_fleet.sh"
grep -q 'STORYBOARD_FLEET_BUNDLE_PARITY_V1' "$DEPLOY" \
  || fail "deploy must verify fleet bundle parity (STORYBOARD_FLEET_BUNDLE_PARITY_V1)"
grep -q 'verify_storyboard_fleet_bundle_parity.sh' "$DEPLOY" \
  || fail "deploy must call verify_storyboard_fleet_bundle_parity.sh"
grep -q 'nohup env PRODUCTION_SERVER_SINGLE_MACHINE' "$DEPLOY" \
  && fail "deploy must not nohup-spawn production_server (dual owner restart storm)"

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

grep -q 'MN_BEATGEN_DB_PATH' "$INSTALL" \
  || fail "install script must set MN_BEATGEN_DB_PATH per Event_N (BEATGEN_PER_EVENT_SQLITE_V1)"

echo "[launchagent-durability] OK — launch agent sync script wired into deploy"
