#!/usr/bin/env bash
# restart_storyboard_fleet.sh — STORYBOARD_FLEET_RESTART_V1
#
# After storyboard bundle fanout, restart (or cold-start) every dedicated Event_N
# server so GET / on :5111–:5116 serves the same fresh storyboard_v59_prod.html.
# Deploying only the target event left Events 1–4 on stale build-sha while Event_5
# was updated — this closes that class permanently.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

ROOT="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"
START="${SCRIPT_DIR}/start_event_server.sh"

FLEET_EVENTS=(Event_1 Event_2 Event_3 Event_4 Event_5 Event_6)
restarted=0
started=0

for event_id in "${FLEET_EVENTS[@]}"; do
  port="$(event_id_to_port "$event_id")" || continue
  event_dir="${DROPBOX}/Production/${event_id}"
  [[ -d "$event_dir" ]] || continue

  if ! event_server_http_serves_event "$port" "$event_id" 2>/dev/null; then
    echo "[fleet-restart] :${port} ${event_id} down — starting via launchd ..."
    MN_TOOLING_ROOT="$ROOT" MN_DROPBOX_ROOT="$DROPBOX" bash "$START" "$event_id"
    started=$((started + 1))
  else
    echo "[fleet-restart] :${port} ${event_id} restarting ..."
    curl -sS -X POST "http://localhost:${port}/api/server/restart" >/dev/null 2>&1 \
      || curl -sS -X POST "http://127.0.0.1:${port}/api/server/restart" >/dev/null 2>&1 \
      || true
    restarted=$((restarted + 1))
  fi
done

echo "[fleet-restart] waiting for fleet cold boot (EVENT_SERVER_COLD_BOOT_WAIT_V1) ..."
fail=0
for event_id in "${FLEET_EVENTS[@]}"; do
  port="$(event_id_to_port "$event_id")" || continue
  [[ -d "${DROPBOX}/Production/${event_id}" ]] || continue
  if ! event_server_wait_http "$port" "${EVENT_SERVER_COLD_BOOT_ATTEMPTS}" "${EVENT_SERVER_WAIT_SLEEP_SECONDS}"; then
    echo "[fleet-restart] FATAL: :${port} ${event_id} did not become healthy" >&2
    fail=1
  else
    echo "[fleet-restart] OK :${port} ${event_id}"
  fi
done
[[ "$fail" -eq 0 ]] || exit 1
echo "[fleet-restart] OK — restarted=${restarted} started=${started}"
