#!/usr/bin/env bash
# verify_interaction_platform_durability.sh — INTERACTION_PLATFORM_V1 (G1 / RC12)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SB="$ROOT/Production/tools/storyboard-v2"
SRC="$SB/src"

fail() { echo "[interaction-platform-durability] FATAL: $1" >&2; exit 1; }

HOOK="$SRC/hooks/useDropTargetCapture.ts"
DD="$SRC/utils/dragdrop.ts"
[[ -f "$HOOK" ]] || fail "missing useDropTargetCapture.ts"
grep -q "bindDropTargetCapture" "$HOOK" || fail "hook must call bindDropTargetCapture"
grep -q "bindDropTargetCapture" "$DD" || fail "dragdrop.ts must export bindDropTargetCapture"

for f in \
  components/phase/WaveformTimeline.tsx \
  components/StitcherTab.tsx \
  components/BgTab.tsx \
  components/StoryboardTab.tsx \
  components/CropperModal.tsx; do
  [[ -f "$SRC/$f" ]] || fail "missing $f"
  grep -qE 'useDropTargetCapture|bindDropTargetCapture' "$SRC/$f" \
    || fail "$f must bind capture-phase drop (DROP-CAPTURE-1)"
done

grep -rq 'draggable={false}' "$SRC/components/phase/PhaseProducer.tsx" "$SRC/components/ui/AssetTile.tsx" \
  || fail "watercolor/library thumbs must set draggable={false} (DROP-IMG-1)"

grep -q "DROP-WC-2" "$SB/e2e/phase_waveform_playback.spec.ts" \
  || fail "missing DROP-WC-2 e2e"

echo "[interaction-platform-durability] fixture DROP-WC-2 ..."
(
  cd "$SB"
  npx playwright test e2e/phase_waveform_playback.spec.ts -g "DROP-WC-2"
) || fail "DROP-WC-2 e2e failed"

echo "[interaction-platform-durability] OK — capture drop on all surfaces + DROP-WC-2 green"
