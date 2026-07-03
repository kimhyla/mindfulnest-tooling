#!/usr/bin/env bash
# verify_phase_boundary_fade_durability.sh — Phase A/B tail + stitch dissolve fade durability.
#
# Intro fade-through-black pattern: video-only boundary fades, black BETWEEN slots,
# no in-clip whiteout eating dialogue, no audio afade at module boundaries.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PHASES="$ROOT/Production/tools/server_handlers/phases.py"
PHASE_A="$ROOT/Production/tools/phase_a_av_post.py"
STITCH="$ROOT/Production/tools/server_handlers/stitch_editor.py"
FFMPEG="$ROOT/Production/tools/credentials_lib/ffmpeg_stitch.py"
TESTS="$ROOT/Production/tools/tests"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'PHASE_B_WHITEOUT_ENABLED: bool = False' "$PHASES" || \
  fail "Phase B in-clip whiteout must stay disabled (stitch handles boundaries)"
grep -q 'PHASE_B_WHITEOUT_FADE_AUDIO: bool = False' "$PHASES" || \
  fail "Phase B whiteout must not afade audio when re-enabled"
grep -q 'TRAILING_SPEECH_HOLD_S = 1.5' "$PHASE_A" || \
  fail "Phase A trailing speech hold must be >= 1.5s"
grep -q '_DEFAULT_PHASE_TRANSITION_FADE_MS = 3800' "$STITCH" || \
  fail "default stitch transitions must use 3800ms pair fade budget"
grep -q '"audio_xfade_ms": 0' "$STITCH" || \
  fail "default stitch transitions must use audio_xfade_ms=0"
grep -q 'module_slot_start_offsets_ms' "$FFMPEG" || \
  fail "ffmpeg_stitch must export module_slot_start_offsets_ms"
grep -q 'STITCH_EXPORT_TIMELINE_AUTHORITY_V1' "$FFMPEG" || \
  fail "ffmpeg_stitch must export STITCH_EXPORT_TIMELINE_AUTHORITY_V1"
grep -q 'remux_mp4_video_timeline_authority' "$FFMPEG" || \
  fail "trim_body_with_fade dissolve path must heal A/V via timeline authority"
grep -q 'expand_clips_with_black_pause_boundaries' "$FFMPEG" || \
  fail "missing black-pause boundary helper"

[[ -f "$TESTS/test_phase_b_whiteout_fade.py" ]] || fail "missing test_phase_b_whiteout_fade.py"
[[ -f "$TESTS/test_module_slot_start_offsets.py" ]] || fail "missing test_module_slot_start_offsets.py"
[[ -f "$TESTS/test_stitch_module_preview.py" ]] || fail "missing test_stitch_module_preview.py"

echo "[phase-boundary-fade-durability] OK — source patterns + tests present"
