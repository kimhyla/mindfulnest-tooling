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
  Production/tools/tests/test_sidecar_io_durability.py \
  Production/tools/tests/test_o3_element_pipeline_duration.py \
  Production/tools/tests/test_kling_voice_bind.py \
  Production/tools/tests/test_kling_o3_duration_extraction.py \
  Production/tools/tests/test_element_voice_alignment.py \
  Production/tools/tests/test_arlo_intro_canonical_hydrate.py \
  Production/tools/tests/test_intro_mirror_write_path_hydrate.py \
  Production/tools/tests/test_beat_plan_draft_autosave.py \
  Production/tools/tests/test_o3_prompt_box_law.py \
  Production/tools/tests/test_o3_verbatim_prompt_durability.py \
  Production/tools/tests/test_o3_generation_intent_commit.py \
  Production/tools/tests/test_o3_stale_intent_reconcile.py \
  Production/tools/tests/test_magic_render_contract_durability.py \
  Production/tools/tests/test_magic_golden_beat01_replay.py \
  Production/tools/tests/test_voice_first_generate_mode.py \
  Production/tools/tests/test_lipsync_staging_durability.py \
  Production/tools/tests/test_lipsync_hosting_preflight.py \
  Production/tools/tests/test_lipsync_public_host.py \
  -q
echo "[o3-intro-contract] visible magic contract..."
bash Production/scripts/verify_visible_magic_contract.sh
