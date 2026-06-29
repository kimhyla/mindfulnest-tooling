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
grep -q 'preserveRefBoxesOnServerBeatMerge' "$SB/state/bgSessionStore.ts" \
  || fail "bgSessionStore must preserve ref boxes on merge"
grep -q 'mergeStitchJobSlotsClientPatch' "$SB/components/StitcherTab.tsx" \
  || fail "StitcherTab must use mergeStitchJobSlotsClientPatch"
grep -q 'STITCH_SAVE_REFRESH_LOCAL_CUES_V1' "$SB/components/StitcherTab.tsx" \
  || fail "StitcherTab missing STITCH_SAVE_REFRESH_LOCAL_CUES_V1"

for surface_id in \
  phase_watercolor_cue_geometry \
  phase_stem_cut_geometry \
  phase_script_draft \
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
) || fail "operator edit vitest failed"

echo "[operator-edit-surfaces] OK — full operator surface contract"
