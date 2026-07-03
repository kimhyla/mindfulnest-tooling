#!/usr/bin/env bash
# verify_stitch_export_truth_durability.sh — FF-037 intro export truth multipass gate
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail() { echo "FATAL: $1" >&2; exit 1; }

echo "=== STITCH_EXPORT_TRUTH (FF-037) durability ==="

echo "[1/7] pytest export truth contract"
python3 -m pytest tests/test_stitch_export_truth_durability.py -v --tb=short

echo "[2/7] pytest kling concat export"
python3 -m pytest tests/test_kling_o3_concat_export.py -v --tb=short

echo "[3/7] static: join fade marker"
grep -q 'STITCH_EXPORT_TRUTH_JOIN_FADE_V1' beat_generator.py \
  || fail "missing STITCH_EXPORT_TRUTH_JOIN_FADE_V1"
grep -q 'KLING_EXPORT_AUDIO_JOIN_FADE_MS = 80' beat_generator.py \
  || fail "join fade must be 80ms"

echo "[4/7] static: playback remux + waveform speech"
grep -q 'STITCH_EXPORT_TRUTH_PLAYBACK_REMUX_V1' server_handlers/stitch_slot_playback.py \
  || fail "missing playback remux marker"
grep -q 'STITCH_EXPORT_TRUTH_WAVEFORM_SPEECH_V1' server_handlers/stitch_slot_playback.py \
  || fail "missing waveform speech marker"
grep -q 'resolve_four_files_waveform_video_path' server_handlers/stitch_slot_playback.py \
  || fail "missing resolve_four_files_waveform_video_path"

echo "[5/7] static: mix faststart"
mix_block="$(python3 - "$TOOLS/production_server.py" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
start = src.index("def _stitch_mix_slot_audio")
end = src.index("\n    def _stitch_build_pipeline", start)
print(src[start:end])
PY
)"
echo "$mix_block" | grep -q '+faststart' || fail "_stitch_mix_slot_audio must use +faststart"

echo "[6/7] static: client waveform dry path"
grep -q 'resolveSlotWaveformVideoPath' storyboard-v2/src/utils/stitchJobMediaHydrate.ts \
  || fail "client missing resolveSlotWaveformVideoPath"
grep -q 'resolveSlotWaveformVideoPath' storyboard-v2/src/components/StitcherTab.tsx \
  || fail "StitcherTab must use resolveSlotWaveformVideoPath"

echo "[7/7] spec present"
test -f "$ROOT/Production/docs/TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V1.md" \
  || fail "missing TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V1.md"

echo "OK verify_stitch_export_truth_durability"
