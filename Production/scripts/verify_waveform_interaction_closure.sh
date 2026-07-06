#!/usr/bin/env bash
# verify_waveform_interaction_closure.sh — WAVEFORM_INTERACTION_CLOSURE_V1
#
# Meta-gate: policy unit tests + durability sub-gates + fixture e2e + optional Event_3 live.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${ROOT}/Production/tools/storyboard-v2"
POLICY="${SB}/src/utils/waveformInteractionPolicy.ts"
SPEC="${ROOT}/Production/docs/TECH_SPEC_WAVEFORM_INTERACTION_CLOSURE_v1.md"

fail() { echo "[waveform-interaction-closure] FAIL: $1" >&2; exit 1; }

[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_WAVEFORM_INTERACTION_CLOSURE_v1.md"
[[ -f "$POLICY" ]] || fail "missing waveformInteractionPolicy.ts"

echo "[waveform-interaction-closure] pass 1/5 — spec + policy module"
grep -q 'WAVEFORM_INTERACTION_CLOSURE_V1' "$SPEC" || fail "spec marker missing"
grep -q 'WTA-INV-6' "$SPEC" || fail "spec must document WTA-INV-6 loud reject"

echo "[waveform-interaction-closure] pass 2/5 — sub-gates (phase waveform + interaction platform)"
bash "${SCRIPT_DIR}/verify_phase_waveform_play_durability.sh"
bash "${SCRIPT_DIR}/verify_waveform_time_authority.sh"

echo "[waveform-interaction-closure] pass 3/5 — build dist + fixture fanout"
(
  cd "$SB"
  npm run build --silent
) || fail "storyboard-v2 npm run build failed"
FIXTURE_HTML="${ROOT}/Production/Event_e2e_fixture/storyboard_v59_prod.html"
cp "${SB}/dist/index.html" "$FIXTURE_HTML" || fail "fixture storyboard fanout failed"

echo "[waveform-interaction-closure] pass 4/5 — vitest (interaction policy)"
(
  cd "$SB"
  node --experimental-strip-types --test src/utils/__tests__/waveformInteractionPolicy.test.ts
) || fail "waveformInteractionPolicy vitest failed"

echo "[waveform-interaction-closure] pass 5/5 — fixture e2e (drop reject + stem drag + drop)"
(
  cd "$SB"
  npx playwright test e2e/phase_waveform_playback.spec.ts \
    -g "DROP-REJECT-1|DROP-WC-2|SEEK-DRAG-B-STEM-1|REMOUNT-STEM-2"
) || fail "fixture waveform interaction e2e failed"

if curl -sf --max-time 5 "http://localhost:5113/api/event/current" >/dev/null 2>&1; then
  echo "[waveform-interaction-closure] pass 6/6 — live Event_3 operator path"
  (
    cd "$SB"
    STORYBOARD_LIVE_BASE_URL=http://localhost:5113 \
      npx playwright test --config playwright.live.config.ts \
      e2e/phase_g_interaction_live.spec.ts \
      -g "DROP-WC-LIVE-1|SEEK-DRAG-B-STEM-LIVE-1"
  ) || fail "Event_3 live interaction proof failed"
else
  echo "[waveform-interaction-closure] WARN pass 6/6 skipped — :5113 down (start Event_3 for live proof)"
fi

echo "[waveform-interaction-closure] OK — WAVEFORM_INTERACTION_CLOSURE_V1"
