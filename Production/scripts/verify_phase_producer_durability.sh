#!/usr/bin/env bash
# verify_phase_producer_durability.sh — source-level guards for Phase A/B producer regressions.
#
# Symptom → fix mapping (2026-06-12, shared PhaseProducer for phase a + b):
#   OVERLAY-1  oversized watercolor — .mn-lipsync-video-wrapper display:inline-block
#   OVERLAY-2  bbox cap — .mn-lipsync-watercolor-overlay max-height:55%
#   OVERLAY-3  pink frame — canvas applyMagentaChromakey (not raw <video>)
#   OVERLAY-4  still animation — WatercolorAnimOverlay loop + wave play sync
#   PLAY-5     ghost audio — pauseAllPhasePlayback on pause toggle
#   PLAY-6     pause UI desync — syncPlayUi on audioprocess
#   PLAY-7     ws leak on remount — ws.pause() before destroy
#   AB-1       single producer — WatercolorAnimOverlay imported in PhaseProducer
#
# Called by deploy_storyboard_v59.sh after verify_phase_waveform_play_durability.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CSS="${REPO_ROOT}/Production/tools/storyboard-v2/src/app.css"
PRODUCER="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx"
ANIM="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/phase/WatercolorAnimOverlay.tsx"
KEY="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/phase/watercolorChromakey.ts"
WS="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx"
BUS="${REPO_ROOT}/Production/tools/storyboard-v2/src/utils/waveformPlaybackBus.ts"
E2E="${REPO_ROOT}/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts"

fail() {
  echo "[phase-producer-durability] FAIL: $1" >&2
  exit 1
}

for f in "$CSS" "$PRODUCER" "$ANIM" "$KEY" "$WS" "$BUS" "$E2E"; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'data-phase-producer-ab="PHASE_PRODUCER_AB_V1"' "$PRODUCER" \
  || fail "PhaseProducer root must expose PHASE_PRODUCER_AB_V1 data attribute for dist guard"
grep -q 'data-phase-watercolor-overlay="PHASE_WATERCOLOR_OVERLAY_V1"' "$PRODUCER" \
  || fail "PhaseProducer root must expose PHASE_WATERCOLOR_OVERLAY_V1 data attribute"
grep -q 'display: inline-block' "$CSS" \
  || fail "mn-lipsync-video-wrapper must use inline-block (OVERLAY-1)"
grep -q 'max-height: 55%' "$CSS" \
  || fail "overlay max-height 55% bbox cap missing (OVERLAY-2)"
grep -q 'PHASE_WATERCOLOR_OVERLAY_V1' "$CSS" \
  || fail "app.css PHASE_WATERCOLOR_OVERLAY_V1 marker missing"
grep -q 'applyMagentaChromakey' "$KEY" \
  || fail "watercolorChromakey.ts must export applyMagentaChromakey (OVERLAY-3)"
grep -q 'video.loop = true' "$ANIM" \
  || fail "WatercolorAnimOverlay must loop animated rub MP4 (OVERLAY-4)"
grep -q 'watercolor-anim-overlay' "$ANIM" \
  || fail "WatercolorAnimOverlay must expose data-testid watercolor-anim-overlay"
grep -q 'WatercolorAnimOverlay' "$PRODUCER" \
  || fail "PhaseProducer must render WatercolorAnimOverlay for animated cues (AB-1)"
grep -q 'onPlayStateChange={setWaveIsPlaying}' "$PRODUCER" \
  || fail "PhaseProducer must wire onPlayStateChange for anim overlay sync"
grep -q 'pauseAllPhasePlayback' "$WS" \
  || fail "WaveformTimeline pause toggle must call pauseAllPhasePlayback (PLAY-5)"
grep -q 'syncPlayUi' "$WS" \
  || fail "WaveformTimeline must syncPlayUi on audioprocess (PLAY-6)"
grep -q 'ws.pause()' "$WS" \
  || fail "WaveformTimeline unmount must ws.pause() before destroy (PLAY-7)"
grep -q 'pauseAllPhasePlayback' "$BUS" \
  || fail "waveformPlaybackBus must export pauseAllPhasePlayback"
grep -q 'openPhaseA' "$E2E" \
  || fail "e2e must include Phase A waveform playback parity tests"
grep -q 'PHASE_A_SINGLE_PLAYER_V1' "$PRODUCER" \
  || fail "PhaseProducer must expose PHASE_A_SINGLE_PLAYER_V1 (LD-829 single canonical player)"
grep -q 'phaseAPreviewFile' "$PRODUCER" \
  || fail "PhaseProducer must use phaseAPreviewFile for canonical stitched/lipsync selection"
grep -q 'data-testid="phase-a-stitched-preview"' "$PRODUCER" \
  && fail "duplicate phase-a-stitched-preview player block must not return (LD-829)"

echo "[phase-producer-durability] OK — Phase A/B producer source patterns + e2e parity present"
