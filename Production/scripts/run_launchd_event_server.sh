#!/usr/bin/env bash
# run_launchd_event_server.sh — stagger dedicated Event LaunchAgents on login.
#
# EVENT_SERVER_BOOT_STAGGER_V1 — Dropbox File Provider returns errno 11 when all
# Event_1..N KeepAlive agents cold-boot at once. Sleep first, then exec Python.
#
# Usage (from launchd ProgramArguments):
#   bash run_launchd_event_server.sh <stagger_seconds> <python> <server.py> [args...]
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <stagger_seconds> <python> <server.py> [args...]" >&2
  exit 2
fi

STAGGER_S="${1}"
shift
case "$STAGGER_S" in
  ''|*[!0-9]*)
    echo "FATAL: stagger_seconds must be a non-negative integer (got: ${STAGGER_S})" >&2
    exit 2
    ;;
esac

if [[ "$STAGGER_S" -gt 0 ]]; then
  echo "[launchd-stagger] sleeping ${STAGGER_S}s before cold boot (EVENT_SERVER_BOOT_STAGGER_V1)"
  sleep "$STAGGER_S"
fi

exec "$@"
