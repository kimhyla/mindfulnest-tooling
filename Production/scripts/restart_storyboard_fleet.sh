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

port_listener_pid() {
  # `|| true`: lsof exits 1 when the port has no listener (normal mid cold
  # boot) — must not kill the script under set -euo pipefail.
  lsof -ti "tcp:${1}" -s tcp:LISTEN 2>/dev/null | head -1 || true
}

# FLEET_RESTART_NEW_PID_WAIT_V1 (2026-07-17): /api/server/restart acks and
# exits ASYNCHRONOUSLY — the old process keeps answering /api/event/current
# for a moment after the POST, so a plain health wait can go green against the
# PRE-restart process. The fleet then actually goes down for a multi-minute
# simultaneous cold boot and the next deploy step (curl smoke / parity) probes
# into that window and FATALs. Fix: record the listener pid before the
# restart POST and require BOTH a pid change AND health before declaring OK.
declare -a RESTART_PORTS=()
declare -a RESTART_OLD_PIDS=()

for event_id in "${FLEET_EVENTS[@]}"; do
  port="$(event_id_to_port "$event_id")" || continue
  event_dir="${DROPBOX}/Production/${event_id}"
  [[ -d "$event_dir" ]] || continue

  if ! event_server_http_serves_event "$port" "$event_id" 2>/dev/null; then
    echo "[fleet-restart] :${port} ${event_id} down — starting via launchd ..."
    MN_TOOLING_ROOT="$ROOT" MN_DROPBOX_ROOT="$DROPBOX" bash "$START" "$event_id"
    started=$((started + 1))
  else
    old_pid="$(port_listener_pid "$port")"
    echo "[fleet-restart] :${port} ${event_id} restarting (old pid=${old_pid:-unknown}) ..."
    RESTART_PORTS+=("$port")
    RESTART_OLD_PIDS+=("${old_pid:-0}")
    curl -sS -X POST "http://localhost:${port}/api/server/restart" >/dev/null 2>&1 \
      || curl -sS -X POST "http://127.0.0.1:${port}/api/server/restart" >/dev/null 2>&1 \
      || true
    restarted=$((restarted + 1))
  fi
done

restart_old_pid_for_port() {
  local want="$1" i
  # ${arr[@]+...} guard — empty-array expansion errors under set -u on bash 3.2.
  for i in ${RESTART_PORTS[@]+"${!RESTART_PORTS[@]}"}; do
    if [[ "${RESTART_PORTS[$i]}" == "$want" ]]; then
      echo "${RESTART_OLD_PIDS[$i]}"
      return 0
    fi
  done
  echo "0"
}

echo "[fleet-restart] waiting for fleet cold boot (EVENT_SERVER_COLD_BOOT_WAIT_V1 + FLEET_RESTART_NEW_PID_WAIT_V1) ..."
fail=0
for event_id in "${FLEET_EVENTS[@]}"; do
  port="$(event_id_to_port "$event_id")" || continue
  [[ -d "${DROPBOX}/Production/${event_id}" ]] || continue
  old_pid="$(restart_old_pid_for_port "$port")"
  healthy=1
  for (( i = 1; i <= EVENT_SERVER_COLD_BOOT_ATTEMPTS; i++ )); do
    cur_pid="$(port_listener_pid "$port")"
    if [[ -n "$cur_pid" && "$cur_pid" != "$old_pid" ]] \
      && curl -sf --max-time 5 "http://localhost:${port}/api/event/current" >/dev/null 2>&1; then
      healthy=0
      break
    fi
    if (( i < EVENT_SERVER_COLD_BOOT_ATTEMPTS )); then
      sleep "${EVENT_SERVER_WAIT_SLEEP_SECONDS}"
    fi
  done
  if [[ "$healthy" -ne 0 ]]; then
    echo "[fleet-restart] FATAL: :${port} ${event_id} did not become healthy on a NEW pid (old=${old_pid})" >&2
    fail=1
  else
    echo "[fleet-restart] OK :${port} ${event_id} (pid $(port_listener_pid "$port"))"
  fi
done
[[ "$fail" -eq 0 ]] || exit 1
echo "[fleet-restart] OK — restarted=${restarted} started=${started}"
