#!/usr/bin/env bash
# verify_bg_export_stitcher_refresh_isolation.sh — BG_EXPORT_STITCHER_NO_GLOBAL_REHYDRATE_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BG_TAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/BgTab.tsx"
TEST="${REPO_ROOT}/Production/tools/tests/test_bg_export_stitcher_refresh_isolation.py"

fail() { echo "[bg-export-stitch-refresh] FAIL: $1" >&2; exit 1; }

BLOCK="$(sed -n '/const finishExportTerminal = useCallback/,/}, \[exportScopeKey, stitchSlotForSegment\]/p' "$BG_TAB")"
echo "$BLOCK" | grep -q 'stitcherRefreshTick.value += 1' \
  || fail "finishExportTerminal must bump stitcherRefreshTick"
echo "$BLOCK" | grep -q 'serverRehydrateTick.value += 1' \
  && fail "finishExportTerminal must NOT bump serverRehydrateTick (black tab wipe)"

python3 -m pytest "$TEST" -q
echo "[bg-export-stitch-refresh] OK"
