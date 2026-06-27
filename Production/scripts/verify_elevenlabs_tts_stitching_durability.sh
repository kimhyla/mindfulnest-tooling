#!/usr/bin/env bash
# verify_elevenlabs_tts_stitching_durability.sh — Phase B multi-segment TTS uses
# ElevenLabs request stitching (previous_request_ids + next_text) so accent/prosody
# stay continuous across [pause]/[silence:Ns] splits.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
LIB="${REPO_ROOT}/Production/lib/elevenlabs_tts.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_elevenlabs_tts_stitching.py"

fail() {
  echo "[elevenlabs-tts-stitching] FAIL: $1" >&2
  exit 1
}

[[ -f "$PHASES" ]] || fail "missing phases.py"
[[ -f "$LIB" ]] || fail "missing elevenlabs_tts.py"
[[ -f "$TEST" ]] || fail "missing test_elevenlabs_tts_stitching.py"

grep -q 'call_elevenlabs_tts' "$PHASES" \
  || fail "phases.py must import call_elevenlabs_tts for multi-segment regen"
grep -q 'previous_request_ids' "$PHASES" \
  || fail "phases.py multi-segment loop must pass previous_request_ids"
grep -q 'model_supports_request_stitching' "$PHASES" \
  || fail "phases.py must gate multi-segment TTS on model stitching support"
grep -q 'build_single_call_tts_script' "$PHASES" \
  || fail "phases.py must use single-call v3 path when stitching unsupported"
grep -q 'single_call_v3' "$PHASES" \
  || fail "phases.py must report single_call_v3 telemetry for eleven_v3"
grep -q 'tts_stitching' "$PHASES" \
  || fail "phases.py regen response must include tts_stitching telemetry"
grep -q 'build_tts_payload' "$LIB" \
  || fail "elevenlabs_tts.py must expose build_tts_payload"
grep -q 'extract_request_id' "$LIB" \
  || fail "elevenlabs_tts.py must capture request-id header"

python3 -m pytest "$TEST" -q

echo "[elevenlabs-tts-stitching] OK — source guards + pytest passed"
