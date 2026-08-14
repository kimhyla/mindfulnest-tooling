#!/usr/bin/env bash
# verify_stitch_sfx_playback_truth_durability.sh — STITCH_SFX_PLAYBACK_TRUTH_V1 + V2 (pre-deploy)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${REPO_ROOT}/Production/tools/storyboard-v2"
TAB="${SB}/src/components/StitcherTab.tsx"
HYDRATE="${SB}/src/utils/stitchJobMediaHydrate.ts"
ENGINE="${SB}/src/audio/StitchSlotAudioMixEngine.ts"
SFX_FETCH="${SB}/src/utils/stitchSfxFetch.ts"
LIVE_SPEC="${SB}/e2e/stitch_sfx_playback_truth_live.spec.ts"
LIVE_CFG="${SB}/playwright.live.config.ts"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_mux_pause_geometry.py"
TEST2="${REPO_ROOT}/Production/tools/tests/test_stitch_slot_timeline_atomic.py"
TEST3="${REPO_ROOT}/Production/tools/tests/test_stitch_sfx_hot_serve_prefetch.py"

fail() { echo "[stitch-sfx-playback-truth] FAIL: $1" >&2; exit 1; }

[[ -f "$TAB" ]] || fail "missing StitcherTab.tsx"
[[ -f "$HYDRATE" ]] || fail "missing stitchJobMediaHydrate.ts"
[[ -f "$ENGINE" ]] || fail "missing StitchSlotAudioMixEngine.ts"
[[ -f "$SFX_FETCH" ]] || fail "missing stitchSfxFetch.ts"
[[ -f "$LIVE_SPEC" ]] || fail "missing stitch_sfx_playback_truth_live.spec.ts"
[[ -f "$LIVE_CFG" ]] || fail "missing playwright.live.config.ts"

grep -q 'STITCH_SFX_PLAYBACK_TRUTH_V1' "$TAB" \
  || fail "STITCH_SFX_PLAYBACK_TRUTH_V1 marker missing"
grep -q 'STITCH_SFX_HOT_SERVE_PREFETCH_V1' "$ENGINE" \
  || fail "STITCH_SFX_HOT_SERVE_PREFETCH_V1 marker missing"
grep -q 'prefetchAllSfx' "$ENGINE" \
  || fail "SFX prefetchAllSfx missing"
grep -q 'SFX_LOAD_FAILED' "$ENGINE" \
  || fail "SFX_LOAD_FAILED audit missing"
grep -q 'fetchStitchSfxArrayBuffer' "$SFX_FETCH" \
  || fail "fetchStitchSfxArrayBuffer missing"
grep -q 'STITCH_MUX_PAUSE_ON_GEOMETRY_V1' "$TAB" \
  || fail "STITCH_MUX_PAUSE_ON_GEOMETRY_V1 marker missing"
grep -q 'Paused — updating SFX preview (video stays loaded)' "$TAB" \
  || fail "pause-on-geometry status missing"
grep -q 'resolveSlotPlaybackPreviewUrl' "$HYDRATE" \
  || fail "resolveSlotPlaybackPreviewUrl missing"
grep -q 'STITCH_AMBIENT_PREVIEW_V1' "$TAB" \
  || fail "STITCH_AMBIENT_PREVIEW_V1 marker missing"
grep -q 'STITCH_JOB_SOFT_REFRESH_V1' "$TAB" \
  || fail "STITCH_JOB_SOFT_REFRESH_V1 soft refresh persistence missing"
grep -q 'ensureMilestoneStandaloneVideo' "$LIVE_SPEC" \
  || fail "STITCH_LIVE_E2E_MILESTONE_V1 ensureMilestoneStandaloneVideo missing"
grep -q 'pollStandaloneMuxHash' "$LIVE_SPEC" \
  || fail "STITCH_LIVE_E2E_MILESTONE_V1 pollStandaloneMuxHash missing"
grep -q 'standaloneSavePayload' "$LIVE_SPEC" \
  || fail "STITCH_LIVE_E2E_MILESTONE_V1 standaloneSavePayload missing"
LIVE_VERIFY="${REPO_ROOT}/Production/scripts/verify_stitch_sfx_playback_truth_live_e2e.sh"
grep -q 'STITCH_LIVE_E2E_EVENT_WARM_V1' "$LIVE_VERIFY" \
  || fail "STITCH_LIVE_E2E_EVENT_WARM_V1 deploy warmup missing"
python3 -m pytest "${REPO_ROOT}/Production/tools/tests/test_stitch_ambient_preview_no_save_wipe.py" -q \
  || fail "ambient preview no-save pytest failed"

(
  cd "$SB"
  node --experimental-strip-types --test \
    src/utils/__tests__/stitchSlotTimelineAtomic.test.ts \
    src/utils/__tests__/stitchSfxCueSchedule.test.ts \
    src/utils/__tests__/stitchSfxFetch.test.ts
) || fail "node unit tests failed"

python3 -m pytest "$TEST" "$TEST2" "$TEST3" -q
echo "[stitch-sfx-playback-truth] OK — source guards + unit + pytest passed"