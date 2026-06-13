#!/usr/bin/env bash
# verify_phase_voice_stem_pin_durability.sh — guards against stale voice stem pins.
#
# Incident 2026-06-13: lipsync ran on June 6 stem while June 13 regen existed;
# production_state pin stale → wrong dialogue baked into phase_a + stitch slot.
#
# STEM-PIN-1  mirror parity — regen writes top-level + nested phase block
# STEM-PIN-2  lipsync preflight blocks newer orphan stems on disk
# STEM-PIN-3  mix_audio blocks stale pin before expensive work
# STEM-PIN-4  stitch phase_a sync blocked when lipsync sidecar != stem pin
# STEM-PIN-5  post-regen verify state pin matches file written to disk

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
STITCH="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_phase_voice_stem_pin_durability.py"

fail() {
  echo "[phase-voice-stem-pin-durability] FAIL: $1" >&2
  exit 1
}

[[ -f "$PHASES" ]] || fail "missing phases.py"
[[ -f "$STITCH" ]] || fail "missing stitch_editor.py"
[[ -f "$TEST" ]] || fail "missing test_phase_voice_stem_pin_durability.py"

grep -q 'PHASE_VOICE_STEM_PIN_DURABILITY_V1' "$PHASES" \
  || fail "PHASE_VOICE_STEM_PIN_DURABILITY_V1 marker missing"
grep -q '_phase_set_voice_stem_keys' "$PHASES" \
  || fail "_phase_set_voice_stem_keys helper missing (STEM-PIN-1)"
grep -q '_phase_preflight_voice_stem_for_lipsync' "$PHASES" \
  || fail "lipsync preflight missing (STEM-PIN-2)"
grep -q '_phase_assert_voice_stem_pin_persisted' "$PHASES" \
  || fail "post-regen pin verify missing (STEM-PIN-5)"
grep -q 'PHASE_VOICE_STEM_PIN_STALE' "$PHASES" \
  || fail "PHASE_VOICE_STEM_PIN_STALE error code missing"
grep -q 'sync blocked — lipsync audio_source' "$STITCH" \
  || fail "stitch phase_a lineage guard missing (STEM-PIN-4)"

python3 -m pytest "$TEST" -q

echo "[phase-voice-stem-pin-durability] OK — source guards + pytest passed"
