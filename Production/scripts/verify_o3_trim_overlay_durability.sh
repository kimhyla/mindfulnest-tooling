#!/usr/bin/env bash
# verify_o3_trim_overlay_durability.sh — O3 drag-trim overlay must clamp stale keep windows
# (regression from O3_TRIM_EXPORT_TRUTH_V1: server duration vs video.duration mismatch).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
OVERLAY="${TOOLS}/storyboard-v2/src/components/bg/BgO3CutOverlay.tsx"
BG_TAB="${TOOLS}/storyboard-v2/src/components/BgTab.tsx"

fail() { echo "FATAL: $*" >&2; exit 1; }

[[ -f "$OVERLAY" ]] || fail "missing BgO3CutOverlay.tsx"
[[ -f "$BG_TAB" ]] || fail "missing BgTab.tsx"

for sym in resolveO3PlaybackDurationS resolveO3ExportDurationS normalizeO3KeepWindow; do
  grep -q "$sym" "$OVERLAY" || fail "BgO3CutOverlay missing $sym"
done
grep -q "resolveO3PlaybackDurationS" "$BG_TAB" \
  || fail "BgTab must use resolveO3PlaybackDurationS for overlay timeline"
grep -q "normalizeO3KeepWindow" "$OVERLAY" \
  || fail "commitDraft must normalize before isValidO3KeepWindow"

cd "$TOOLS"
PYTHONPATH="${REPO_ROOT}/Production:${REPO_ROOT}" \
  python3 -m pytest tests/test_o3_per_option_cut.py -q --cache-clear

echo "[verify_o3_trim_overlay] OK"
