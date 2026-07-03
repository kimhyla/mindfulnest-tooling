#!/usr/bin/env bash
# CROSS_PIPELINE_G1_G8_CLOSURE_V1 — meta gate for operator truth stack closure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS="$ROOT/Production/scripts"
SB="$ROOT/Production/tools/storyboard-v2"
MATRIX="$ROOT/Production/docs/OPERATOR_UX_SYMPTOM_MATRIX_v1.md"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

for g in \
  verify_o3_job_truth_durability \
  verify_o3_failed_redo_heal_durability \
  verify_o3_subprocess_lifecycle_durability \
  verify_beatgen_truth_stack_durability \
  verify_event_library_scope_durability \
  verify_library_cache_coherence_durability \
  verify_bg_o3_stitch_lineage_client_durability \
  verify_stitch_export_trim_authority_durability; do
  bash "$SCRIPTS/${g}.sh" && mark "$g" || err "$g"
done

python3 -m pytest "$ROOT/Production/tools/tests/test_o3_job_truth_matrix.py" \
  "$ROOT/Production/tools/tests/test_o3_subprocess_lifecycle.py" \
  "$ROOT/Production/tools/tests/test_sidecar_concurrent_stress.py" \
  "$ROOT/Production/tools/tests/test_cr_library_milestone_scope_parity.py" -q \
  && mark 'cross-pipeline pytest bundle' \
  || err 'cross-pipeline pytest bundle'

for spec in \
  o3_failed_redo_restores_prior_clip.spec.ts \
  o3_restart_survival.spec.ts \
  library_scope_parity.spec.ts \
  directus_has_crop_disk_fallback.spec.ts \
  library_cache_coherence.spec.ts \
  trim_then_export_shows_new_clip.spec.ts; do
  test -f "$SB/e2e/$spec" && mark "e2e $spec present" || err "missing e2e $spec"
  if grep -q 'test\.skip' "$SB/e2e/$spec" 2>/dev/null; then
    err "test.skip forbidden in $spec"
  fi
done

grep -q 'LIBRARY_CLIENT_CACHE_COHERENCE_V1' "$ROOT/Production/tools/storyboard-v2/src/utils/libraryCachePolicy.ts" \
  && grep -q 'invalidateLibrarySessionCache(eventId)' "$ROOT/Production/tools/storyboard-v2/src/components/LibraryPanel.tsx" \
  && mark 'G7 upload wired to invalidateLibrarySessionCache' \
  || err 'G7 upload missing invalidateLibrarySessionCache'

if [[ "${MN_FAF_REQUIRE_MATRIX_SHIPPED:-0}" == "1" ]]; then
  for id in G1 G2 G3 G4 G5 G6 G7 G8; do
    if grep -E "\\| ${id} \\|" "$MATRIX" | grep -qE 'in_progress|partial|spec-only'; then
      err "matrix ${id} not shipped"
    fi
  done
  mark 'matrix G1-G8 shipped (MN_FAF_REQUIRE_MATRIX_SHIPPED=1)'
fi

exit "$fail"
