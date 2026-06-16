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
