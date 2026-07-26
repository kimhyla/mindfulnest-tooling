#!/usr/bin/env bash
# vacation_pc_mac_undo.sh — Mac return: reload Event_1..7 LaunchAgents after PC week.
# Staggers bootstrap (one Event at a time) so Dropbox File Provider does not
# return errno 11 under concurrent cold-boot.
#
#   bash Production/scripts/vacation_pc_mac_undo.sh --dry-run
#   bash Production/scripts/vacation_pc_mac_undo.sh --force
#
# Canonical copy also mirrored to ~/.mindfulnest/vacation/mac_undo.sh.
set -euo pipefail

DRY_RUN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"
PORTS=(5111 5112 5113 5114 5115 5116 5117)

echo "=== vacation mac_undo === domain=$DOMAIN dry_run=$DRY_RUN"
echo "Prerequisite: PC production_server stopped; Dropbox idle on both machines."

missing=0
for n in 1 2 3 4 5 6 7; do
  label="com.mindfulnest.production-server-event${n}"
  plist="${HOME}/Library/LaunchAgents/${label}.plist"
  if [[ -f "$plist" ]]; then
    echo "  OK  $plist"
  else
    echo "  MISSING $plist"; missing=1
  fi
done
[[ "$missing" -eq 0 ]] || { echo "FATAL: missing plists — do not invent new agents" >&2; exit 1; }

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY-RUN: would stagger-bootstrap event1..7, wait per port, curl event/current."
  exit 0
fi
if [[ "$FORCE" -ne 1 ]]; then
  echo "Refusing without --force."
  exit 2
fi

for n in 1 2 3 4 5 6 7; do
  label="com.mindfulnest.production-server-event${n}"
  launchctl bootout "${DOMAIN}/${label}" 2>/dev/null || true
done
sleep 3

fail=0
for n in 1 2 3 4 5 6 7; do
  label="com.mindfulnest.production-server-event${n}"
  plist="${HOME}/Library/LaunchAgents/${label}.plist"
  port=$((5110 + n))
  if launchctl bootstrap "${DOMAIN}" "$plist" 2>/dev/null; then
    echo "  bootstrap ${label}"
  elif launchctl load "$plist" 2>/dev/null; then
    echo "  load ${label}"
  else
    echo "  FAIL ${label}" >&2
    fail=1
    continue
  fi
  ok=0
  for _i in $(seq 1 40); do
    if out="$(curl -sf --max-time 2 "http://127.0.0.1:${port}/api/event/current" 2>/dev/null)"; then
      eid="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin).get('event_id','?'))" 2>/dev/null || echo '?')"
      echo "  OK   :${port} event_id=${eid}"
      ok=1
      break
    fi
    sleep 3
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "  FAIL :${port} never answered" >&2
    fail=1
  fi
  sleep 2
done

echo "--- final smoke ---"
for p in "${PORTS[@]}"; do
  if out="$(curl -sf --max-time 5 "http://127.0.0.1:${p}/api/event/current" 2>/dev/null)"; then
    eid="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin).get('event_id','?'))" 2>/dev/null || echo '?')"
    echo "  OK   :${p} event_id=${eid}"
  else
    echo "  FAIL :${p}"; fail=1
  fi
done
[[ "$fail" -eq 0 ]] || { echo "UNDO incomplete — check launchctl / logs" >&2; exit 1; }
echo "UNDO complete. Mac fleet is sole writer again."
