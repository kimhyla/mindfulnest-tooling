#!/usr/bin/env bash
# verify_stitch_ambient_durability.sh — canonical ambient presets + 0.15 volume gate.
#
# Root cause class (2026-06-12):
#   1. Empty-slot wipe on ambient save without merge_slots
#   2. Legacy 0.6 / 0.18 ambient_volume drift vs canonical 0.15 under speech
#   3. Default beds only on intro — must auto-apply per slot on export/load
#   4. Composer waveform audio_extract must mix ambient + SFX with amix normalize=0
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
STITCHER="$ROOT/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
CONST="$ROOT/Production/tools/storyboard-v2/src/utils/stitchConstants.ts"
WAVEFORM="$ROOT/Production/tools/storyboard-v2/src/components/StitcherSlotWaveform.tsx"
EDITOR="$ROOT/Production/tools/server_handlers/stitch_editor.py"
DIST="$ROOT/Production/tools/storyboard-v2/dist/index.html"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCH_DEFAULT_AMBIENT_BEDS' "$EDITOR" || fail "missing STITCH_DEFAULT_AMBIENT_BEDS in stitch_editor.py"
grep -q 'STITCH_AMBIENT_BED_VOLUME = 0.15' "$EDITOR" || fail "missing STITCH_AMBIENT_BED_VOLUME constant"
grep -q 'STITCH_AMBIENT_FULL_PERIOD_TILE_V2' "$ROOT/Production/tools/server_handlers/stitch_ambient_loop.py" \
  || fail "missing STITCH_AMBIENT_FULL_PERIOD_TILE_V2"
grep -q 'concat=n=2:v=0:a=1\[.*tile\]' "$ROOT/Production/tools/server_handlers/stitch_ambient_loop.py" \
  || fail "ambient tile must use pre+wrap concat (V2)"
grep -q '\[amb1p1\]' "$ROOT/Production/tools/server_handlers/stitch_ambient_loop.py" \
  && fail "V3 offset tile labels must not be present in shipped ambient loop"
grep -q 'build_ambient_seamless_period_tile' "$ROOT/Production/tools/server_handlers/stitch_ambient_loop.py" \
  || fail "missing build_ambient_seamless_period_tile"
grep -q 'STITCH_AMBIENT_FULL_PERIOD_TILE_V2:STITCH_AMBIENT_BED_MIX_FADE_IN_V1' "$CONST" \
  || fail "STITCH_AMBIENT_LOOP_SIG_V1 must mirror server ambient_loop_sig_token()"
grep -q 'previewUrlMatchesPersistedMux' "$ROOT/Production/tools/storyboard-v2/src/utils/stitchJobMediaHydrate.ts" \
  || fail "resolveSlotPlaybackPreviewUrl must reject stale mux hash URLs"
grep -q 'force_ambient_mix_rebuild' "$EDITOR" \
  || fail "mux preview export must force ambient mix rebuild"
grep -q 'STITCH_AMBIENT_FORCE_REBUILD_ON_EXPORT_V1' "$EDITOR" \
  || fail "export-only ambient force rebuild marker missing"
preview_block="$(python3 - "$EDITOR" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
start = src.index("def handle_stitch_preview")
end = src.index("\ndef ", start + 1)
print(src[start:end])
PY
)"
echo "$preview_block" | grep -q 'force_ambient_mix_rebuild' \
  && fail "handle_stitch_preview must not force ambient rebuild (STITCH_SLOT_SESSION_CACHE_V1)"
grep -q 'build_ambient_bed_filter_lane' "$EDITOR" || fail "missing build_ambient_bed_filter_lane in stitch_editor"
grep -q 'build_ambient_bed_filter_lane' "$ROOT/Production/tools/production_server.py" \
  || fail "missing build_ambient_bed_filter_lane in production_server"
grep -q 'normalize_job_slots_audio' "$EDITOR" || fail "missing normalize_job_slots_audio"
grep -q '_persist_stitch_job_canonical_audio' "$EDITOR" || fail "missing _persist_stitch_job_canonical_audio"
grep -q '_mix_stitch_waveform_audio' "$EDITOR" || fail "missing _mix_stitch_waveform_audio"
grep -q 'apply_stitch_slot_default_ambient_preset' "$EDITOR" || fail "missing apply_stitch_slot_default_ambient_preset"

grep -q 'STITCH_DEFAULT_AMBIENT_BEDS_V1' "$CONST" || fail "missing STITCH_DEFAULT_AMBIENT_BEDS_V1 in stitchConstants"
grep -q 'normalizeStitchSlotAmbientVolumesInPlace' "$STITCHER" || fail "missing normalizeStitchSlotAmbientVolumesInPlace"
grep -q 'STITCH_AMBIENT_VOLUME_PERSIST_V1' "$STITCHER" || fail "missing STITCH_AMBIENT_VOLUME_PERSIST_V1 marker"

grep -q 'STITCH_AMBIENT_BED_VOLUME_V1' "$WAVEFORM" || fail "missing STITCH_AMBIENT_BED_VOLUME_V1 on waveform wrap"
grep -q 'STITCH_SLOT_AUDIO_MIX_V1' "$WAVEFORM" || fail "missing STITCH_SLOT_AUDIO_MIX_V1 on waveform wrap"

if [[ -f "$DIST" ]]; then
  grep -q 'STITCH_DEFAULT_AMBIENT_BEDS_V1' "$DIST" || fail "dist missing STITCH_DEFAULT_AMBIENT_BEDS_V1"
  grep -q 'STITCH_AMBIENT_VOLUME_PERSIST_V1' "$DIST" || fail "dist missing STITCH_AMBIENT_VOLUME_PERSIST_V1"
fi

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_ambient_hydrate.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_ambient_loop.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_ambient_loop_seam_budget.py" -q

echo "[stitch-ambient-durability] OK — source markers + pytest passed"
