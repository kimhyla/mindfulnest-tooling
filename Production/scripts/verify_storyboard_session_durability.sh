#!/usr/bin/env bash
# verify_storyboard_session_durability.sh — aggregate gate for 2026-06-12 session fixes.
# Runs all sub-guards; invoked by deploy_storyboard_v59.sh before rsync.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPTS="$ROOT/Production/scripts"

run() {
  bash "$1" || exit 1
}

run "$SCRIPTS/verify_phase_waveform_play_durability.sh"
run "$SCRIPTS/verify_phase_producer_durability.sh"
run "$SCRIPTS/verify_phase_a_single_player_durability.sh"
run "$SCRIPTS/verify_stitcher_module_seek_durability.sh"
run "$SCRIPTS/verify_stitch_slot_preview_video_durability.sh"
run "$SCRIPTS/verify_stitch_canonical_transitions_durability.sh"
run "$SCRIPTS/verify_stitch_ambient_durability.sh"
run "$SCRIPTS/verify_stitch_sfx_qa.sh"
run "$SCRIPTS/verify_library_audio_durability.sh"
run "$SCRIPTS/verify_phase_boundary_fade_durability.sh"
run "$SCRIPTS/verify_phase_voice_stem_pin_durability.sh"
run "$SCRIPTS/verify_stitch_slot_audio_extract_durability.sh"
run "$SCRIPTS/verify_stitch_slot_export_full_media_durability.sh"
run "$SCRIPTS/verify_event_canonical_module.sh"
run "$SCRIPTS/verify_event_library_scope_durability.sh"
run "$SCRIPTS/verify_scope_deep_link_durability.sh"

python3 -m pytest \
  "$ROOT/Production/tools/tests/test_stitch_audio_file_serve.py" \
  "$ROOT/Production/tools/tests/test_cr_upload_audio.py" \
  "$ROOT/Production/tools/tests/test_phase_b_whiteout_fade.py" \
  "$ROOT/Production/tools/tests/test_stitch_module_seek.py" \
  "$ROOT/Production/tools/tests/test_module_slot_start_offsets.py" \
  "$ROOT/Production/tools/tests/test_stitch_module_preview.py" \
  "$ROOT/Production/tools/tests/test_phase_a_single_player.py" \
  "$ROOT/Production/tools/tests/test_stitch_slot_preview_video_playable.py" \
  "$ROOT/Production/tools/tests/test_stitch_canonical_transition_sfx.py" \
  "$ROOT/Production/tools/tests/test_stitch_sfx_duration_trim.py" \
  "$ROOT/Production/tools/tests/test_stitch_ambient_hydrate.py" \
  "$ROOT/Production/tools/tests/test_phase_a_av_post.py::test_trailing_speech_hold_avoids_aggressive_clip" \
  "$ROOT/Production/tools/tests/test_phase_voice_stem_pin_durability.py" \
  "$ROOT/Production/tools/tests/test_stitch_slot_audio_extract_durability.py" \
  "$ROOT/Production/tools/tests/test_stitch_slot_export_full_media_durability.py" \
  -q

echo "[storyboard-session-durability] OK — all sub-guards + pytest passed"
