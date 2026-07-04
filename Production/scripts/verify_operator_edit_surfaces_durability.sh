#!/usr/bin/env bash
# verify_operator_edit_surfaces_durability.sh — OPERATOR_EDIT_AUTHORITY_V1
# Full operator edit surface gate: BG, Phase A/B, Stitcher, Storyboard — all events.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SB="$ROOT/Production/tools/storyboard-v2/src"
REG="$ROOT/Production/tools/authority_registry.py"
SPEC="$ROOT/Production/docs/TECH_SPEC_OPERATOR_EDIT_AUTHORITY_V1.md"
MERGE="$SB/utils/operatorEditMerge.ts"
MERGE_TEST="$SB/utils/__tests__/operatorEditMerge.test.ts"

fail() { echo "[operator-edit-surfaces] FATAL: $1" >&2; exit 1; }

echo "[operator-edit-surfaces] pass 1/4 — canonical primitive + spec"
[[ -f "$SPEC" ]] || fail "missing $SPEC"
[[ -f "$MERGE" ]] || fail "missing operatorEditMerge.ts"
[[ -f "$MERGE_TEST" ]] || fail "missing operatorEditMerge.test.ts"
grep -q 'OPERATOR_EDIT_AUTHORITY_V1' "$MERGE" || fail "operatorEditMerge missing marker"
grep -q 'mergeOperatorFieldOnHydrate' "$MERGE" || fail "missing mergeOperatorFieldOnHydrate"
grep -q 'mergeOperatorArrayOnHydrate' "$MERGE" || fail "missing mergeOperatorArrayOnHydrate"
grep -q 'OPERATOR_EDIT_SURFACES' "$REG" || fail "authority_registry missing OPERATOR_EDIT_SURFACES"

echo "[operator-edit-surfaces] pass 2/4 — Phase A/B surfaces"
grep -q 'usePhaseWatercolorCues' "$SB/components/phase/PhaseProducer.tsx" \
  || fail "PhaseProducer must use usePhaseWatercolorCues"
grep -q 'usePhaseStemCut' "$SB/components/phase/PhaseProducer.tsx" \
  || fail "PhaseProducer must use usePhaseStemCut"
grep -q 'usePhaseAmbientPreset' "$SB/components/phase/PhaseProducer.tsx" \
  || fail "PhaseProducer must use usePhaseAmbientPreset"
grep -q 'usePhaseBaseClipPicker' "$SB/components/phase/PhaseProducer.tsx" \
  || fail "PhaseProducer must use usePhaseBaseClipPicker"
grep -q 'mergeOperatorFieldOnHydrate' "$SB/hooks/usePhaseBaseClipPicker.ts" \
  || fail "usePhaseBaseClipPicker must use mergeOperatorFieldOnHydrate"
grep -q 'usePhaseBaseClipPicker.test.ts' "$ROOT/Production/scripts/verify_operator_edit_surfaces_durability.sh" \
  || fail "operator edit gate must run usePhaseBaseClipPicker vitest"
grep -q 'PHASE-CLIP-HYDRATE-1' "$ROOT/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts" \
  || fail "missing PHASE-CLIP-HYDRATE-1 marker"
grep -q 'AMBIENT-HYDRATE-1' "$ROOT/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts" \
  || fail "missing AMBIENT-HYDRATE-1 e2e"
grep -q 'useProtectedPromptField' "$SB/components/phase/PhaseProducer.tsx" \
  || fail "PhaseProducer script must use useProtectedPromptField"
grep -q 'PHASE_STEM_CUT_AUTHORITY_V1' "$SB/hooks/usePhaseStemCut.ts" \
  || fail "usePhaseStemCut missing marker"
grep -q 'mergeWatercolorCuesOnHydrate' "$SB/utils/phaseWatercolorCuesAuthority.ts" \
  || fail "watercolor authority must delegate to operatorEditMerge"
grep -q 'operatorEditMerge' "$SB/utils/phaseWatercolorCuesAuthority.ts" \
  || fail "phaseWatercolorCuesAuthority must import operatorEditMerge"
grep -q 'data-operator-edit-authority' "$SB/components/phase/PhaseProducer.tsx" \
  || fail "PhaseProducer missing data-operator-edit-authority marker"
if grep -q 'stateSlice\.watercolor_cues' "$SB/components/phase/PhaseProducer.tsx"; then
  fail "PhaseProducer must not read stateSlice.watercolor_cues"
fi
if grep -q 'setScriptDraft' "$SB/components/phase/PhaseProducer.tsx"; then
  fail "PhaseProducer must not use scriptDraft state (useProtectedPromptField)"
fi

echo "[operator-edit-surfaces] pass 3/4 — Beat Gen + Stitcher surfaces"
grep -q 'useProtectedPromptField' "$SB/components/BgTab.tsx" \
  || fail "BgTab must use useProtectedPromptField"
grep -q 'mergeBeatsOnSessionHydrate' "$SB/state/bgSessionStore.ts" \
  || fail "bgSessionStore must use mergeBeatsOnSessionHydrate"
if grep -q 'preserveRefBoxesOnServerBeatMerge' "$SB/state/bgSessionStore.ts"; then
  fail "bgSessionStore must not call preserveRefBoxesOnServerBeatMerge directly"
fi
grep -q 'useBgO3TrimNumericDraft' "$SB/components/BgTab.tsx" \
  || fail "BgTab must use useBgO3TrimNumericDraft"
grep -q 'useBgO3CutSession' "$SB/components/BgTab.tsx" \
  || fail "BgTab must use useBgO3CutSession"
grep -q 'o3TrimApplyIsBaked' "$SB/components/BgTab.tsx" \
  || fail "BgTab must use o3TrimApplyIsBaked (export_baked + trim_baked contract)"
grep -q 'o3TrimApplyContract' "$SB/components/BgTab.tsx" \
  || fail "BgTab must import o3TrimApplyContract"
grep -q 'materializedCut' "$SB/components/BgTab.tsx" \
  || fail "BgTab O3 tile must use materializedCut playback anchor (no skipPreviewClearRef)"
grep -q 'pathappPatch' "$SB/components/BeatMagicButtons.tsx" \
  || fail "BeatMagicButtons must clear magic via pathappPatch"
grep -q 'storyboard_clear_magic_video' "$SB/components/BeatMagicButtons.tsx" \
  || fail "BeatMagicButtons must use storyboard_clear_magic_video catalog endpoint"
grep -q 'export_baked' "$SB/utils/o3TrimApplyContract.ts" \
  || fail "o3TrimApplyContract must handle export_baked"
grep -q 'shouldPreserveBgO3CutDraft' "$SB/components/bg/BgO3CutOverlay.tsx" \
  || fail "BgO3CutOverlay must preserve draft during drag"
grep -q 'mergeStitchAmbientBedOnHydrate' "$SB/utils/stitchSlotDurableMerge.ts" \
  || fail "stitchSlotDurableMerge missing mergeStitchAmbientBedOnHydrate"
grep -q 'beginStitchAmbientPatch' "$SB/components/StitcherTab.tsx" \
  || fail "StitcherTab must track ambient patch in flight"
grep -q 'useStoryboardDialogueField' "$SB/components/StoryboardTab.tsx" \
  || fail "StoryboardTab must use useStoryboardDialogueField"
grep -q 'useStoryboardTrimFields' "$SB/components/StoryboardTab.tsx" \
  || fail "StoryboardTab must use useStoryboardTrimFields"
grep -q 'mergeStitchJobSlotsClientPatch' "$SB/components/StitcherTab.tsx" \
  || fail "StitcherTab must use mergeStitchJobSlotsClientPatch"
grep -q 'STITCH_SAVE_REFRESH_LOCAL_CUES_V1' "$SB/components/StitcherTab.tsx" \
  || fail "StitcherTab missing STITCH_SAVE_REFRESH_LOCAL_CUES_V1"

for surface_id in \
  phase_watercolor_cue_geometry \
  phase_stem_cut_geometry \
  phase_script_draft \
  phase_ambient_preset \
  phase_base_clip_picker \
  stitch_sfx_cue_geometry \
  bg_beat_prompt_field \
  bg_beat_ref_boxes; do
  grep -q "id=\"${surface_id}\"" "$REG" || fail "OPERATOR_EDIT_SURFACES missing $surface_id"
done

echo "[operator-edit-surfaces] pass 4/4 — vitest"
(
  cd "$ROOT/Production/tools/storyboard-v2"
  node --experimental-strip-types --test "$MERGE_TEST"
  node --experimental-strip-types --test "$SB/utils/__tests__/phaseWatercolorCuesAuthority.test.ts"
  node --experimental-strip-types --test "$SB/hooks/__tests__/usePhaseBaseClipPicker.test.ts"
  node --experimental-strip-types --test "$SB/hooks/__tests__/useBgO3TrimNumericDraft.test.ts"
  node --experimental-strip-types --test "$SB/utils/__tests__/bgSessionBeatMerge.test.ts"
  node --experimental-strip-types --test "$SB/utils/__tests__/bgO3CutSession.test.ts"
  node --experimental-strip-types --test "$SB/utils/__tests__/o3TrimApplyContract.test.ts"
  node --experimental-strip-types --test "$SB/utils/__tests__/stitchSlotDurableMerge.test.ts"
) || fail "operator edit vitest failed"

echo "[operator-edit-surfaces] OK — full operator surface contract"
