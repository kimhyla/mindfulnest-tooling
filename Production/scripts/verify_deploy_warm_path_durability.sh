#!/usr/bin/env bash
# verify_deploy_warm_path_durability.sh — G4 warm-path deploy contract (RC14)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPTS="$ROOT/Production/scripts"
SB="$ROOT/Production/tools/storyboard-v2"
E2E="$SB/e2e/stitch_sfx_playback_truth_live.spec.ts"
MARKER_DIR="$ROOT/Production/.deploy_mux_warm"

fail() { echo "[deploy-warm-path-durability] FATAL: $1" >&2; exit 1; }

[[ -x "$SCRIPTS/deploy_mux_warm_g4_pre.sh" ]] || fail "missing deploy_mux_warm_g4_pre.sh"
[[ -f "$SCRIPTS/deploy_mux_warm_g4_pre.py" ]] || fail "missing deploy_mux_warm_g4_pre.py"
grep -q "DEPLOY_MUX_WARM_G4_PRE_V1" "$SCRIPTS/deploy_mux_warm_g4_pre.py" \
  || fail "deploy_mux_warm_g4_pre.py missing marker comment"
grep -q "Event_2_stitch" "$SCRIPTS/deploy_mux_warm_g4_pre.py" \
  || fail "deploy_mux_warm_g4_pre.py must drain Event_2_stitch before milestone ops (contention)"
grep -q "MN_MUX_WARM_RESTART" "$SCRIPTS/deploy_mux_warm_g4_pre.sh" \
  || fail "deploy_mux_warm_g4_pre.sh must gate restart behind MN_MUX_WARM_RESTART (RC14d optional)"

grep -q "deploy_mux_warm_g4_pre" "$SCRIPTS/verify_stitch_sfx_playback_truth_live_e2e.sh" \
  || fail "verify_stitch_sfx_playback_truth_live_e2e.sh must call g4-pre"

grep -q "DEPLOY_MUX_WARM_G4_PRE_V1" "$E2E" \
  || fail "live E2E must reference DEPLOY_MUX_WARM_G4_PRE_V1 fast-fail"

grep -q "ensureMuxPreviewReady" "$E2E" \
  && grep -q "beforeAll" "$E2E" \
  && grep -A20 "beforeAll" "$E2E" | grep -q "ensureMuxPreviewReady" \
  && fail "beforeAll must not call ensureMuxPreviewReady — use g4-pre warm marker"

grep -q "STITCH_SAVE_ASYNC_ARTIFACTS_V1" "$SCRIPTS/deploy_mux_warm_g4_pre.py" \
  || grep -q "STITCH_SAVE_ASYNC_ARTIFACTS_V1" "$ROOT/Production/tools/server_handlers/stitch_artifact_build.py" \
  || fail "g4-pre / stitch save must use STITCH_SAVE_ASYNC_ARTIFACTS_V1 async ambient rebuild"
grep -q "STITCH_SAVE_ASYNC_ARTIFACTS_V1" "$ROOT/Production/tools/server_handlers/stitch_editor.py" \
  || fail "stitch_editor must reference STITCH_SAVE_ASYNC_ARTIFACTS_V1"

grep -q "STITCH_ARTIFACT_ORCHESTRATOR_V1" "$ROOT/Production/tools/server_handlers/stitch_artifact_build.py" \
  || fail "stitch_artifact_build must export STITCH_ARTIFACT_ORCHESTRATOR_V1"
grep -q "submit_stitch_artifact_build_plan" "$ROOT/Production/tools/server_handlers/stitch_editor.py" \
  || fail "save_job/preview must use submit_stitch_artifact_build_plan"
grep -q "STITCH_ARTIFACT_ORCHESTRATOR_V1" "$SB/src/utils/stitchArtifactBuildPoll.ts" \
  || fail "client must poll artifact_build (stitchArtifactBuildPoll.ts)"

grep -q "deploy_mux_warm_g4_pre" "$SCRIPTS/deploy_storyboard_v59.sh" \
  || fail "deploy_storyboard_v59.sh must invoke g4-pre before g.4 E2E"

[[ -d "$MARKER_DIR" ]] || mkdir -p "$MARKER_DIR"

echo "[deploy-warm-path-durability] OK — G4 warm-path scripts + E2E fast-fail wired"
