#!/usr/bin/env bash
# verify_stitch_slot_export_full_media_durability.sh — full slot video on all tab exports.
#
# EXPORT-FULL-1  stitch_upsert_event_slot runs export preflight before persist
# EXPORT-FULL-2  video_dur_ms written from on-disk probe (not caller guess)
# EXPORT-FULL-3  Beat Gen export-to-stitcher → upsert (intro + resolution)
# EXPORT-FULL-4  Phase export_stitcher → upsert (phase_a + phase_b)
# EXPORT-FULL-5  mp4 playability + decode smoke on export target

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
KLING="${REPO_ROOT}/Production/tools/server_handlers/kling_o3.py"
ENDPOINTS="${REPO_ROOT}/Production/tools/storyboard-v2/src/api/endpoints.ts"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_slot_export_full_media_durability.py"

fail() {
  echo "[stitch-slot-export-full-media-durability] FAIL: $1" >&2
  exit 1
}

for f in "$EDITOR" "$PHASES" "$KLING" "$ENDPOINTS" "$TEST"; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'STITCH_SLOT_EXPORT_FULL_MEDIA_V1' "$EDITOR" \
  || fail "STITCH_SLOT_EXPORT_FULL_MEDIA_V1 marker missing"
grep -q 'stitch_slot_export_media_preflight' "$EDITOR" \
  || fail "export preflight helper missing"
grep -q 'return job_name, probed_ms, export_warnings' "$EDITOR" \
  || fail "upsert must return probed duration (EXPORT-FULL-2)"
grep -q 'mp4_decodes_cleanly' "$EDITOR" \
  || fail "export must decode-smoke MP4 (EXPORT-FULL-5)"
grep -q 'bg_export_to_stitcher' "$ENDPOINTS" \
  || fail "Beat Gen export endpoint missing (EXPORT-FULL-3)"
grep -q 'phase_export_stitcher' "$ENDPOINTS" \
  || fail "Phase export endpoint missing (EXPORT-FULL-4)"
grep -q 'stitch_upsert_event_slot' "$KLING" \
  || fail "Beat Gen must call stitch_upsert_event_slot"
grep -q 'stitch_upsert_event_slot' "$PHASES" \
  || fail "Phase export must call stitch_upsert_event_slot"
grep -q 'bake_and_persist_slot_playback_mp4' "$EDITOR" \
  || fail "event slots must use four-files bake (FF-036)"
grep -q 'STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1' "$REPO_ROOT/Production/tools/server_handlers/stitch_slot_playback.py" \
  || fail "STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1 marker missing"

python3 -m pytest "$TEST" -q
bash "$SCRIPT_DIR/verify_stitch_export_four_files_slot_apply_durability.sh"

echo "[stitch-slot-export-full-media-durability] OK — all four tab export gates + pytest passed"
