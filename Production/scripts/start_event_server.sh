#!/usr/bin/env bash
# Start dedicated storyboard server(s) — one event per port (no shared-pin fights).
#
# SERVER_LAUNCHD_SINGLE_OWNER_V1 — sync launchd KeepAlive agent; do NOT nohup-spawn
# (dual owner with deploy/KeepAlive caused restart storms on :5112).
#
# EVENT_SERVER_COLD_BOOT_WAIT_V1 — skip port preemption when this event already
# answers on its dedicated port (preempt mid cold boot caused Event_3 death spirals).
#
# Port rule: Event_N → localhost:(5110+N)
#   Event_1 → :5111    Event_2 → :5112    Event_4 → :5114
#
# Kim workflow:
#   1. Ask agent (or run):  bash Production/scripts/start_event_server.sh Event_3
#      On Windows (no launchd): powershell -File Production/scripts/start_event_server.ps1 Event_3
#   2. Open bookmark:       http://localhost:5113/?event=Event_3
#   3. Leave that tab on that URL — do not use Event dropdown to switch events.
#
# Agents: never tell Kim to open a dedicated URL until that port answers
# /api/event/current for the matching event_id (connection refused = server down).
#
# Multiple events (one tab each):
#   bash Production/scripts/start_event_server.sh Event_2 Event_4 Event_1
#
# Status:
#   bash Production/scripts/status_event_servers.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
TOOLING="${MN_TOOLING_ROOT:-${HOME}/Projects/mindfulnest-tooling}"
INSTALL="${TOOLING}/Production/scripts/install_production_server_launchagent.sh"

if [[ ! -f "$INSTALL" ]]; then
  echo "FATAL: missing ${INSTALL}" >&2
  echo "Set MN_TOOLING_ROOT or clone mindfulnest-tooling" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: bash Production/scripts/start_event_server.sh Event_1 [Event_2 ...]" >&2
  echo "Port rule: Event_N → http://localhost:$((5110 + N))/?event=Event_N" >&2
  exit 1
fi

start_one() {
  local event_id="$1"
  local port
  port="$(event_id_to_port "$event_id")" || exit 1
  local event_dir="${DROPBOX}/Production/${event_id}"
  if [[ ! -d "$event_dir" ]]; then
    echo "FATAL: missing ${event_dir}" >&2
    exit 1
  fi
  if event_server_http_serves_event "$port" "$event_id"; then
    echo "[start] ${event_id} already healthy on :${port} — skip port preemption"
  else
    bash "${SCRIPT_DIR}/ensure_server_port.sh" "$port" "$event_id" "$event_dir"
  fi
  MN_TOOLING_ROOT="$TOOLING" MN_DROPBOX_ROOT="$DROPBOX" \
    bash "$INSTALL" "$event_id"
  echo "  OK  ${event_id} → $(event_storyboard_url "$event_id")"
}

echo "=== Dedicated event servers (5110+N) — launchd single owner ==="
for event_id in "$@"; do
  start_one "$event_id"
done
echo ""
echo "Bookmark each tab to its URL above. Do not flip events via dropdown on dedicated ports."
