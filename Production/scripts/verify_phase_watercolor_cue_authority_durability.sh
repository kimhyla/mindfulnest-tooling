#!/usr/bin/env bash
# verify_phase_watercolor_cue_authority_durability.sh — PHASE_WATERCOLOR_CUE_AUTHORITY_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SB="$ROOT/Production/tools/storyboard-v2/src"
PRODUCER="$SB/components/phase/PhaseProducer.tsx"
AUTH="$SB/utils/phaseWatercolorCuesAuthority.ts"
HOOK="$SB/hooks/usePhaseWatercolorCues.ts"
TEST="$SB/utils/__tests__/phaseWatercolorCuesAuthority.test.ts"

fail() { echo "[phase-watercolor-cue-authority] FATAL: $1" >&2; exit 1; }

echo "[phase-watercolor-cue-authority] pass 1/3 — source contract"
for f in "$PRODUCER" "$AUTH" "$HOOK" "$TEST"; do
  [[ -f "$f" ]] || fail "missing $f"
done
grep -q 'PHASE_WATERCOLOR_CUE_AUTHORITY_V1' "$AUTH" \
  || fail "phaseWatercolorCuesAuthority missing marker"
grep -q 'usePhaseWatercolorCues' "$PRODUCER" \
  || fail "PhaseProducer must use usePhaseWatercolorCues hook"
grep -q 'mergeWatercolorCuesOnHydrate' "$AUTH" \
  || fail "missing mergeWatercolorCuesOnHydrate"
grep -q 'adoptFromEventState' "$HOOK" \
  || fail "hook must expose adoptFromEventState"
if grep -q 'stateSlice\.watercolor_cues' "$PRODUCER"; then
  fail "PhaseProducer must not read stateSlice.watercolor_cues (hook owns cues)"
fi

echo "[phase-watercolor-cue-authority] pass 2/3 — registry row"
grep -q 'phase_watercolor_cue_geometry' "$ROOT/Production/tools/authority_registry.py" \
  || fail "authority_registry missing phase_watercolor_cue_geometry"

echo "[phase-watercolor-cue-authority] pass 3/3 — vitest"
(
  cd "$ROOT/Production/tools/storyboard-v2"
  node --experimental-strip-types --test "$TEST"
) || fail "phaseWatercolorCuesAuthority tests failed"

echo "[phase-watercolor-cue-authority] OK"
