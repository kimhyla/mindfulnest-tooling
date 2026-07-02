#!/usr/bin/env bash
# FF-040 — lipsync export video A/V authority durability gate.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
FF="$ROOT/Production/tools/credentials_lib/ffmpeg_stitch.py"
BG="$ROOT/Production/tools/beat_generator.py"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1' "$FF" \
  || fail "missing STITCH_EXPORT_LIPSYNC_VIDEO_AUTHORITY_V1"
grep -q 'STITCH_EXPORT_NORM_AV_MAX_DRIFT_S' "$FF" \
  || fail "missing STITCH_EXPORT_NORM_AV_MAX_DRIFT_S"
grep -q 'apad=whole_dur=' "$FF" \
  || fail "normalize must pad/trim audio to video duration"
grep -q 'assert_stitch_export_clips_av_aligned' "$BG" \
  || fail "beat_generator export must call av alignment gate"

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_export_lipsync_video_authority.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_export_av_drift_gate.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_export_timeline_authority_v1.py" -q

echo "[stitch-export-lipsync-video-authority] OK"
