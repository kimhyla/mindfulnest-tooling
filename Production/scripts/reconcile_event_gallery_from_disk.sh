#!/usr/bin/env bash
# Post-deploy one-shot O3 gallery repair for an event (additive, no regen).
set -euo pipefail
EVENT="${1:-Event_2}"
PORT="${2:-5112}"
BASE="http://localhost:${PORT}"
curl -sf "${BASE}/" >/dev/null
curl -sf "${BASE}/api/bg/session-state?scope_event_id=${EVENT}&scope_arc_number=1&scope_video_role=intro&force_reconcile_o3=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('beats', len(d.get('beats') or []), 'ok')"
echo "gallery repair triggered for ${EVENT} on port ${PORT}"
