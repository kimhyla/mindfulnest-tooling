#!/usr/bin/env bash
# verify_phase_waveform_play_durability.sh — source-level guards for ▶ Play regressions.
#
# dist markers in check_storyboard_critical_features.sh catch bundle absence;
# this script greps TypeScript sources for the structural patterns that prevent:
#   PLAY-1 seek/play collision (Play inside seek wrapper)
#   PLAY-2 async play before user gesture
#   PLAY-3 unstable playback-bus identity
#   PLAY-4 render-time stopAll effect
#
# Called by deploy_storyboard_v59.sh after dist regression guard.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WS="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx"
BUS="${REPO_ROOT}/Production/tools/storyboard-v2/src/utils/waveformPlaybackBus.ts"
APP="${REPO_ROOT}/Production/tools/storyboard-v2/src/app.tsx"
E2E="${REPO_ROOT}/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts"

fail() {
  echo "[waveform-play-durability] FAIL: $1" >&2
  exit 1
}

[[ -f "$WS" ]] || fail "missing WaveformTimeline.tsx"
[[ -f "$BUS" ]] || fail "missing waveformPlaybackBus.ts"
[[ -f "$APP" ]] || fail "missing app.tsx"
[[ -f "$E2E" ]] || fail "missing e2e/phase_waveform_playback.spec.ts"

grep -q 'mn-waveform-source-label' "$WS" \
  || fail "shouldSkipSeek must exclude .mn-waveform-source-label (PLAY-1)"
grep -q 'stopPropagation' "$WS" \
  || fail "Play button must stopPropagation on pointerdown (PLAY-1)"
grep -q 'void ws.play()' "$WS" \
  || fail "startPlayback must call ws.play() synchronously — void ws.play() (PLAY-2)"
grep -q 'busId' "$BUS" \
  || fail "waveformPlaybackBus must use busId identity (PLAY-3)"
grep -q 'registerWaveformPlaybackControl' "$WS" \
  || fail "WaveformTimeline must register on playback bus (Stitcher + Phase A/B)"
grep -q 'mn-stitcher-pane' "$BUS" \
  || fail "waveformPlaybackBus must pause Stitcher preview media on tab change"
grep -q 'mn-library-preview-audio' "$BUS" \
  || fail "waveformPlaybackBus must pause library preview audio on tab change"
grep -q 'prevTabRef' "$APP" \
  || fail "app.tsx must use prevTabRef tab-change stop (PLAY-4)"
grep -q 'seek-jump' "$E2E" \
  || fail "e2e/phase_waveform_playback.spec.ts must include seek-jump regression test"
grep -q 'openPhaseA' "$E2E" \
  || fail "e2e must include Phase A parity tests (openPhaseA)"

echo "[waveform-play-durability] OK — source patterns + e2e spec present"
