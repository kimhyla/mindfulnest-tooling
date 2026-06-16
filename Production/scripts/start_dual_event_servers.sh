#!/usr/bin/env bash
# Convenience wrapper — starts two dedicated servers using the global port rule.
#
# Default: Event_2 (:5112) + Event_4 (:5114) — one tab per bookmark, no shared pin.
# Override: MN_EVENT_A=Event_1 MN_EVENT_B=Event_3 bash ...
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVENT_A="${MN_EVENT_A:-Event_2}"
EVENT_B="${MN_EVENT_B:-Event_4}"
exec bash "${SCRIPT_DIR}/start_event_server.sh" "$EVENT_A" "$EVENT_B"
