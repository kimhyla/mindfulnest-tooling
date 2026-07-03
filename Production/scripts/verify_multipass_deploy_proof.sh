#!/usr/bin/env bash
# CROSS_PIPELINE_G1_G8_CLOSURE_V1 — post-deploy multipass proof block.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS="$ROOT/Production/scripts"
SB="$ROOT/Production/tools/storyboard-v2"
PORT="${MN_LIVE_PORT:-5114}"
BASE="http://localhost:${PORT}"
PASS="${1:-1}"

echo "=== MULTIPASS PROOF pass ${PASS}/2 ==="
HEAD="$(git -C "$ROOT" rev-parse --short HEAD)"
SERVED="$(curl -sf "${BASE}/" | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p' | head -1)"
[[ -n "$SERVED" ]] || { echo "FAIL pass ${PASS}: no build-sha from :${PORT}"; exit 1; }
[[ "$SERVED" == "$HEAD" ]] || { echo "FAIL pass ${PASS}: build-sha mismatch served=${SERVED} git=${HEAD}"; exit 1; }
echo "  OK  build-sha parity ${SERVED}"

curl -sf "${BASE}/api/event/current" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d.get('event_id') == 'Event_4', d
print('  OK  event_id=Event_4')
"

bash "$SCRIPTS/verify_cross_pipeline_g1_g8_closure_durability.sh"
echo "  OK  verify_cross_pipeline_g1_g8_closure_durability"

(
  cd "$SB"
  npx playwright test \
    e2e/o3_failed_redo_restores_prior_clip.spec.ts \
    e2e/o3_restart_survival.spec.ts \
    e2e/library_scope_parity.spec.ts \
    e2e/directus_has_crop_disk_fallback.spec.ts \
    e2e/library_cache_coherence.spec.ts \
    e2e/trim_then_export_shows_new_clip.spec.ts
)
echo "  OK  pass 6b e2e (6 files)"

echo "=== MULTIPASS pass ${PASS}/2 COMPLETE ==="
