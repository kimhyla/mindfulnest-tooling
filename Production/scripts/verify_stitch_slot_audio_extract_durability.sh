#!/usr/bin/env bash
# verify_stitch_slot_audio_extract_durability.sh — slot waveform extract/mix duration guards.
#
# Incident 2026-06-13: Phase A port to Stitcher showed 38s video but ~16s waveform audio
# (stale truncated stitch_audio_*.mp3 cache) — linked playback cut off mid-clip.
#
# LINEAGE-1  probe video before extract; reject cache < 85% of video duration
# LINEAGE-2  ambient mix uses video duration (not truncated base extract)
# LINEAGE-3  mix cache validated before serve; bust hash includes video_dur_ms
# LINEAGE-4  phase/bg export preflight probes file + blocks stale Phase A lineage
# LINEAGE-5  client refuses extract when duration_ms drifts from video_dur_ms

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
FF="${REPO_ROOT}/Production/tools/credentials_lib/ffmpeg_stitch.py"
WAVEFORM="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/StitcherSlotWaveform.tsx"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_slot_audio_extract_durability.py"

fail() {
  echo "[stitch-slot-audio-extract-durability] FAIL: $1" >&2
  exit 1
}

for f in "$EDITOR" "$FF" "$WAVEFORM" "$TEST"; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1' "$EDITOR" \
  || fail "STITCH_SLOT_MEDIA_LINEAGE_DURABILITY_V1 marker missing"
grep -q 'stitch_audio_cache_is_valid' "$FF" \
  || fail "stitch_audio_cache_is_valid missing in ffmpeg_stitch.py"
grep -q 'STITCH_SLOT_AUDIO_EXTRACT_TRUNCATED' "$EDITOR" \
  || fail "extract truncation error missing (LINEAGE-1)"
grep -q 'expected_video_dur_ms' "$EDITOR" \
  || fail "mix must use expected_video_dur_ms (LINEAGE-2)"
grep -q 'stitch_slot_export_media_preflight' "$EDITOR" \
  || fail "export preflight missing (LINEAGE-4)"
grep -q 'audio duration' "$WAVEFORM" \
  || fail "client duration mismatch guard missing (LINEAGE-5)"

python3 -m pytest "$TEST" -q

echo "[stitch-slot-audio-extract-durability] OK — source guards + pytest passed"
