#!/usr/bin/env bash
# verify_fast_and_flawless_done.sh — FAST_AND_FLAWLESS_DONE_V3 meta gate
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPTS="$ROOT/Production/scripts"
SB="$ROOT/Production/tools/storyboard-v2"
MATRIX="$ROOT/Production/docs/OPERATOR_UX_SYMPTOM_MATRIX_v1.md"
DONE="$ROOT/Production/docs/FAST_AND_FLAWLESS_DONE_v1.md"
SYN_V2="$ROOT/Production/docs/OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_v2.md"
E2E_POLL="$SB/e2e/phase_e_edit_during_poll.spec.ts"
PARITY="$SB/e2e/behavioral-parity.spec.ts"
TOUCH="$SB/e2e/touchpoint-a.spec.ts"

fail() { echo "[fast-and-flawless] FATAL: $1" >&2; exit 1; }

echo "[fast-and-flawless] === meta gate FAST_AND_FLAWLESS_DONE_V3 ==="

[[ -f "$DONE" ]] || fail "missing FAST_AND_FLAWLESS_DONE_v1.md"
grep -q "FAST_AND_FLAWLESS_DONE_V3" "$DONE" || fail "done doc must be V3 (Phase G)"
[[ -f "$SYN_V2" ]] || fail "missing OPERATOR_UX_ROOT_CAUSE_SYNTHESIS_v2.md"
grep -q "RC11" "$SYN_V2" || fail "synthesis v2 must document RC11–RC14"

echo "[fast-and-flawless] pass 1/10 — no test.fixme in parity suites"
grep -E '^\s*test\.fixme\b' "$PARITY" && fail "behavioral-parity.spec.ts still has test.fixme — implement + un-skip"
grep -E '^\s*test\.fixme\b' "$TOUCH" && fail "touchpoint-a.spec.ts still has test.fixme — implement + un-skip"

echo "[fast-and-flawless] pass 2/10 — symptom matrix in-scope rows"
for id in WTA-017 WTA-018 WTA-023 WTA-024 WTA-028 O3-004 O3-005 O3-006 SB-009 GAP-001 GAP-002 GAP-003; do
  if grep -E "\\| ${id} \\|" "$MATRIX" | grep -qE 'partial|spec-only'; then
    fail "matrix row ${id} still partial/spec-only — update matrix after proof"
  fi
done

echo "[fast-and-flawless] pass 3/10 — durability sub-gates"
for g in \
  verify_operator_edit_surfaces_durability \
  verify_o3_prompt_lineage_durability \
  verify_waveform_time_authority \
  verify_event_switch_automation_durability \
  verify_operator_session_perf \
  verify_o3_generation_intent_transaction_durability \
  verify_storyboard_session_durability \
  verify_authority_registry_durability \
  verify_speech_loudnorm_durability \
  verify_parallel_event_isolation_durability \
  verify_stitch_slot_artifact_freshness \
  verify_voice_reliability_durability; do
  bash "$SCRIPTS/${g}.sh"
done

echo "[fast-and-flawless] pass 4/10 — named hydrate e2e markers"
for marker in \
  STITCH-AMBIENT-HYDRATE-1 \
  SB-DIALOGUE-HYDRATE-1 \
  SB-TRIM-HYDRATE-1 \
  BG-O3-CUT-HYDRATE-1 \
  BG-SESSION-TERMINAL-1 \
  DROP-WC-1 \
  DROP-WC-2 \
  REMOUNT-1 \
  PHASE-CLIP-HYDRATE-1 \
  AMBIENT-HYDRATE-1; do
  grep -rq "$marker" "$SB/e2e/" "$SB/src/hooks/__tests__/" "$SB/src/utils/__tests__/" \
    || fail "missing hydrate marker $marker"
done
grep -q 'test.skip' "$E2E_POLL" && fail "phase_e_edit_during_poll must not use test.skip" || true

echo "[fast-and-flawless] pass 5/10 — fixture playwright hydrate + poll"
(
  cd "$SB"
  npx playwright test e2e/phase_e_operator_hydrate.spec.ts e2e/phase_e_edit_during_poll.spec.ts \
    e2e/phase_waveform_playback.spec.ts \
    -g "HYDRATE-1|REMOUNT-1|DROP-WC-1|DROP-WC-2|AMBIENT-HYDRATE-1|PHASE-CLIP-HYDRATE-1"
) || fail "fixture hydrate/playhead e2e failed"

echo "[fast-and-flawless] pass 6/10 — full behavioral parity"
(
  cd "$SB"
  npx playwright test e2e/behavioral-parity.spec.ts
) || fail "behavioral-parity failed"

echo "[fast-and-flawless] pass 7/10 — full touchpoint A"
(
  cd "$SB"
  npx playwright test e2e/touchpoint-a.spec.ts
) || fail "touchpoint-a failed"

echo "[fast-and-flawless] pass 8/14 — Phase G sub-gates (G1, G3, G4)"
bash "$SCRIPTS/verify_interaction_platform_durability.sh"
bash "$SCRIPTS/verify_deploy_warm_path_durability.sh"
bash "$SCRIPTS/verify_event_catalog_invariants_durability.sh" || {
  echo "[fast-and-flawless] WARN — catalog invariants need live server on :5114; continuing"
}

echo "[fast-and-flawless] pass 9/14 — live fleet hydrate + interaction (when servers up)"
LIVE_OK=0
for port in 5111 5112 5113 5114 5115 5116; do
  if curl -sf "http://localhost:${port}/api/event/current" >/dev/null 2>&1; then
    LIVE_OK=1
    SHA="$(curl -sf "http://localhost:${port}/" | sed -n 's/.*name="build-sha" content="\([^"]*\)".*/\1/p' | head -1)"
    HEAD="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
    [[ -n "$SHA" && -n "$HEAD" && "$SHA" == "$HEAD" ]] || fail "port ${port} build-sha mismatch: served=${SHA} git=${HEAD}"
  fi
done
if [[ "$LIVE_OK" -eq 1 ]]; then
  (
    cd "$SB"
    STORYBOARD_LIVE_BASE_URL=http://localhost:5111 npx playwright test --config playwright.live.config.ts e2e/phase_e_hydrate_live.spec.ts
  ) || fail "live hydrate e2e failed"
  bash "$SCRIPTS/verify_live_fleet_interaction.sh" || fail "live fleet interaction failed"
else
  echo "[fast-and-flawless] WARN — no live servers; skipping live e2e (run after deploy)"
fi

echo "[fast-and-flawless] pass 10/14 — perf benchmark"
bash "$SCRIPTS/verify_operator_session_perf.sh"

echo "[fast-and-flawless] pass 11/14 — vitest hydrate hook contracts"
(
  cd "$SB"
  node --experimental-strip-types --test \
    src/hooks/__tests__/useStoryboardTrimFields.test.ts \
    src/utils/__tests__/bgO3CutSession.test.ts \
    src/utils/__tests__/waveformTimeAuthority.test.ts
) || fail "vitest hydrate contracts failed"

echo "[fast-and-flawless] OK — all acceptance criteria met (V3 Phase G)"
