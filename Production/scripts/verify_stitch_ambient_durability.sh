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

echo "[stitch-ambient-durability] OK — source markers + pytest passed"
