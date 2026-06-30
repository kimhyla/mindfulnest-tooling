#!/usr/bin/env bash
# verify_live_fleet_interaction.sh — LIVE_FLEET_PROOF_V1 (G2 / RC11)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPTS="$ROOT/Production/scripts"
SB="$ROOT/Production/tools/storyboard-v2"
HEAD="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"

fail() { echo "[live-fleet-interaction] FATAL: $1" >&2; exit 1; }

[[ -f "$SB/e2e/phase_g_interaction_live.spec.ts" ]] \
  || fail "missing phase_g_interaction_live.spec.ts"

declare -A PORT_EVENT=(
  [5111]=Event_1
  [5112]=Event_2
  [5113]=Event_3
  [5114]=Event_4
  [5115]=Event_5
  [5116]=Event_6
)

LIVE_ANY=0
for port in 5111 5112 5113 5114 5115 5116; do
  event="${PORT_EVENT[$port]}"
  if ! curl -sf "http://localhost:${port}/api/event/current" >/dev/null 2>&1; then
    echo "[live-fleet-interaction] SKIP :${port} (${event}) — server down"
    continue
  fi
  LIVE_ANY=1
  SHA="$(curl -sf "http://localhost:${port}/" | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p' | head -1)"
  if [[ -n "$SHA" && -n "$HEAD" && "$SHA" != "$HEAD" ]]; then
    fail "port ${port} build-sha mismatch: served=${SHA} git=${HEAD}"
  fi
  CUR="$(curl -sf "http://localhost:${port}/api/event/current")"
  echo "[live-fleet-interaction] :${port} ${event} build-sha=${SHA:-?} current=${CUR}"
  WC="$(curl -sf "http://localhost:${port}/api/phase/watercolor_list" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo 0)"
  [[ "${WC}" -ge 1 ]] || fail "${event} on :${port} has zero watercolors — run bootstrap_event_watercolors.py"
done

if [[ "$LIVE_ANY" -eq 0 ]]; then
  echo "[live-fleet-interaction] WARN — no live servers; curl fleet skipped"
  exit 0
fi

if curl -sf "http://localhost:5114/api/event/current" >/dev/null 2>&1; then
  echo "[live-fleet-interaction] Playwright DROP-WC-LIVE-1 on Event_4 :5114 ..."
  (
    cd "$SB"
    STORYBOARD_LIVE_BASE_URL=http://localhost:5114 \
      npx playwright test --config playwright.live.config.ts e2e/phase_g_interaction_live.spec.ts
  ) || fail "phase_g_live_interaction live E2E failed"
fi

echo "[live-fleet-interaction] OK — fleet build-sha + watercolor catalog + live drag proof"
