#!/usr/bin/env bash
# verify_stitch_export_four_files_slot_apply_durability.sh
# Send to Stitcher (Beat Gen + Phase) must bake four-files playback onto stitch slot.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PLAYBACK="${REPO_ROOT}/Production/tools/server_handlers/stitch_slot_playback.py"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
KLING="${REPO_ROOT}/Production/tools/server_handlers/kling_o3.py"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_export_four_files_slot_apply.py"

fail() {
  echo "[stitch-export-four-files-slot-apply] FAIL: $1" >&2
  exit 1
}

for f in "$PLAYBACK" "$EDITOR" "$KLING" "$PHASES" "$TEST"; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -q 'STITCH_EXPORT_FOUR_FILES_SLOT_APPLY_V1' "$PLAYBACK" \
  || fail "slot apply marker missing"
grep -q 'def assert_four_files_export_slot_applied' "$PLAYBACK" \
  || fail "assert_four_files_export_slot_applied missing"
grep -q 'dry_str = str(dry_video_path)' "$PLAYBACK" \
  || fail "normalize must receive str path (PosixPath regression)"
grep -q 'bake_and_persist_slot_playback_mp4' "$EDITOR" \
  || fail "event slot upsert must bake four-files playback"
grep -q 'persist_dry_authority_slot_export' "$EDITOR" \
  && fail "FF-042 dry-only upsert must not be used for event slots"
grep -q 'def verify_event_slot_four_files_export_applied' "$PLAYBACK" \
  || fail "verify_event_slot_four_files_export_applied missing"
grep -q 'verify_event_slot_four_files_export_applied' "$KLING" \
  || fail "Beat Gen export must use shared four-files slot gate"
grep -q 'STITCH_EXPORT_SLOT_NOT_APPLIED' "$KLING" \
  || fail "Beat Gen export must fail loud when slot not applied"
grep -q 'verify_event_slot_four_files_export_applied' "$PHASES" \
  || fail "Phase export must verify four-files slot apply"
grep -q 'STITCH_PLAYBACK_BAKE_FAILED' "$PHASES" \
  || fail "Phase export must fail loud on playback bake errors"
grep -q 'server_mutation_gate_reason' "$PHASES" \
  || fail "Phase export must reject requests during server restart"
grep -q 'stitch_upsert_event_slot' "$PHASES" \
  || fail "Phase export must call stitch_upsert_event_slot"

python3 -m pytest "$TEST" -q

echo "[stitch-export-four-files-slot-apply] OK — four-files slot apply gates + pytest passed"
