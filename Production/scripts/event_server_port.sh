#!/usr/bin/env bash
# Shared port mapping: one event → one dedicated storyboard server port.
#
# Rule (EVENT_DEDICATED_PORT_V1):
#   Event_1 → http://localhost:5111/?event=Event_1
#   Event_2 → http://localhost:5112/?event=Event_2
#   Event_N → port 5110 + N
#
# Source from other scripts:  source "$(dirname "$0")/event_server_port.sh"

event_id_to_port() {
  local event_id="$1"
  local n="${event_id#Event_}"
  if [[ ! "$n" =~ ^[0-9]+$ ]]; then
    echo "FATAL: expected Event_<number>, got ${event_id}" >&2
    return 1
  fi
  echo $((5110 + n))
}

port_to_event_id() {
  local port="$1"
  local n=$((port - 5110))
  if (( n < 1 )); then
    echo "FATAL: port ${port} is below dedicated range (5111+)" >&2
    return 1
  fi
  echo "Event_${n}"
}

event_storyboard_url() {
  local event_id="$1"
  local port
  port="$(event_id_to_port "$event_id")" || return 1
  echo "http://localhost:${port}/?event=${event_id}"
}

# EVENT_SERVER_COLD_BOOT_WAIT_V1 — dedicated Event_N cold start can exceed 90s
# (Event_1 sidecar reconcile ~137s observed; Directus lock, ghost scrub). Shared by
# launchd install, deploy, and event_server_provision.py (keep defaults aligned).
# 2026-07-17: attempts 90→240 — whole-fleet simultaneous cold boot against
# Dropbox observed at ~4-5 min, past the old 180s ceiling (deploy bdceaff6).
: "${EVENT_SERVER_QUICK_HEALTH_ATTEMPTS:=3}"
: "${EVENT_SERVER_COLD_BOOT_ATTEMPTS:=240}"
: "${EVENT_SERVER_WAIT_SLEEP_SECONDS:=2}"
: "${EVENT_SESSION_STATE_CURL_MAX_SECONDS:=180}"

event_server_wait_http() {
  local port="${1:?port required}"
  local attempts="${2:-${EVENT_SERVER_COLD_BOOT_ATTEMPTS}}"
  local sleep_s="${3:-${EVENT_SERVER_WAIT_SLEEP_SECONDS}}"
  local i
  for (( i = 1; i <= attempts; i++ )); do
    if curl -sf --max-time 5 "http://localhost:${port}/api/event/current" >/dev/null 2>&1; then
      return 0
    fi
    if (( i < attempts )); then
      sleep "$sleep_s"
    fi
  done
  return 1
}

event_server_http_serves_event() {
  local port="${1:?port required}"
  local event_id="${2:?event_id required}"
  curl -sf --max-time 5 "http://localhost:${port}/api/event/current" 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('event_id')==sys.argv[1] else 1)" "$event_id" 2>/dev/null
}
