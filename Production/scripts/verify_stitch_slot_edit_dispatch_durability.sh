#!/usr/bin/env bash
# verify_stitch_slot_edit_dispatch_durability.sh — STITCH_SLOT_EDIT_DISPATCH_V1 gate
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EDITOR="$ROOT/Production/tools/server_handlers/stitch_editor.py"
DISPATCH="$ROOT/Production/tools/server_handlers/stitch_slot_edit_dispatch.py"
STITCHER="$ROOT/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
CLIENT="$ROOT/Production/tools/storyboard-v2/src/utils/stitchSlotEditDispatch.ts"
SPEC="$ROOT/Production/docs/TECH_SPEC_STITCH_SLOT_EDIT_DISPATCH_V1.md"

fail() { echo "[edit-dispatch] FAIL — $*" >&2; exit 1; }

grep -q 'STITCH_SLOT_EDIT_DISPATCH_V1' "$DISPATCH" || fail "dispatch module marker missing"
grep -q 'plan_stitch_save_dispatch' "$DISPATCH" || fail "plan_stitch_save_dispatch missing"
grep -q 'edit_dispatch' "$EDITOR" || fail "edit_dispatch response missing"
grep -q 'if slot_keys is not None:' "$EDITOR" || fail "empty slot_keys guard missing"
grep -q 'inferStitchEditKind' "$STITCHER" || fail "client inferStitchEditKind missing"
grep -q 'edit_kind' "$STITCHER" || fail "edit_kind on save missing"
grep -q 'STITCH_SLOT_EDIT_DISPATCH_V1' "$CLIENT" || fail "client dispatch module missing"
test -f "$SPEC" || fail "tech spec missing"

python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_slot_edit_dispatch.py" -q
python3 -m pytest "$ROOT/Production/tools/tests/test_stitch_ambient_preview_no_save_wipe.py" -q

echo "[edit-dispatch] OK — markers + pytest passed"
