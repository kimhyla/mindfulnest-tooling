#!/usr/bin/env bash
# verify_waveform_time_authority.sh — WAVEFORM_TIME_AUTHORITY_V1 (E3)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SB="$ROOT/Production/tools/storyboard-v2/src"
WTA="$SB/utils/waveformTimeAuthority.ts"
WTA_TEST="$SB/utils/__tests__/waveformTimeAuthority.test.ts"
WTL="$SB/components/phase/WaveformTimeline.tsx"
SPEC="$ROOT/Production/docs/TECH_SPEC_OPERATOR_SESSION_COMPLETION_v1.md"

fail() { echo "[waveform-time-authority] FATAL: $1" >&2; exit 1; }

echo "[waveform-time-authority] pass 1/3 — spec + module"
[[ -f "$SPEC" ]] || fail "missing TECH_SPEC_OPERATOR_SESSION_COMPLETION_v1.md"
grep -q 'WAVEFORM_TIME_AUTHORITY_V1' "$WTA" || fail "missing WTA marker"
grep -q 'preserveAcrossRemount' "$WTA" || fail "missing preserveAcrossRemount"
grep -q 'createWaveformTimeAuthority' "$WTL" || fail "WaveformTimeline must use WTA"
grep -q 'preserveAcrossRemount' "$WTL" || fail "WaveformTimeline must preserve on remount"

echo "[waveform-time-authority] pass 2/3 — vitest"
(
  cd "$ROOT/Production/tools/storyboard-v2"
  node --experimental-strip-types --test "$WTA_TEST"
) || fail "waveformTimeAuthority vitest failed"

echo "[waveform-time-authority] pass 3/3 — e2e marker"
grep -q 'REMOUNT-1' "$ROOT/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts" \
  || fail "phase_waveform_playback.spec.ts missing REMOUNT-1"
grep -q 'AMBIENT-HYDRATE-1' "$ROOT/Production/tools/storyboard-v2/e2e/phase_waveform_playback.spec.ts" \
  || fail "phase_waveform_playback.spec.ts missing AMBIENT-HYDRATE-1"

echo "[waveform-time-authority] OK"
