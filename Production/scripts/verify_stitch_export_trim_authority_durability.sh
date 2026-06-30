#!/usr/bin/env bash
# verify_stitch_export_trim_authority_durability.sh — KLING_O3_EXPORT_TRIM_AUTHORITY_V1
#
# Root cause class (2026-06-30):
#   Option-row trim (trim_start_s/trim_back_s) diverged from beat-level export authority
#   after heal_invalid_kling_o3_trim cleared beat fields only → Send to Stitcher shipped
#   untrimmed clips while UI showed trimmed handles.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
BG="$TOOLS/beat_generator.py"
K3="$TOOLS/server_handlers/kling_o3.py"
HYDRATE="$TOOLS/storyboard-v2/src/utils/stitchJobMediaHydrate.ts"

fail() { echo "[stitch-export-trim-authority] FATAL: $1" >&2; exit 1; }

echo "[stitch-export-trim-authority] pass 1/4 — export prep contract in beat_generator.py"
grep -q 'KLING_O3_EXPORT_TRIM_AUTHORITY_V1' "$BG" \
  || fail "missing KLING_O3_EXPORT_TRIM_AUTHORITY_V1 marker"
grep -q 'def prepare_beats_for_stitch_export' "$BG" \
  || fail "missing prepare_beats_for_stitch_export"
grep -q 'def assert_beat_export_trim_ready' "$BG" \
  || fail "missing assert_beat_export_trim_ready"
grep -q 'hydrate_beat_trim_from_active_option(beat)' "$BG" \
  || fail "prepare must always hydrate option→beat trim"
grep -q 'KLING_O3_EXPORT_TRIM_ACCURATE_SEEK_V1' "$BG" \
  || fail "missing accurate seek marker on materialize"
grep -q '"-i", str(local_src)' "$BG" \
  || fail "materialize must place -i before -ss (output-side seek)"

echo "[stitch-export-trim-authority] pass 2/4 — Send to Stitcher fails closed on trim drift"
grep -q 'prepare_beats_for_stitch_export' "$K3" \
  || fail "kling_o3 export must call prepare_beats_for_stitch_export"
grep -q 'EXPORT_TRIM_AUTHORITY' "$K3" \
  || fail "kling_o3 export must reject EXPORT_TRIM_AUTHORITY"

echo "[stitch-export-trim-authority] pass 3/4 — hard refresh interim dry video for mux slots"
grep -q 'STITCH_MUX_INTERIM_DRY_VIDEO_V1' "$HYDRATE" \
  || fail "missing STITCH_MUX_INTERIM_DRY_VIDEO_V1 interim playback contract"

echo "[stitch-export-trim-authority] pass 4/4 — pytest"
export PYTHONPATH="${ROOT}/Production/tools:${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest "$TOOLS/tests/test_stitch_export_trim_authority_v1.py" \
  "$TOOLS/tests/test_o3_export_durability.py" -q \
  || fail "trim authority pytest failed"

echo "[stitch-export-trim-authority] OK"
