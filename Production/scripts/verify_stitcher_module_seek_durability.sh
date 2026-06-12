#!/usr/bin/env bash
# verify_stitcher_module_seek_durability.sh — LD-828 regression gate for Stitcher
# multi-phase track seek (module preview jump buttons).
#
# Root cause class (2026-06-11/12):
#   1. LD-827 /files fallback + module offsets applied to wrong src → intro-only seek
#   2. video key included viewerSlot → remount reset currentTime to 0 on every click
#   3. cumulativeSlotOffsetsMs ignored black-pause inserts between slots
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
STITCHER="$ROOT/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
MOD="$ROOT/Production/tools/storyboard-v2/src/utils/stitchModulePreview.ts"
DIST="$ROOT/Production/tools/storyboard-v2/dist/index.html"
SERVER="$ROOT/Production/tools/production_server.py"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCHER_MODULE_SEEK_V1' "$STITCHER" || fail "missing STITCHER_MODULE_SEEK_V1 marker in StitcherTab"
grep -q 'seekModulePreviewTo' "$STITCHER" || fail "missing seekModulePreviewTo"
grep -q "key={modulePreviewUrl ? 'stitcher-module-preview'" "$STITCHER" || \
  fail "video key must stay stable for module preview (no viewerSlot remount)"
grep -q 'LD-827 fallback' "$STITCHER" || fail "missing LD-827 seek guard comment"
grep -q 'modulePreviewSeekOffsetMs' "$MOD" || fail "missing modulePreviewSeekOffsetMs helper"
grep -q 'slot_start_offsets_ms' "$MOD" || fail "missing slot_start_offsets_ms in module preview cache type"
grep -q 'module_slot_start_offsets_ms' "$SERVER" || fail "server must compute slot_start_offsets_ms"

if [[ -f "$DIST" ]]; then
  grep -q 'STITCHER_MODULE_SEEK_V1' "$DIST" || fail "dist missing STITCHER_MODULE_SEEK_V1"
  grep -q 'stitcher-module-preview' "$DIST" || fail "dist missing stable module preview video key"
fi

echo "[stitcher-module-seek-durability] OK — source + dist markers present"
