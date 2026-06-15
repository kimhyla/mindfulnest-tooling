#!/usr/bin/env bash
# verify_bg_ref_app_context_durability.sh — BG_REF_APP_CONTEXT_V1
#
# Regression: AppContext._library_root_dirs / resolve_library_image_path used
# self.app.event_dir (handler-only) → BG ref library drag returned 500
# "'AppContext' object has no attribute 'app'".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVER="${REPO_ROOT}/Production/tools/production_server.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_app_context_library_roots.py"
BASE="${MN_STORYBOARD_BASE:-http://localhost:${MN_SERVER_PORT:-5111}}"

fail() { echo "[bg-ref-app-context-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$SERVER" ]] || fail "missing production_server.py"
[[ -f "$TEST" ]] || fail "missing test_app_context_library_roots.py"

grep -q 'BG_REF_APP_CONTEXT_V1' "$SERVER" \
  || fail "production_server.py missing BG_REF_APP_CONTEXT_V1 marker on AppContext helpers"

grep -q 'library_image_roots(self.event_dir, self.event_dir.parent)' "$SERVER" \
  || fail "_library_root_dirs must call library_image_roots(self.event_dir, ...)"

grep -q '_resolve(image_key, self.event_dir, self.event_dir.parent)' "$SERVER" \
  || fail "resolve_library_image_path must use self.event_dir (not self.app.event_dir)"

python3 -m pytest "$TEST" -q

if curl -sf "$BASE/api/event/current" >/dev/null 2>&1; then
  PROD_ROOT="${MN_PRODUCTION_ROOT:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}"
  CANON="${PROD_ROOT}/canonical_images/canonical_heartwood_grove_01.png"
  if [[ ! -f "$CANON" ]]; then
    echo "[bg-ref-app-context-durability] WARN: canonical PNG missing at $CANON — skip live BG ref curl"
  else
    curl -sf -X POST "$BASE/api/event/load" \
      -H 'Content-Type: application/json' \
      -d '{"event_id":"Event_2"}' >/dev/null
    RESP=$(curl -sf -X POST "$BASE/api/bg/update-beat" \
      -H 'Content-Type: application/json' \
      -d "{\"beat_id\":\"bg_arc1_event2_pre_beat_01\",\"scope_event_id\":\"Event_2\",\"scope_video_role\":\"intro\",\"bg_ref_image\":{\"key\":\"canonical_heartwood_grove_01\",\"abs_path\":\"$CANON\"}}")
    echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok') is True, d" \
      || fail "live BG ref drop curl did not return ok:true — $RESP"
    echo "[bg-ref-app-context-durability] OK — source guards + pytest + live BG ref curl passed"
  fi
else
  echo "[bg-ref-app-context-durability] OK — source guards + pytest passed (server down; skip live curl)"
fi
