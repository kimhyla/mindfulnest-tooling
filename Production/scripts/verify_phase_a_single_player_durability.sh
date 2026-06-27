#!/usr/bin/env bash
# verify_phase_a_single_player_durability.sh — LD-829 regression gate for Phase A tab.
#
# Root cause class (2026-06-13):
#   Phase A showed TWO <video> elements — lipsync player + stitched preview block.
#   Stitcher got LD-828 single composer; Phase A tab did not.
#
# Canonical rule (PHASE_A_CHIPPER_PIPELINE_LOCKED_v1):
#   One player on Phase A tab; stitched when fresh, else lipsync while producing.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PRODUCER="$ROOT/Production/tools/storyboard-v2/src/components/phase/PhaseProducer.tsx"
WAVEFORM="$ROOT/Production/tools/storyboard-v2/src/components/phase/WaveformTimeline.tsx"
DIST="$ROOT/Production/tools/storyboard-v2/dist/index.html"
GUARD="$ROOT/Production/scripts/check_storyboard_critical_features.sh"

fail() { echo "[phase-a-single-player-durability] FATAL: $1" >&2; exit 1; }

[[ -f "$PRODUCER" ]] || fail "missing PhaseProducer.tsx"

grep -q 'PHASE_A_SINGLE_PLAYER_V1' "$PRODUCER" \
  || fail "missing PHASE_A_SINGLE_PLAYER_V1 marker on PhaseProducer"
grep -q 'phaseAPreviewFile' "$PRODUCER" \
  || fail "missing phaseAPreviewFile helper"
grep -q 'priorityAudioFileForPhase' "$PRODUCER" \
  || fail "missing priorityAudioFileForPhase helper"
grep -q 'Preview (normalized dry lipsync — ambient added in Stitcher):' "$PRODUCER" \
  || fail "missing dry lipsync preview label"
grep -q 'phase-a-mix-btn' "$PRODUCER" \
  && fail "Phase A Mix Audio button must not exist (ambient in Stitcher)"

# Banned regressions — second stitched-only player block.
grep -q 'data-testid="phase-a-stitched-preview"' "$PRODUCER" \
  && fail "duplicate phase-a-stitched-preview block reintroduced"
grep -q 'mn-phase-stitched-video' "$PRODUCER" \
  && fail "mn-phase-stitched-video second player reintroduced"
grep -q 'Stitched preview (lipsync + ambient bed):' "$PRODUCER" \
  && fail "legacy second-player heading reintroduced"

grep -q "'stitched'" "$WAVEFORM" \
  || fail "WaveformTimeline must accept stitched sourceLabel"

if [[ -f "$DIST" ]]; then
  grep -q 'PHASE_A_SINGLE_PLAYER_V1' "$DIST" \
    || fail "dist missing PHASE_A_SINGLE_PLAYER_V1 (run npm run build)"
  grep -q 'Preview (normalized dry lipsync' "$DIST" \
    || fail "dist missing dry lipsync preview label"
fi

if [[ -f "$GUARD" ]]; then
  bash "$GUARD" || fail "check_storyboard_critical_features.sh failed"
fi

python3 -m pytest \
  "$ROOT/Production/tools/tests/test_phase_a_single_player.py" \
  "$ROOT/Production/tools/tests/test_phase_a_stitcher_ambient_only.py" -q \
  || fail "Phase A pytest guards failed"

echo "[phase-a-single-player-durability] OK — LD-829 source + dist + pytest guards passed"
