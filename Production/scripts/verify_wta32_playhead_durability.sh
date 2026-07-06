#!/usr/bin/env bash
# verify_wta32_playhead_durability.sh — WTA32_PLAYHEAD_AUTHORITY_V1
#
# Structural + behavioral gates for play-from-scrub / drop-hold class (ac59914 regression).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SB="${ROOT}/Production/tools/storyboard-v2"
WS="${SB}/src/components/phase/WaveformTimeline.tsx"
WTA="${SB}/src/utils/waveformTimeAuthority.ts"
ANCHOR="${SB}/src/utils/waveformPlaybackAnchor.ts"
ANCHOR_TEST="${SB}/src/utils/__tests__/waveformPlaybackAnchor.test.ts"
LESSONS="${ROOT}/Production/docs/LESSONS_LEARNED_20260706_WTA32_PLAYHEAD_AUTHORITY_v1.md"
E2E="${SB}/e2e/phase_waveform_playback.spec.ts"
LIVE_E2E="${SB}/e2e/phase_g_interaction_live.spec.ts"

fail() { echo "[wta32-playhead-durability] FAIL: $1" >&2; exit 1; }

echo "[wta32-playhead-durability] pass 1/4 — lessons + pure module"
[[ -f "$LESSONS" ]] || fail "missing LESSONS_LEARNED_20260706_WTA32_PLAYHEAD_AUTHORITY_v1.md"
grep -q 'WTA32_PLAYHEAD_AUTHORITY_V1' "$LESSONS" || fail "lessons doc marker missing"
[[ -f "$ANCHOR" ]] || fail "missing waveformPlaybackAnchor.ts"
grep -q 'WTA32_PLAYBACK_ANCHOR_V1' "$ANCHOR" || fail "missing WTA32_PLAYBACK_ANCHOR_V1 marker"

echo "[wta32-playhead-durability] pass 2/4 — structural invariants (WTA-INV-8..12)"
grep -q 'playbackAnchorMsRef' "$WS" \
  || fail "WaveformTimeline must use playbackAnchorMsRef (WTA-INV-9)"
grep -q 'lastScrubMsRef.current = null' "$WS" \
  || fail "WaveformTimeline must clear lastScrubMsRef on play (WTA-INV-10)"
grep -q 'waveformPlaybackAnchor' "$WS" \
  || fail "WaveformTimeline must import waveformPlaybackAnchor contracts"
grep -q 'endDragSeek' "$WS" \
  || fail "commitPlayheadMs must use endDragSeek hold window"
python3 - "$WTA" <<'PY' || fail "legacy scrub must win only at stale media ~0 (WTA-INV-8)"
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
if "mediaTimeMs < 50) return legacy" not in src.replace(" ", ""):
    # tolerate formatting — check semantic pattern
    if "legacy > 0 && mediaTimeMs < 50" not in src:
        raise SystemExit(1)
if "if (legacy != null && legacy > 0) return legacy;" in src:
    raise SystemExit("unconditional legacy scrub still present")
PY
python3 - "$WS" <<'PY' || fail "drop must commit playhead before onWatercolorDrop (WTA-INV-12)"
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
block = src.split("if (payload.kind === 'lib-watercolor')", 1)[1].split("if (payload.kind === 'lib-sfx'", 1)[0]
ci = block.find("commitPlayheadMs")
oi = block.find("onWatercolorDropRef")
if ci < 0 or oi < 0 or ci > oi:
    raise SystemExit(1)
PY
grep -q 'pausedPlayheadHoldMs' "$WS" \
  || fail "paused onSeeking must use pausedPlayheadHoldMs (WTA-INV-11)"

echo "[wta32-playhead-durability] pass 3/4 — vitest contracts"
(
  cd "$SB"
  node --experimental-strip-types --test \
    "$ANCHOR_TEST" \
    src/utils/__tests__/waveformTimeAuthority.test.ts
) || fail "WTA-32 vitest failed"

echo "[wta32-playhead-durability] pass 4/4 — e2e markers"
grep -q 'DROP-PLAY-1' "$E2E" || fail "fixture must include DROP-PLAY-1"
grep -q 'SEEK-PLAY-1' "$E2E" || fail "fixture must include SEEK-PLAY-1"
grep -q 'DROP-PLAYHEAD-LIVE-1' "$LIVE_E2E" || fail "live spec must include DROP-PLAYHEAD-LIVE-1"

echo "[wta32-playhead-durability] OK — WTA32_PLAYHEAD_AUTHORITY_V1"
