#!/usr/bin/env bash
# verify_video_quality_bake_durability.sh — Bake final MP4 must stay on VIDEO_QUALITY_V1 + V2 lean profile.
#
# VQ-BAKE-1  stitch_editor bake core calls encode_module_final_lean with MODULE_FINAL_LEAN_DELIVERY_CURRENT
# VQ-BAKE-2  video_delivery module_final_lean uses gradfun + slow preset (not legacy medium-only path)
# VQ-BAKE-3  pytest contract tests for bake wiring + bitrate cap
#
# Called from verify_o3_intro_contract.sh (deploy gate).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VD="${REPO_ROOT}/Production/tools/video_delivery.py"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
FF="${REPO_ROOT}/Production/tools/credentials_lib/ffmpeg_stitch.py"

fail() {
  echo "[video-quality-bake-durability] FAIL: $1" >&2
  exit 1
}

for f in "$VD" "$EDITOR" "$FF"; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'MODULE_FINAL_LEAN_DELIVERY_V3' "$VD" \
  || fail "video_delivery must define MODULE_FINAL_LEAN_DELIVERY_V3 (VQ-BAKE-1)"
grep -q 'MODULE_FINAL_LEAN_DELIVERY_CURRENT = MODULE_FINAL_LEAN_DELIVERY_V3' "$VD" \
  || fail "MODULE_FINAL_LEAN_DELIVERY_CURRENT must point at V3 (VQ-BAKE-1)"
grep -q 'use_lean_quality_encode' "$VD" \
  || fail "video_delivery must branch use_lean_quality_encode for module_final_lean (VQ-BAKE-2)"
grep -q 'MODULE_FINAL_LEAN_GRADFUN_VF' "$VD" \
  || fail "video_delivery bake VF must include lean gradfun (VQ-BAKE-2)"
grep -q 'VIDEO_QUALITY_PRESET_BAKE' "$VD" \
  || fail "video_delivery bake must use VIDEO_QUALITY_PRESET_BAKE slow preset (VQ-BAKE-2)"
grep -q 'encode_module_final_lean' "$EDITOR" \
  || fail "stitch_editor bake must call encode_module_final_lean (VQ-BAKE-1)"
grep -q 'MODULE_FINAL_LEAN_DELIVERY_CURRENT' "$EDITOR" \
  || fail "stitch_editor bake must import MODULE_FINAL_LEAN_DELIVERY_CURRENT (VQ-BAKE-1)"
grep -q 'VIDEO_QUALITY_V1' "$EDITOR" \
  || fail "stitch_editor bake progress must label VIDEO_QUALITY_V1 (VQ-BAKE-1)"
grep -q 'delivery_profile": MODULE_FINAL_LEAN_DELIVERY_CURRENT' "$EDITOR" \
  || fail "stitch_editor bake response must return delivery_profile current (VQ-BAKE-1)"
grep -q '"v7"' "$FF" || grep -q 'v7' "$FF" \
  || fail "ffmpeg_stitch normalize recipe must be v7 (VQ-BAKE-3)"

cd "$REPO_ROOT/Production/tools"
python3 -m pytest \
  tests/test_module_final_lean_delivery.py \
  tests/test_video_encode_policy.py \
  tests/test_playback_video_policy.py \
  tests/test_waveform_linked_video_match_audio.py \
  -q

echo "[video-quality-bake-durability] OK — bake V3 wiring + VQ pytest suite"
