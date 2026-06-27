#!/usr/bin/env bash
# dedicated_port_env.sh — STITCH_GUARD_PORT_TOPOLOGY_V1 / EVENT_DEDICATED_PORT_V1
#
# Shared helpers for live-smoke scripts on dedicated storyboard ports.
# Source:  source "$(dirname "$0")/dedicated_port_env.sh"
#
# Rule: port 511N serves Event_N only. Cross-event event/load → 409 DEDICATED_PORT_PIN_IMMUTABLE.

dedicated_event_for_port() {
  local port="$1"
  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    echo "FATAL: expected numeric port, got ${port}" >&2
    return 1
  fi
  if (( port < 5111 )); then
    return 1
  fi
  echo "Event_$((port - 5110))"
}

is_dedicated_storyboard_port() {
  local port="$1"
  [[ "$port" =~ ^[0-9]+$ ]] && (( port >= 5111 ))
}

# MN_SERVER_PORT default 5111; returns pinned event id or empty for non-dedicated.
resolve_live_smoke_event_id() {
  local port="${MN_SERVER_PORT:-5111}"
  if is_dedicated_storyboard_port "$port"; then
    dedicated_event_for_port "$port"
  fi
}
