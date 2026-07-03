#!/usr/bin/env bash
# verify_stitch_export_truth_v2_durability.sh — FF-038 intro export truth v2 multipass gate
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail() { echo "FATAL: $1" >&2; exit 1; }

echo "=== STITCH_EXPORT_TRUTH v2 (FF-038) durability ==="

echo "[1/8] pytest export truth v2"
python3 -m pytest tests/test_stitch_export_truth_v2_durability.py -v --tb=short

echo "[2/8] pytest ambient loop seam budget"
python3 -m pytest tests/test_stitch_ambient_loop_seam_budget.py -v --tb=short

echo "[3/8] pytest export truth v1 regression"
python3 -m pytest tests/test_stitch_export_truth_durability.py -v --tb=short

echo "[4/8] static: still-insert metadata + video fade"
grep -q 'STITCH_EXPORT_TRUTH_STILL_INSERT_VIDEO_FADE_V1' beat_generator.py \
  || fail "missing STITCH_EXPORT_TRUTH_STILL_INSERT_VIDEO_FADE_V1"
grep -q '_still_insert_exit_at_join' beat_generator.py \
  || fail "missing _still_insert_exit_at_join"
grep -q 'still_insert_flags, scratch_dir' beat_generator.py \
  || fail "resolve must return still_insert_flags"

echo "[5/8] static: ambient tile concat loop"
grep -q 'STITCH_AMBIENT_TILE_CONCAT_LOOP_V1' server_handlers/stitch_ambient_loop.py \
  || fail "missing STITCH_AMBIENT_TILE_CONCAT_LOOP_V1"
grep -q 'build_ambient_explicit_tile_concat_loop' server_handlers/stitch_ambient_loop.py \
  || fail "missing build_ambient_explicit_tile_concat_loop"
if grep -q '\[.*tile\]aloop=loop=-1' server_handlers/stitch_ambient_loop.py; then
  fail "full-period ambient path must not use hard aloop on tile"
fi

echo "[6/8] static: waveform peaks invalidate on export"
grep -q 'STITCH_EXPORT_TRUTH_WAVEFORM_INVALIDATE_ON_EXPORT_V1' server_handlers/stitch_slot_playback.py \
  || fail "missing waveform invalidate marker"
grep -q 'slot.pop("waveform_peaks_hash"' server_handlers/stitch_slot_playback.py \
  || fail "missing waveform_peaks_hash purge"

echo "[7/8] authority registry"
bash "$ROOT/Production/scripts/verify_authority_registry_durability.sh"

echo "[8/8] spec present"
test -f "$ROOT/Production/docs/TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V2.md" \
  || fail "missing TECH_SPEC_STITCH_INTRO_EXPORT_TRUTH_V2.md"

echo "OK verify_stitch_export_truth_v2_durability"
