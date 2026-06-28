#!/usr/bin/env bash
# audit_authority_duplicates.sh — retroactive scan for competing authority predicates.
#
# Usage:
#   bash audit_authority_duplicates.sh              # report only (exit 0)
#   bash audit_authority_duplicates.sh --strict-subset  # fail on fixed-class regressions
set -uo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
SB="$TOOLS/storyboard-v2/src"
STRICT="${1:-}"

report() { echo "[authority-audit] $*"; }
section() { echo ""; echo "=== $1 ==="; }
fail_strict() {
  if [[ "$STRICT" == "--strict-subset" ]]; then
    echo "[authority-audit] FATAL: $1" >&2
    exit 1
  fi
  report "FINDING: $1"
}

section "A. Kling stitch export — client must not gate on kling_o3_status alone (export files)"
FIND_A=$(rg -n "kling_o3_status\s*===?\s*['\"]approved['\"]" "$SB/utils/bgStitchExport.ts" 2>/dev/null || true)
if [[ -n "$FIND_A" ]]; then
  echo "$FIND_A"
  fail_strict "bgStitchExport.ts gates on kling_o3_status"
else
  report "bgStitchExport.ts clean"
fi

section "B. Duplicate job_busy gate in bgStitchExport (must use o3JobBlocksStitchExport)"
FIND_B=$(rg -n "job_busy\s*\|\||o3_current_job_id" "$SB/utils/bgStitchExport.ts" 2>/dev/null || true)
if [[ -n "$FIND_B" ]]; then
  echo "$FIND_B"
  fail_strict "bgStitchExport.ts duplicates job_busy predicate"
else
  report "bgStitchExport.ts uses contract for job busy"
fi

section "C. auto_pin must delegate to beat_kling_stitch_export_ready"
if grep -A8 'def auto_pin_approved_kling_o3_delivery' "$TOOLS/beat_generator.py" | grep -q 'kling_o3_status.*!=.*approved'; then
  fail_strict "auto_pin still uses raw kling_o3_status gate"
else
  report "auto_pin delegates to stitch contract"
fi

section "D. BgTab prompt textarea must prefer _derived.display_prompt"
if ! grep -q '_derived?.display_prompt' "$SB/components/BgTab.tsx"; then
  fail_strict "BgTab beatPromptText missing _derived.display_prompt"
else
  report "BgTab uses display_prompt authority"
fi

section "E. Informational — kling_o3_status === approved elsewhere (display/heal, not export gates)"
rg -n "kling_o3_status\s*===?\s*['\"]approved['\"]" "$SB" \
  --glob '!**/__tests__/**' \
  --glob '!**/klingStitchReadiness.ts' \
  --glob '!**/bgStitchExport.ts' 2>/dev/null || true

section "F. Informational — server write paths still setting kling_o3_status directly"
rg -n 'beat\["kling_o3_status"\]\s*=\s*"approved"' "$TOOLS" \
  --glob '*.py' \
  --glob '!**/kling_stitch_readiness.py' \
  --glob '!**/tests/**' 2>/dev/null | head -20 || true

section "G. Stitch timeline — StitcherTab DEFAULT_SLOT_DUR fallbacks (review only)"
rg -n "DEFAULT_SLOT_DUR_MS \*" "$SB/components/StitcherTab.tsx" 2>/dev/null || true

report "audit complete"
exit 0
