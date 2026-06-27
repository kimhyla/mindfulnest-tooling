#!/usr/bin/env bash
# verify_stitch_slot_timeline_atomic_durability.sh — STITCH_SLOT_TIMELINE_ATOMIC_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
TAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/StitcherTab.tsx"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_slot_timeline_atomic.py"

fail() { echo "[stitch-slot-timeline-atomic] FAIL: $1" >&2; exit 1; }

[[ -f "$EDITOR" ]] || fail "missing stitch_editor.py"
[[ -f "$TAB" ]] || fail "missing StitcherTab.tsx"
[[ -f "$TEST" ]] || fail "missing test_stitch_slot_timeline_atomic.py"

grep -q 'STITCH_SLOT_TIMELINE_ATOMIC_V1' "$EDITOR" \
  || fail "STITCH_SLOT_TIMELINE_ATOMIC_V1 missing in stitch_editor.py"
grep -q 'ensure_stitch_slot_timeline_dur_ms' "$EDITOR" \
  || fail "ensure_stitch_slot_timeline_dur_ms missing"
grep -q 'STITCH_SLOT_TIMELINE_ATOMIC_V1' "$TAB" \
  || fail "STITCH_SLOT_TIMELINE_ATOMIC_V1 missing in StitcherTab.tsx"
grep -q 'stitchSlotTimelineDurMs' "$TAB" \
  || fail "stitchSlotTimelineDurMs must drive rail/drop duration"

python3 -m pytest "$TEST" -q
echo "[stitch-slot-timeline-atomic] OK — source guards + pytest passed"
