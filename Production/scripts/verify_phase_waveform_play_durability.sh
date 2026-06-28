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
CSS="${REPO_ROOT}/Production/tools/storyboard-v2/src/app.css"
WS="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx"
BUS="${REPO_ROOT}/Production/tools/storyboard-v2/src/utils/waveformPlaybackBus.ts"
APP="${REPO_ROOT}/Production/tools/storyboard-v2/src/app.tsx"
E2E="${REPO_ROOT}/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts"

fail() {
  echo "[waveform-play-durability] FAIL: $1" >&2
  exit 1
}

[[ -f "$CSS" ]] || fail "missing app.css"
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
grep -q 'SEEK-DRAG' "$E2E" \
  || fail "e2e must include drag-seek regression (SEEK-DRAG)"
grep -q 'openPhaseA' "$E2E" \
  || fail "e2e must include Phase A parity tests (openPhaseA)"
grep -q 'wsRef.current' "$WS" \
  || fail "drag-seek applySeek must use wsRef.current (stale ws closure guard)"
grep -q 'lastScrubMsRef' "$WS" \
  || fail "paused scrub must use lastScrubMsRef (play-pause-drag on lipsync mp4)"
grep -q 'timelineDurationMsRef' "$WS" \
  || fail "drag-seek must use timelineDurationMsRef — ws.getDuration() can be 0 while loaded"
grep -q 'WAVEFORM_DRAG_SEEK_V2' "$WS" \
  || fail "drag-seek handlers must set data-drag-seek-bound WAVEFORM_DRAG_SEEK_V2"
grep -q 'WAVEFORM_CUE_HANDLE_V1' "$CSS" \
  || fail "cue-block-handle must declare WAVEFORM_CUE_HANDLE_V1 marker in app.css"
grep -q 'pointer-events: auto' "$CSS" \
  || fail "app.css must set pointer-events:auto on interactive waveform handles"
python3 - "$CSS" <<'PY' || fail "mn-waveform-cue-block-handle must include pointer-events:auto (paired with SEEK-4 body none)"
import sys
from pathlib import Path
css = Path(sys.argv[1]).read_text()
start = css.index('.mn-waveform-cue-block-handle {')
end = css.index('}', start)
block = css[start:end+1]
if 'pointer-events: auto' not in block:
    raise SystemExit(1)
PY
grep -q 'resolveTimelineDurationMs' "$WS" \
  || fail "cue resize must use resolveTimelineDurationMs / timelineDurationMsRef (CUE-RESIZE-1)"
grep -q 'data-waveform-cue-handle-v1' "$WS" \
  || fail "WaveformTimeline must expose data-waveform-cue-handle-v1 marker"
grep -q 'CUE-RESIZE-1' "$E2E" \
  || fail "e2e must include behavioral cue resize test (CUE-RESIZE-1)"
grep -q 'CUE-RESIZE-2' "$E2E" \
  || fail "e2e must include left-handle cue resize test (CUE-RESIZE-2)"

echo "[waveform-play-durability] OK — source patterns + e2e spec present"
