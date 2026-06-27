#!/usr/bin/env bash
# List dedicated event servers (ports 5111–5199) and storyboard URLs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

echo "Port   Event     HTTP   URL"
for port in $(seq 5111 5119); do
  event_id="$(port_to_event_id "$port" 2>/dev/null)" || continue
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://localhost:${port}/" 2>/dev/null || echo "---")
  if [[ "$code" == "200" ]]; then
    cur=$(curl -s --max-time 2 "http://localhost:${port}/api/event/current" 2>/dev/null \
      | python3 -c "import json,sys; print(json.load(sys.stdin).get('event_id','?'))" 2>/dev/null || echo "?")
    printf "%-6s %-9s %-6s http://localhost:%s/?event=%s  (serving %s)\n" \
      "$port" "$event_id" "$code" "$port" "$event_id" "$cur"
  elif lsof -ti:"$port" >/dev/null 2>&1; then
    listeners=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | wc -l | tr -d ' ')
    dup=""
    if [[ "${listeners:-0}" -gt 1 ]]; then
      dup=" DUPLICATE LISTENERS"
    fi
    printf "%-6s %-9s %-6s (process up, HTTP not ready%s)\n" "$port" "$event_id" "$code" "$dup"
  fi
done
