#!/usr/bin/env bash
# post_tooling_change_smoke.sh — delegates to deploy_option_b (STORYBOARD_OPTION_B_V1).
#
# Legacy name kept for operator rules / docs. Do not duplicate rsync here.
#
# Usage:
#   bash Production/scripts/post_tooling_change_smoke.sh
#   MN_EVENT_ID=Event_2 bash Production/scripts/post_tooling_change_smoke.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVENT_ID="${MN_EVENT_ID:-Event_1}"

echo "=== post_tooling_change_smoke → deploy_option_b (STORYBOARD_OPTION_B_V1) ==="
exec bash "$SCRIPT_DIR/deploy_option_b.sh" --event "$EVENT_ID"
