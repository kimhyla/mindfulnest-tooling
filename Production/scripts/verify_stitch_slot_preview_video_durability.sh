#!/usr/bin/env bash
# verify_stitch_slot_preview_video_durability.sh — STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1
#
# Root cause class (2026-06-13):
#   stitch_preview_* LRU hit passed ffprobe duration checks but H.264 bitstream was
#   corrupt → browser <video> black while WaveSurfer audio still played.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
STITCHER="$ROOT/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
POOL="$ROOT/Production/tools/storyboard-v2/src/components/StitchComposerVideoPool.tsx"
FFMPEG="$ROOT/Production/tools/credentials_lib/ffmpeg_stitch.py"
SERVER="$ROOT/Production/tools/production_server.py"
DIST="$ROOT/Production/tools/storyboard-v2/dist/index.html"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1' "$STITCHER" || fail "missing client marker"
grep -q 'clearCachedStitcherPreview' "$STITCHER" || fail "missing preview cache invalidation on video error"
grep -q 'STITCH_UNIFIED_PLAYBACK_V1' "$STITCHER" || fail "missing unified playback marker"
grep -q 'onPoolSlotError' "$STITCHER" || fail "missing onPoolSlotError handler"
grep -q 'onSlotError' "$POOL" || fail "missing pool onSlotError handler"
grep -q 'STITCH_COMPOSER_VIDEO_POOL_V1' "$POOL" || fail "missing video pool marker"
grep -q 'def mp4_decodes_cleanly' "$FFMPEG" || fail "missing mp4_decodes_cleanly"
grep -q 'mp4_decodes_cleanly' "$FFMPEG" || fail "preview_cache_is_valid must decode-probe"
grep -q 'copy_streams=False' "$FFMPEG" || fail "concat must re-encode fallback on A/V drift"
grep -q 'stitch_preview_decode_timeout_s' "$FFMPEG" || fail "missing duration-scaled decode timeout"
grep -q 'av_duration_drift_s(path)' "$FFMPEG" || fail "preview_cache_is_valid must check A/V drift"
grep -q 'assert_stitch_export_clips_av_aligned(slot_finals)' "$SERVER" || fail "pipeline must gate slot finals A/V"
grep -q 'preview_av_drift_s = av_duration_drift_s(out_path)' "$SERVER" || fail "pipeline must gate preview A/V"
grep -q 'st_mtime_ns' "$SERVER" || fail "preview hash must fingerprint slot finals"
grep -q 'len(slot_finals) == 1' "$SERVER" || fail "single-slot preview must copy not concat"

if [[ -f "$DIST" ]]; then
  grep -q 'STITCH_SLOT_PREVIEW_VIDEO_PLAYABLE_V1' "$DIST" || fail "dist missing marker"
fi

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_slot_preview_video_playable.py" "$ROOT/Production/tools/tests/test_stitch_module_bake_av_parity.py" -q

echo "[stitch-slot-preview-video-durability] OK — decode validation + client fallback wired"
