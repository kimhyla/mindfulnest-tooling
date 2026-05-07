#!/usr/bin/env bash
# Phase 3.3 + G13 — verify the MUTATION_CHANNEL_INVARIANT_V1 grep gate
# (defined in .github/workflows/playwright_e2e.yml) fires on a deliberate
# raw-fetch violation. Mirrors the gate's exclusion logic exactly.
#
# Usage: bash Production/scripts/verify_mutation_channel_invariant_gate.sh
#
# Expected output: "G13 PASS — gate fires on deliberate violation, restores
# on cleanup". Non-zero exit on any deviation.
#
# Per V59 architectural-fix Wave 1 spec §5 Phase 3.3 (deliberate RED-then-GREEN
# proof) + Phase 4 G13 (mandatory enforcement verification gate).

set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/Production/tools/storyboard-v2"

SCRATCH="src/components/_TEMP_grep_gate_test.tsx"
trap 'rm -f "$SCRATCH"' EXIT

# Step 1 — write a scratch component containing a raw fetch to MUTATION_ENDPOINTS.
cat > "$SCRATCH" <<'TS'
// Scratch — G13 grep-gate deliberate-break test artifact (will be auto-removed).
// Should trip MUTATION_CHANNEL_INVARIANT_V1 grep gate.
import { MUTATION_ENDPOINTS } from '../api/endpoints';
export async function tempBreak() {
  const res = await fetch(MUTATION_ENDPOINTS.video_set_active, { method: 'POST' });
  return res;
}
TS

# Step 2 — run the gate's grep1 check. Must produce a match.
matches=$(grep -rnE "fetch\(.*MUTATION_ENDPOINTS\." \
  src/components/ src/state/ src/utils/ 2>/dev/null \
  | grep -vE "(ProjectSelector\.tsx|EventSelector\.tsx|ProductionMapTab\.tsx).*MUTATION_ENDPOINTS\.event_load" \
  || true)
if [ -n "$matches" ]; then
  echo "[gate-with-temp-violation] correctly RED:"
  echo "$matches"
  step1_red=1
else
  echo "[gate-with-temp-violation] FALSE GREEN — gate did not catch the deliberate violation!"
  step1_red=0
fi

# Step 3 — remove scratch.
rm -f "$SCRATCH"

# Step 4 — re-run grep1. Must produce no matches.
matches=$(grep -rnE "fetch\(.*MUTATION_ENDPOINTS\." \
  src/components/ src/state/ src/utils/ 2>/dev/null \
  | grep -vE "(ProjectSelector\.tsx|EventSelector\.tsx|ProductionMapTab\.tsx).*MUTATION_ENDPOINTS\.event_load" \
  || true)
if [ -z "$matches" ]; then
  echo "[gate-without-temp-violation] correctly GREEN"
  step2_green=1
else
  echo "[gate-without-temp-violation] FALSE RED:"
  echo "$matches"
  step2_green=0
fi

# Step 5 — assert both outcomes.
if [ "${step1_red:-0}" -eq 1 ] && [ "${step2_green:-0}" -eq 1 ]; then
  echo "G13 PASS — gate fires on deliberate violation, restores on cleanup"
  exit 0
else
  echo "G13 FAIL — step1_red=${step1_red:-0} step2_green=${step2_green:-0}"
  exit 1
fi
