#!/usr/bin/env bash
# verify_waveform_time_authority.sh — WAVEFORM_TIME_AUTHORITY_V1 (E3)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SB="$ROOT/Production/tools/storyboard-v2/src"
WTA="$SB/utils/waveformTimeAuthority.ts"
WTA_TEST="$SB/utils/__tests__/waveformTimeAuthority.test.ts"
WSC="$SB/utils/waveformSeekController.ts"
WSC_TEST="$SB/utils/__tests__/waveformSeekController.test.ts"
WAP="$SB/utils/waveformAudioPolicy.ts"
WAP_TEST="$SB/utils/__tests__/waveformAudioPolicy.test.ts"
WTL="$SB/components/phase/WaveformTimeline.tsx"
SPEC="$ROOT/Production/docs/TECH_SPEC_OPERATOR_SESSION_COMPLETION_v1.md"

fail() { echo "[waveform-time-authority] FATAL: $1" >&2; exit 1; }

echo "[waveform-time-authority] pass 1/4 — spec + module"
[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_OPERATOR_SESSION_COMPLETION_v1.md"
grep -q 'WAVEFORM_TIME_AUTHORITY_V1' "$WTA" || fail "missing WTA marker"
grep -q 'preserveAcrossRemount' "$WTA" || fail "missing preserveAcrossRemount"
grep -q 'createWaveformTimeAuthority' "$WTL" || fail "WaveformTimeline must use WTA"
grep -q 'preserveAcrossRemount' "$WTL" || fail "WaveformTimeline must preserve on remount"

grep -q 'bindWaveformSeekController' "$WTL" || fail "WaveformTimeline must use waveformSeekController"
grep -q 'WAVEFORM_SEEK_CONTROLLER_V1' "$WSC" || fail "missing WAVEFORM_SEEK_CONTROLLER_V1 marker"
grep -q 'WTA-12' "$WSC" || fail "missing WTA-12 endDragSeek guard in seek controller"
grep -q 'WTA-12' "$WTL" || fail "missing WTA-12 paused onSeeking path in WaveformTimeline"

echo "[waveform-time-authority] pass 2/4 — vitest (authority)"
(
  cd "$ROOT/Production/tools/storyboard-v2"
  node --experimental-strip-types --test "$WTA_TEST"
) || fail "waveformTimeAuthority vitest failed"

echo "[waveform-time-authority] pass 3/4 — vitest (seek controller + audio policy)"
(
  cd "$ROOT/Production/tools/storyboard-v2"
  node --experimental-strip-types --test "$WSC_TEST" "$WAP_TEST"
) || fail "waveformSeekController / waveformAudioPolicy vitest failed"

echo "[waveform-time-authority] pass 4/4 — e2e marker"
grep -q 'REMOUNT-1' "$ROOT/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts" \
  || fail "phase_waveform_playback.spec.ts missing REMOUNT-1"
grep -q 'AMBIENT-HYDRATE-1' "$ROOT/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts" \
  || fail "phase_waveform_playback.spec.ts missing AMBIENT-HYDRATE-1"

echo "[waveform-time-authority] pass 5/5 — fleet deploy parity (all ports + fanout)"
grep -q 'STORYBOARD_FLEET_BUNDLE_PARITY_V1' "$ROOT/Production/scripts/verify_storyboard_fleet_bundle_parity.sh" \
  || fail "missing verify_storyboard_fleet_bundle_parity.sh"
grep -q 'STORYBOARD_FLEET_RESTART_V1' "$ROOT/Production/scripts/restart_storyboard_fleet.sh" \
  || fail "missing restart_storyboard_fleet.sh"
grep -q 'verify_storyboard_fleet_bundle_parity.sh' "$ROOT/Production/scripts/deploy_storyboard_v59.sh" \
  || fail "deploy_storyboard_v59.sh must gate fleet bundle parity after fanout"

echo "[waveform-time-authority] OK"
