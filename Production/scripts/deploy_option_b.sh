#!/usr/bin/env bash
# deploy_option_b.sh — canonical Option B deploy (STORYBOARD_OPTION_B_SPEC_v1).
#
# Single operator/agent entry point:
#   git commit → bash Production/scripts/deploy_option_b.sh --event Event_2
#
# Never partial-deploy. Never "restart alone". Exit 0 = live proof attached.
#
# Usage:
#   bash Production/scripts/deploy_option_b.sh --event Event_2
#   bash Production/scripts/deploy_option_b.sh   # uses server_event_pin.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=event_server_port.sh
source "${SCRIPT_DIR}/event_server_port.sh"

SRC_TOOLING="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
DEST_DROPBOX="${MN_DROPBOX_ROOT:-${HOME}/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}"

EVENT_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --event)
      EVENT_ARG="Production/${2#Production/}"
      shift 2
      ;;
    --event=*)
      EVENT_ARG="Production/${1#--event=Production/}"
      shift
      ;;
    *)
      echo "FATAL: unknown argument: $1" >&2
      echo "Usage: bash deploy_option_b.sh [--event Event_N]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$EVENT_ARG" ]]; then
  PIN_FILE="$DEST_DROPBOX/Production/server_event_pin.json"
  if [[ -f "$PIN_FILE" ]]; then
    PIN_ID="$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); e=(d.get('event_id') or '').strip(); print(e)" "$PIN_FILE" 2>/dev/null || true)"
    if [[ -n "$PIN_ID" ]]; then
      EVENT_ARG="Production/${PIN_ID}"
      echo "[deploy_option_b] event from pin → $EVENT_ARG"
    fi
  fi
fi
EVENT_ARG="${EVENT_ARG:-Production/Event_1}"
EVENT_ID="$(basename "$EVENT_ARG")"
PORT="$(event_id_to_port "$EVENT_ID")"

export MN_TOOLING_ROOT="$SRC_TOOLING"
export MN_DROPBOX_ROOT="$DEST_DROPBOX"
export MN_EVENT_DIR="$EVENT_ARG"
export MN_SERVER_PORT="$PORT"

echo "=== STORYBOARD_OPTION_B_V1 deploy ==="
echo "  tooling:  $SRC_TOOLING"
echo "  dropbox:  $DEST_DROPBOX"
echo "  event:    $EVENT_ID"
echo "  port:     $PORT"
echo "  url:      $(event_storyboard_url "$EVENT_ID")"
echo ""

bash "$SCRIPT_DIR/deploy_storyboard_v59.sh" --event "$EVENT_ID"

bash "$SCRIPT_DIR/verify_deploy_option_b_live.sh" --event "$EVENT_ID"

echo ""
echo "[deploy_option_b] complete — Option B deploy verified for $EVENT_ID on :$PORT"
