#!/usr/bin/env bash
# FF-039 — ambient period junction crossfade durability gate.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
LOOP="$ROOT/Production/tools/server_handlers/stitch_ambient_loop.py"
CONST="$ROOT/Production/tools/storyboard-v2/src/utils/stitchConstants.ts"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1' "$LOOP" \
  || fail "missing STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1"
grep -q 'build_ambient_period_junction_loop' "$LOOP" \
  || fail "missing build_ambient_period_junction_loop"
grep -q 'acrossfade=d=' "$LOOP" \
  || fail "junction loop must use acrossfade"
grep -q 'STITCH_AMBIENT_PERIOD_JUNCTION_XFADE_V1' "$CONST" \
  || fail "client STITCH_AMBIENT_LOOP_SIG_V1 must include junction marker"
grep -q 'period_junction_xfade_v1' "$CONST" \
  || fail "client sig suffix must bump for cache bust"

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_ambient_period_junction.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_ambient_loop.py" -q

echo "[stitch-ambient-period-junction] OK"
