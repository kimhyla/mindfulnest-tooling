#!/usr/bin/env bash
# verify_stitch_canonical_transitions_durability.sh — STITCH_CANONICAL_TRANSITIONS_V1 +
# STITCH_CANONICAL_TRANSITION_SFX_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
STITCH="$ROOT/Production/tools/server_handlers/stitch_editor.py"
SERVER="$ROOT/Production/tools/production_server.py"
MOD="$ROOT/Production/tools/storyboard-v2/src/utils/stitchModulePreview.ts"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'STITCH_CANONICAL_TRANSITIONS_V1' "$STITCH" || fail "missing STITCH_CANONICAL_TRANSITIONS_V1"
grep -q 'STITCH_CANONICAL_TRANSITION_SFX_V1' "$STITCH" || fail "missing STITCH_CANONICAL_TRANSITION_SFX_V1"
grep -q 'canonical_stitch_transitions_for_pipeline' "$STITCH" || fail "missing canonical_stitch_transitions_for_pipeline"
grep -q 'magic_sound.mp3' "$STITCH" || fail "missing magic_sound boundary map"
grep -q 'windy_magic.mp3' "$STITCH" || fail "missing windy_magic boundary map"
grep -q '_stitch_apply_canonical_boundary_sfx' "$SERVER" || fail "missing boundary sfx overlay in pipeline"
grep -q '_stitch_apply_resolution_finale' "$SERVER" || fail "missing resolution finale in pipeline"
grep -q 'STITCH_RESOLUTION_FINALE_V1' "$STITCH" || fail "missing STITCH_RESOLUTION_FINALE_V1"
grep -q 'outtro3.mp3' "$STITCH" || fail "missing outtro3 finale map"
grep -q 'STITCH_MILESTONE_FINALE_V1' "$STITCH" || fail "missing STITCH_MILESTONE_FINALE_V1"
grep -q 'outtro3.mp3' "$STITCH" || fail "missing outtro3 milestone/resolution finale map"
grep -q '_stitch_apply_milestone_finale' "$SERVER" || fail "missing milestone finale in pipeline"
grep -q 'return defaultStitchTransitions()' "$MOD" || fail "client must always resolve canonical transitions"

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_canonical_transition_sfx.py" -q

echo "[stitch-canonical-transitions-durability] OK — fades + boundary SFX wired"
