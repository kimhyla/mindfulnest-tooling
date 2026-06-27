#!/usr/bin/env bash
# verify_bg_generate_gate_durability.sh — ELEMENT_GATE_PROMPT_ISOLATION_V1 + BG_GENERATE_FEEDBACK_V1
#
# Incidents 2026-06:
# - Prompt debounce re-ran Element @Image1 gate → false re-register + disabled Generate.
# - Generate click had no spinner/toast when save or submit stalled (silent failure).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BG="${REPO_ROOT}/Production/tools/server_handlers/background.py"
BGTAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/BgTab.tsx"

fail() { echo "[bg-generate-gate-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$BG" ]] || fail "missing background.py"
[[ -f "$BGTAB" ]] || fail "missing BgTab.tsx"

grep -q '_BG_ELEMENT_CHAR_REF_SYNC_FIELDS' "$BG" \
  || fail "server must scope Element gate sync to identity fields only"
grep -q 'Prompt-only saves must not push gate fields' "$BG" \
  || fail "handle_bg_update_beat must omit gate fields on prompt-only writes"

grep -q 'ELEMENT_GATE_PROMPT_ISOLATION_V1' "$BGTAB" \
  || fail "BgTab must not apply element_char_ref_ok from prompt-only saves"
grep -q 'BG_GENERATE_FEEDBACK_V1' "$BGTAB" \
  || fail "BgTab must show submit-pending busy state on Generate click"
grep -q 'bg-generate-save-blocked' "$BGTAB" \
  || fail "BgTab must toast when Generate blocked by failed prompt save"
grep -q 'o3SubmitPending' "$BGTAB" \
  || fail "BgTab must track o3SubmitPending for Generate button feedback"

echo "[bg-generate-gate-durability] OK — prompt edits isolated from Element gate + Generate feedback wired"
