#!/usr/bin/env bash
# verify_elevenlabs_tts_stitching_durability.sh — Phase B eleven_v3 ffmpeg concat path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
LIB="${REPO_ROOT}/Production/lib/elevenlabs_tts.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_elevenlabs_tts_stitching.py"
CONCAT_TEST="${REPO_ROOT}/Production/tools/tests/test_phase_voice_stem_concat.py"

fail() {
  echo "[elevenlabs-tts-stitching] FAIL: $1" >&2
  exit 1
}

[[ -f "$PHASES" ]] || fail "missing phases.py"
[[ -f "$LIB" ]] || fail "missing elevenlabs_tts.py"
[[ -f "$TEST" ]] || fail "missing test_elevenlabs_tts_stitching.py"

grep -q 'PHASE_VOICE_STEM_CONCAT_V1' "$PHASES" \
  || fail "PHASE_VOICE_STEM_CONCAT_V1 marker missing"
grep -q 'multi_v3_ffmpeg_concat_v1' "$PHASES" \
  || fail "phases.py must use multi_v3_ffmpeg_concat_v1 for eleven_v3 + markers"
grep -q 'coalesce_segments_for_v3_regen' "$PHASES" \
  || fail "phases.py must coalesce speech before ffmpeg concat"
grep -q '_build_silence_mp3' "$PHASES" \
  || fail "phases.py must inject exact ffmpeg silence"
grep -q 'ffmpeg_silence_min_s' "$LIB" \
  || fail "elevenlabs_tts.py must gate ffmpeg on silence duration"
grep -q 'prepend_accent_to_first_speech_chunk' "$LIB" \
  || fail "elevenlabs_tts.py must prepend accent to first chunk only"

python3 -m pytest "$TEST" "$CONCAT_TEST" -q

echo "[elevenlabs-tts-stitching] OK — source guards + pytest passed"
