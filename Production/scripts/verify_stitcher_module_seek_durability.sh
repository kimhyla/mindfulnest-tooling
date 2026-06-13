#!/usr/bin/env bash
# verify_stitcher_module_seek_durability.sh — LD-828 regression gate for Stitcher
# single slot composer (multi-phase track switches processed per-slot preview).
#
# Root cause class (2026-06-11/12):
#   1. Dual players: top raw /files vs bottom module reel → wrong Phase A on top
#   2. LD-827 /files fallback + module offsets applied to wrong src → intro-only seek
#   3. video key included viewerSlot → remount reset currentTime to 0 on every click
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
STITCHER="$ROOT/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
MOD="$ROOT/Production/tools/storyboard-v2/src/utils/stitchModulePreview.ts"
DIST="$ROOT/Production/tools/storyboard-v2/dist/index.html"
SERVER="$ROOT/Production/tools/production_server.py"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCHER_SINGLE_COMPOSER_V1' "$STITCHER" || fail "missing STITCHER_SINGLE_COMPOSER_V1 marker in StitcherTab"
grep -q 'buildSlotPreview' "$STITCHER" || fail "missing buildSlotPreview"
grep -q 'seekComposerTo' "$STITCHER" || fail "missing seekComposerTo"
grep -q 'composerVideoUrl' "$STITCHER" || fail "composer must use processed previewUrls fallback"
grep -q 'modulePreviewSeekOffsetMs' "$MOD" || fail "missing modulePreviewSeekOffsetMs helper"
grep -q 'slot_start_offsets_ms' "$MOD" || fail "missing slot_start_offsets_ms in module preview cache type"
grep -q 'module_slot_start_offsets_ms' "$SERVER" || fail "server must compute slot_start_offsets_ms"

if [[ -f "$DIST" ]]; then
  grep -q 'STITCHER_SINGLE_COMPOSER_V1' "$DIST" || fail "dist missing STITCHER_SINGLE_COMPOSER_V1"
  grep -q 'stitcher-composer-video' "$DIST" || fail "dist missing stitcher-composer-video"
fi

echo "[stitcher-module-seek-durability] OK — source + dist markers present"
