#!/usr/bin/env bash
# verify_bg_stitch_export_preflight_durability.sh — BG_STITCH_EXPORT_PREFLIGHT_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
MODULE="$TOOLS/bg_stitch_export_preflight.py"
BG_TAB="$TOOLS/storyboard-v2/src/components/BgTab.tsx"
ENDPOINTS="$TOOLS/storyboard-v2/src/api/endpoints.ts"
SERVER="$TOOLS/production_server.py"

fail() { echo "[bg-stitch-export-preflight-durability] FATAL: $1" >&2; exit 1; }

[[ -f "$MODULE" ]] || fail "missing bg_stitch_export_preflight.py"
grep -q 'BG_STITCH_EXPORT_PREFLIGHT_V1' "$MODULE" || fail "missing contract marker"
grep -q 'build_bg_stitch_export_preflight_manifest' "$MODULE" || fail "missing manifest builder"
grep -q 'export-to-stitcher-preflight' "$SERVER" || fail "production_server missing preflight route"
grep -q 'bg_export_to_stitcher_preflight' "$ENDPOINTS" || fail "endpoints missing preflight read key"
grep -q 'bg_export_to_stitcher_preflight' "$BG_TAB" || fail "BgTab must call preflight before export"
grep -q 'stitchExportPreflightErrorMessage' "$BG_TAB" || fail "BgTab must surface preflight fix instructions"

OWC="$TOOLS/operator_workbench_contract.py"
grep -q 'beat_stitch_export_derived_fields' "$OWC" || fail "operator_workbench_contract missing stitch derived enrich"
grep -q 'stitch_export_ready' "$TOOLS/kling_stitch_readiness.py" \
  || fail "kling_stitch_readiness missing stitch_export_ready derived fields"

BG_TYPES="$TOOLS/storyboard-v2/src/types/bgBeat.ts"
grep -q 'stitch_export_ready' "$BG_TYPES" || fail "BgBeatDerived missing stitch_export_ready"

if grep -q "isStitchApproved = klingO3Status === 'approved'" "$BG_TAB"; then
  fail "option tile regressed to klingO3Status === approved stitch gate"
fi

export PYTHONPATH="${ROOT}/Production/tools:${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest "$TOOLS/tests/test_bg_stitch_export_preflight.py" -q \
  || fail "pytest test_bg_stitch_export_preflight failed"

(
  cd "$TOOLS/storyboard-v2"
  npx --yes vitest run src/utils/__tests__/bgStitchExport.test.ts
) || fail "vitest bgStitchExport.test.ts failed"

echo "[bg-stitch-export-preflight-durability] OK — structural contract + pytest + vitest passed"
