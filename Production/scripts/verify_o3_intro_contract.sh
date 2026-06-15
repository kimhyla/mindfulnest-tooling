#!/usr/bin/env bash
# O3 + intro contract gate — run before deploy merge or after backup restore.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
echo "[o3-intro-contract] beat_generator deploy-backup contract..."
python3 Production/scripts/verify_deploy_backup_contract.py --beat-generator Production/tools/beat_generator.py
echo "[o3-intro-contract] pytest O3 + intro suite..."
python3 -m pytest \
  Production/tools/tests/test_beat_generator_o3_sidecar_contract.py \
  Production/tools/tests/test_o3_job_state_reliability.py \
  Production/tools/tests/test_o3_stuck_job_recovery.py \
  Production/tools/tests/test_arlo_canonical_registry.py \
  Production/tools/tests/test_intro_export_api_contract.py \
  Production/tools/tests/test_teleport_intro_canonical.py \
  Production/tools/tests/test_intro_final_pair_fade.py \
  Production/tools/tests/test_stitch_cache_and_boundaries.py \
  Production/tools/tests/test_stitch_canonical_job.py \
  Production/tools/tests/test_beat_ref_drop_lock.py \
  Production/tools/tests/test_library_sources_immutable.py \
  Production/tools/tests/test_still_insert_render.py \
  Production/tools/tests/test_bg_add_beat_sidecar_lock.py \
  Production/tools/tests/test_insert_beat_form_first.py \
  Production/tools/tests/test_o3_element_pipeline_duration.py \
  Production/tools/tests/test_kling_voice_bind.py \
  Production/tools/tests/test_kling_o3_duration_extraction.py \
  Production/tools/tests/test_element_voice_alignment.py \
  -q
echo "[o3-intro-contract] all gates passed"
