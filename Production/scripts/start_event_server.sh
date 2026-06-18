#!/usr/bin/env bash
# Start dedicated storyboard server(s) — one event per port (no shared-pin fights).
#
# Port rule: Event_N → localhost:(5110+N)
#   Event_1 → :5111    Event_2 → :5112    Event_4 → :5114
#
# Kim workflow:
#   1. Ask agent (or run):  bash Production/scripts/start_event_server.sh Event_3
#   2. Open bookmark:       http://localhost:5113/?event=Event_3
#   3. Leave that tab on that URL — do not use Event dropdown to switch events.
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
PYTHON="${MN_PYTHON:-${HOME}/.pyenv/versions/3.12.7/bin/python3}"
SERVER="${DROPBOX}/Production/tools/production_server.py"
STORYBOARD="storyboard_v59_prod.html"
STARTUP_WAIT="${MN_SERVER_STARTUP_WAIT:-30}"

if [[ $# -lt 1 ]]; then
  echo "Usage: bash Production/scripts/start_event_server.sh Event_1 [Event_2 ...]" >&2
  echo "Port rule: Event_N → http://localhost:$((5110 + N))/?event=Event_N" >&2
  exit 1
fi

kill_port() {
  lsof -ti:"$1" | xargs kill -9 2>/dev/null || true
}

start_one() {
  local event_id="$1"
  local port
  port="$(event_id_to_port "$event_id")" || exit 1
  local event_dir="${DROPBOX}/Production/${event_id}"
  if [[ ! -d "$event_dir" ]]; then
    echo "FATAL: missing ${event_dir}" >&2
    exit 1
  fi
  local log="${event_dir}/dedicated_server_${port}.log"
  kill_port "$port"
  TOOLS_DIR="$(dirname "$SERVER")"
  LIPSYNC_EXPORTS="$("$PYTHON" "$TOOLS_DIR/lipsync_public_host.py" --shell-export 2>/dev/null || true)"
  if [[ -n "$LIPSYNC_EXPORTS" ]]; then
    eval "$LIPSYNC_EXPORTS"
  fi
  cd "$DROPBOX"
  nohup env PRODUCTION_SERVER_SINGLE_MACHINE=1 MN_EVENT_PIN_IGNORE=1 \
    "$PYTHON" -u "$SERVER" \
    --event-dir "Production/${event_id}" \
    --storyboard "$STORYBOARD" \
    --event-id "$event_id" \
    --port "$port" \
    >> "$log" 2>&1 &
  local code="000"
  local attempt max_attempts
  max_attempts=$(( STARTUP_WAIT / 3 ))
  if (( max_attempts < 5 )); then max_attempts=5; fi
  for attempt in $(seq 1 "$max_attempts"); do
    sleep 3
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${port}/" 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then
      break
    fi
  done
  if [[ "$code" != "200" ]]; then
    echo "FATAL: ${event_id} on :${port} failed (HTTP ${code}) — see ${log}" >&2
    tail -20 "$log" >&2 || true
    exit 1
  fi
  echo "  OK  ${event_id} → $(event_storyboard_url "$event_id")"
}

echo "=== Dedicated event servers (5110+N) ==="
for event_id in "$@"; do
  start_one "$event_id"
done
echo ""
echo "Bookmark each tab to its URL above. Do not flip events via dropdown on dedicated ports."
