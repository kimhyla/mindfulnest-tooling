#!/usr/bin/env bash
# verify_kling_stitch_readiness_durability.sh — KLING_STITCH_READINESS_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
MODULE="$TOOLS/kling_stitch_readiness.py"
TS="$TOOLS/storyboard-v2/src/utils/klingStitchReadiness.ts"
BG_TAB="$TOOLS/storyboard-v2/src/components/BgTab.tsx"

fail() { echo "[kling-stitch-readiness-durability] FATAL: $1" >&2; exit 1; }

[[ -f "$MODULE" ]] || fail "missing kling_stitch_readiness.py"
grep -q 'def beat_kling_stitch_export_ready' "$MODULE" || fail "missing beat_kling_stitch_export_ready"
grep -q 'def finalize_kling_delivery_clip' "$MODULE" || fail "missing finalize_kling_delivery_clip"
grep -q 'def sync_kling_stitch_status_from_active_clip' "$MODULE" || fail "missing sync_kling_stitch_status_from_active_clip"

grep -q 'beatKlingStitchExportReady' "$TS" || fail "missing client beatKlingStitchExportReady"
grep -q 'KLING_STITCH_READINESS_V1' "$TS" || fail "missing client contract marker"
grep -q 'data-kling-stitch-readiness-v1' "$BG_TAB" || fail "BgTab missing contract data attribute"

# Structural: O3 beats must not depend on a separate Approve Kling clip button.
if grep -q 'Approve Kling clip' "$BG_TAB"; then
  fail "O3 approve button regressed — readiness is active-clip based"
fi
if grep -q 'onSelectO3Video(b.beat_id, optionKey, { draftOnly: true })' "$BG_TAB"; then
  fail "blanket draftOnly on all beats"
fi

grep -q 'beat_kling_stitch_export_ready' "$TOOLS/beat_generator.py" \
  || fail "beat_has_stitch_export_clip must delegate to contract module"

GUARD="$ROOT/Production/scripts/check_storyboard_critical_features.sh"
grep -q 'KLING_STITCH_READINESS' "$GUARD" || fail "regression guard missing KLING_STITCH_READINESS marker"

export PYTHONPATH="${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest "$TOOLS/tests/test_kling_stitch_readiness.py" -q \
  || fail "pytest test_kling_stitch_readiness failed"

(
  cd "$TOOLS/storyboard-v2"
  npx --yes vitest run src/utils/__tests__/klingStitchReadiness.test.ts
) || fail "vitest klingStitchReadiness.test.ts failed"

echo "[kling-stitch-readiness-durability] OK — structural contract + pytest + vitest passed"
