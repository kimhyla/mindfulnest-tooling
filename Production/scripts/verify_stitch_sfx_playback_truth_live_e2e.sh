#!/usr/bin/env bash
# verify_stitch_sfx_playback_truth_live_e2e.sh — post-deploy live milestone Playwright
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${REPO_ROOT}/Production/tools/storyboard-v2"
PORT="${MN_SERVER_PORT:-5112}"
BASE="${MN_STORYBOARD_BASE:-http://127.0.0.1:${PORT}}"

fail() { echo "[stitch-sfx-playback-truth-live] FAIL: $1" >&2; exit 1; }

if ! curl -sf "${BASE}/api/event/current" >/dev/null 2>&1; then
  echo "[stitch-sfx-playback-truth-live] SKIP — server :${PORT} not reachable"
  exit 0
fi

bash "${SCRIPT_DIR}/ensure_storyboard_playwright_browsers.sh"

# STITCH_LIVE_E2E_SERVER_STABLE_V1 — HTTP 200 on load_job is NOT readiness (ephemeral
# milestone jobs return 200 + empty standalone when jobs{}). Require N consecutive
# /api/event/current OK + matching build-sha before Playwright (post-restart race).
STABLE_NEED=3
STABLE_OK=0
for _warm in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if curl -sf "${BASE}/api/event/current" >/dev/null 2>&1; then
    STABLE_OK=$((STABLE_OK + 1))
    if [[ "$STABLE_OK" -ge "$STABLE_NEED" ]]; then
      break
    fi
  else
    STABLE_OK=0
  fi
  sleep 2
done
if [[ "$STABLE_OK" -lt "$STABLE_NEED" ]]; then
  fail "server not stable after launchd restart (${STABLE_OK}/${STABLE_NEED} consecutive /api/event/current OK)"
fi
sleep 1

SHA="$(curl -sf "${BASE}/" | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p' | head -1)"
HEAD="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
if [[ -n "$SHA" && -n "$HEAD" && "$SHA" != "$HEAD" ]]; then
  fail "build-sha mismatch before live E2E: served=${SHA} git=${HEAD}"
fi

# STITCH_LIVE_E2E_EVENT_WARM_V1 — drain Event_2 load_job auto-bake before milestone GETs (TECH_SPEC_STITCH_LIVE_E2E_MILESTONE_V1).
echo "[stitch-sfx-playback-truth-live] warming Event_2_stitch load_job (may bake once)..."
if ! curl -sf --max-time 300 "${BASE}/api/stitch_editor/job/Event_2_stitch" >/dev/null; then
  fail "Event_2 load_job warmup failed — server may still be baking"
fi

echo "[stitch-sfx-playback-truth-live] g4-pre mux warm (DEPLOY_MUX_WARM_G4_PRE_V1) ..."
bash "${SCRIPT_DIR}/deploy_mux_warm_g4_pre.sh" || fail "deploy_mux_warm_g4_pre failed"

(
  cd "$SB"
  STORYBOARD_LIVE_BASE_URL="$BASE" npx playwright test --config playwright.live.config.ts
) || fail "live Playwright E2E failed"

echo "[stitch-sfx-playback-truth-live] OK — live Playwright passed (build-sha=${SHA:-?})"
