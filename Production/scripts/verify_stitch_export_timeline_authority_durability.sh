#!/usr/bin/env bash
# verify_stitch_export_timeline_authority_durability.sh — STITCH_EXPORT_TIMELINE_AUTHORITY_V1 (FF-024)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
BG="$TOOLS/beat_generator.py"
FS="$TOOLS/credentials_lib/ffmpeg_stitch.py"

fail() { echo "[stitch-export-timeline] FATAL: $1" >&2; exit 1; }

echo "[stitch-export-timeline] pass 1/3 — timeline authority in ffmpeg_stitch"
grep -q 'STITCH_EXPORT_TIMELINE_AUTHORITY_V1' "$FS" || fail "missing marker"
grep -q 'def export_clip_timeline_duration_s' "$FS" || fail "missing export_clip_timeline_duration_s"
grep -q 'def assert_stitch_export_cumulative_av_aligned' "$FS" || fail "missing cumulative gate"

echo "[stitch-export-timeline] pass 2/3 — BG export concat wires normalize + cumulative gate"
grep -q 'normalize_for_concat' "$BG" || fail "BG export must normalize before concat"
grep -q 'assert_stitch_export_cumulative_av_aligned' "$BG" || fail "BG export must run cumulative A/V gate"
grep -q 'export_clip_timeline_duration_s' "$BG" || fail "boundaries must use timeline authority"

echo "[stitch-export-timeline] pass 3/3 — pytest"
export PYTHONPATH="${ROOT}/Production/tools:${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest "$TOOLS/tests/test_stitch_export_timeline_authority_v1.py" -q \
  || fail "timeline authority pytest failed"

echo "[stitch-export-timeline] OK"
