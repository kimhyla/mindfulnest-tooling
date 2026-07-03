#!/usr/bin/env bash
# verify_speech_loudnorm_durability.sh — AUTO_LOUDNORM_V1 gate
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
SPEC="$ROOT/Production/docs/TECH_SPEC_AUTO_LOUDNORM_V1.md"

fail() { echo "[speech-loudnorm] FATAL: $1" >&2; exit 1; }

echo "[speech-loudnorm] pass 1/3 — spec + module marker"
[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_AUTO_LOUDNORM_V1.md"
grep -q "STITCH_SPEECH_LOUDNORM_V1" "$SPEC" || fail "spec missing recipe token"
grep -q "apply_speech_loudnorm_to_mp4" "$TOOLS/server_handlers/speech_loudnorm.py" \
  || fail "missing speech_loudnorm module"

echo "[speech-loudnorm] pass 2/3 — layer A/B hooks (FF-042 dry-authority)"
grep -q "KLING_O3_EXPORT_BG_PASSTHROUGH_V1" "$TOOLS/beat_generator.py" \
  || fail "missing FF-042 passthrough marker in beat export"
grep -q "apply_speech_loudnorm_export_beat_clip" "$TOOLS/beat_generator.py" \
  && fail "Layer A must not run on Send to Stitcher export (FF-042)"
grep -q "apply_speech_loudnorm_to_mp4" "$TOOLS/server_handlers/stitch_slot_playback.py" \
  || fail "missing loudnorm in slot playback bake path"
grep -q "apply_speech_loudnorm_to_mp4" "$TOOLS/production_server.py" \
  || fail "missing Layer B pipeline hook"

echo "[speech-loudnorm] pass 3/3 — pytest"
(
  cd "$TOOLS"
  python3 -m pytest tests/test_speech_loudnorm_v1.py -q
)

echo "[speech-loudnorm] OK"
