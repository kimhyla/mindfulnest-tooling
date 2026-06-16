#!/usr/bin/env bash
# Convenience wrapper — starts two dedicated servers using the global port rule.
#
# DISABLED by default (SINGLE_SERVER_V1): production_server binds :5111 only.
# Dual-event requires MN_DUAL_EVENT_SERVERS=1 AND future --port support in Python.
#
# Default when enabled: Event_2 (:5112) + Event_4 (:5114)
# Override: MN_EVENT_A=Event_1 MN_EVENT_B=Event_3 bash ...
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${MN_DUAL_EVENT_SERVERS:-0}" != "1" ]]; then
  echo "FATAL: dual-event servers are off. Use http://localhost:5111/?event=Event_N" >&2
  echo "  (set MN_DUAL_EVENT_SERVERS=1 only after production_server --port ships)" >&2
  exit 1
fi
EVENT_A="${MN_EVENT_A:-Event_2}"
EVENT_B="${MN_EVENT_B:-Event_4}"
exec bash "${SCRIPT_DIR}/start_event_server.sh" "$EVENT_A" "$EVENT_B"
