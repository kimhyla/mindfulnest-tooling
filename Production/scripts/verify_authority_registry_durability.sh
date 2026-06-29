#!/usr/bin/env bash
# verify_authority_registry_durability.sh — STORYBOARD_AUTHORITY_REGISTRY_V1
#
# Multipass static gate: one authority per concept; detect duplicate export/enable predicates.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
SCRIPTS="$ROOT/Production/scripts"
DOC="$ROOT/Production/docs/STORYBOARD_AUTHORITY_REGISTRY_v1.md"
REGISTRY="$TOOLS/authority_registry.py"

fail() { echo "[authority-registry-durability] FATAL: $1" >&2; exit 1; }
warn() { echo "[authority-registry-durability] WARN: $1" >&2; }

echo "[authority-registry-durability] pass 1/7 — registry artifacts"
[[ -f "$DOC" ]] || fail "missing $DOC"
[[ -f "$REGISTRY" ]] || fail "missing authority_registry.py"
grep -q 'STORYBOARD_AUTHORITY_REGISTRY_V1' "$DOC" \
  || fail "doc missing STORYBOARD_AUTHORITY_REGISTRY_V1 marker"
grep -q 'AUTHORITY_REGISTRY_V1' "$REGISTRY" \
  || fail "authority_registry.py missing AUTHORITY_REGISTRY_V1"
grep -q 'kling_stitch_export_ready' "$REGISTRY" \
  || fail "machine registry missing kling_stitch_export_ready concept"

echo "[authority-registry-durability] pass 2/7 — shipped contract modules exist"
for pair in \
  "kling_stitch_readiness.py:beat_kling_stitch_export_ready" \
  "o3_job_status_contract.py:beat_o3_operator_busy" \
  "operator_workbench_contract.py:resolve_beat_still_scene_abs_path" \
  "magic_render_contract.py:MAGIC_RENDER_CONTRACT_VERSION" \
  "authority_registry.py:CONCEPTS"; do
  mod="${pair%%:*}"
  needle="${pair#*:}"
  [[ -f "$TOOLS/$mod" ]] || fail "missing contract module $mod"
  grep -q "$needle" "$TOOLS/$mod" || fail "$mod missing $needle"
done

SB="$TOOLS/storyboard-v2/src"
for pair in \
  "utils/klingStitchReadiness.ts:beatKlingStitchExportReady" \
  "o3JobStatusContract.ts:beatO3JobBusy" \
  "state/resolveAuthoritativeClientScope.ts:readAuthoritativeEventId" \
  "utils/stitchJobMediaHydrate.ts:stitchSlotTimelineDurMs" \
  "utils/stitchJobMediaHydrate.ts:resolveSlotPlaybackPreviewUrl" \
  "utils/bgStitchExport.ts:beatStitchExportReady"; do
  mod="${pair%%:*}"
  needle="${pair#*:}"
  [[ -f "$SB/$mod" ]] || fail "missing client module $mod"
  grep -q "$needle" "$SB/$mod" || fail "$mod missing $needle"
done

grep -q 'STITCH_SLOT_TIMELINE_ATOMIC_V1' "$TOOLS/server_handlers/stitch_editor.py" \
  || fail "stitch_editor missing timeline atomic marker"
grep -q 'ensure_stitch_slot_timeline_dur_ms' "$TOOLS/server_handlers/stitch_editor.py" \
  || fail "stitch_editor missing ensure_stitch_slot_timeline_dur_ms"
grep -q 'STITCH_SINGLE_OWNER_V1' "$TOOLS/server_handlers/stitch_editor.py" \
  || fail "stitch_editor missing STITCH_SINGLE_OWNER_V1"

echo "[authority-registry-durability] pass 3/7 — server delegation (no parallel stitch gates)"
grep -q 'return beat_kling_stitch_export_ready' "$TOOLS/beat_generator.py" \
  || fail "beat_has_stitch_export_clip must delegate to kling_stitch_readiness"
grep -q 'beat_has_stitch_export_clip' "$TOOLS/server_handlers/kling_o3.py" \
  || fail "kling_o3 export must use beat_has_stitch_export_clip"

echo "[authority-registry-durability] pass 4/7 — forbidden duplicate client export predicates"
if grep -E "kling_o3_status\s*===?\s*['\"]approved['\"]" "$SB/utils/bgStitchExport.ts" >/dev/null 2>&1; then
  fail "bgStitchExport.ts must not gate on kling_o3_status === approved (use beatKlingStitchExportReady)"
fi
if grep -q 'Approve Kling clip' "$TOOLS/storyboard-v2/src/components/BgTab.tsx"; then
  fail "BgTab regressed separate Approve Kling clip gate"
fi
grep -q 'allBeatsStitchExportReady' "$TOOLS/storyboard-v2/src/components/BgTab.tsx" \
  || fail "BgTab Send to Stitcher must use allBeatsStitchExportReady"
if grep -E "b\.job_busy\s*\|\|\s*b\.o3_current_job_id" "$SB/utils/bgStitchExport.ts" >/dev/null 2>&1; then
  fail "bgStitchExport.ts must use o3JobBlocksStitchExport (duplicate job_busy gate)"
fi
grep -q 'beat_kling_stitch_export_ready' "$TOOLS/beat_generator.py" \
  || fail "auto_pin must delegate to beat_kling_stitch_export_ready"
if grep -A6 'def auto_pin_approved_kling_o3_delivery' "$TOOLS/beat_generator.py" | grep -q 'kling_o3_status.*approved'; then
  fail "auto_pin_approved_kling_o3_delivery still gates on raw kling_o3_status"
fi
grep -q '_derived?.display_prompt' "$TOOLS/storyboard-v2/src/components/BgTab.tsx" \
  || fail "BgTab beatPromptText must prefer _derived.display_prompt"

echo "[authority-registry-durability] pass 5/7 — retroactive audit (strict subset)"
bash "$SCRIPTS/audit_authority_duplicates.sh" --strict-subset || fail "retroactive audit found duplicate authorities"

echo "[authority-registry-durability] pass 6/7 — sibling durability gates wired"
grep -q 'verify_kling_stitch_readiness_durability' "$SCRIPTS/verify_storyboard_session_durability.sh" \
  || fail "session durability must call verify_kling_stitch_readiness_durability"
grep -q 'verify_scope_client_authority_durability' "$SCRIPTS/verify_storyboard_session_durability.sh" \
  || fail "session durability must call verify_scope_client_authority_durability"
grep -q 'verify_authority_registry_durability' "$SCRIPTS/verify_storyboard_session_durability.sh" \
  || fail "session durability must call verify_authority_registry_durability (this script)"
grep -q 'verify_phase_watercolor_cue_authority_durability' "$SCRIPTS/verify_storyboard_session_durability.sh" \
  || fail "session durability must call verify_phase_watercolor_cue_authority_durability"
grep -q 'verify_operator_edit_surfaces_durability' "$SCRIPTS/verify_storyboard_session_durability.sh" \
  || fail "session durability must call verify_operator_edit_surfaces_durability"

GUARD="$SCRIPTS/check_storyboard_critical_features.sh"
grep -q 'KLING_STITCH_READINESS' "$GUARD" \
  || fail "regression guard missing KLING_STITCH_READINESS markers"

grep -q 'STITCH_SFX_PLAYBACK_TRUTH_V1' "$SB/utils/__tests__/stitchSfxPlaybackTruth.test.ts" \
  || fail "missing stitchSfxPlaybackTruth.test.ts contract tests"

echo "[authority-registry-durability] pass 7/7 — pytest + client parity tests"
export PYTHONPATH="${ROOT}/Production:${ROOT}/Production/tools${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest \
  "$TOOLS/tests/test_authority_registry_durability.py" \
  "$TOOLS/tests/test_kling_stitch_readiness.py" \
  "$TOOLS/tests/test_o3_job_status_contract_parity.py" \
  "$TOOLS/tests/test_operator_workbench_contract.py" \
  -q \
  || fail "authority registry pytest bundle failed"

(
  cd "$TOOLS/storyboard-v2"
  npx --yes vitest run src/utils/__tests__/klingStitchReadiness.test.ts
  node --experimental-strip-types --test \
    src/utils/__tests__/o3JobStatusContract.test.ts \
    src/utils/__tests__/stitchSlotTimelineAtomic.test.ts
) || fail "authority registry client test bundle failed"

echo "[authority-registry-durability] OK — registry + delegation + forbidden duplicates + pytest/vitest passed"
