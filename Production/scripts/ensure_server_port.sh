#!/usr/bin/env bash
# PRODUCTION_SERVER_PORT_GUARD_V1 — single entry for port preemption (all launch paths).
#
# Usage:
#   bash Production/scripts/ensure_server_port.sh 5112 Event_2 /path/to/Event_2
#
set -euo pipefail

PORT="${1:?port required}"
EVENT_ID="${2:?event_id required}"
EVENT_DIR="${3:?event_dir required}"
EXCLUDE_PID="${4:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLING="${MN_TOOLING_ROOT:-${HOME}/Projects/mindfulnest-tooling}"
PYTHON="${MN_PYTHON:-${HOME}/.pyenv/versions/3.12.7/bin/python3}"
PROD="${TOOLING}/Production"

export PYTHONPATH="${PROD}${PYTHONPATH:+:${PYTHONPATH}}"

args=(ensure --port "$PORT" --event-id "$EVENT_ID" --event-dir "$EVENT_DIR")
if [[ "$EXCLUDE_PID" != "0" ]]; then
  args+=(--exclude-pid "$EXCLUDE_PID")
fi

exec "$PYTHON" -m lib.server_port_guard "${args[@]}"
