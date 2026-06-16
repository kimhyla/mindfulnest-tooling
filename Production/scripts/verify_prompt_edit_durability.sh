#!/usr/bin/env bash
# verify_prompt_edit_durability.sh — PROMPT_EDIT_DURABILITY_V1
#
# Incident 2026-06: Beat Gen prompt textarea snap-back + caret jump to end mid-edit.
# Root cause: controlled value={...} + refreshState/O3 poll clobber during debounced save.
# Fix: uncontrolled textarea (DOM owns value while typing) + promptEditRegistry overlay.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REGISTRY="${REPO_ROOT}/Production/tools/storyboard-v2/src/state/promptEditRegistry.ts"
HOOK="${REPO_ROOT}/Production/tools/storyboard-v2/src/hooks/useProtectedPromptField.ts"
BGTAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/BgTab.tsx"

fail() { echo "[prompt-edit-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$REGISTRY" ]] || fail "missing promptEditRegistry.ts"
[[ -f "$HOOK" ]] || fail "missing useProtectedPromptField.ts"
[[ -f "$BGTAB" ]] || fail "missing BgTab.tsx"

grep -q 'PROMPT_EDIT_DURABILITY_V1' "$REGISTRY" \
  || fail "PROMPT_EDIT_DURABILITY_V1 marker missing"
grep -q 'applyPromptEditsToBeats' "$REGISTRY" \
  || fail "applyPromptEditsToBeats missing"
grep -q 'stripProtectedPromptFromPatch' "$REGISTRY" \
  || fail "stripProtectedPromptFromPatch missing"

grep -q 'textareaRef' "$HOOK" \
  || fail "useProtectedPromptField must use uncontrolled textareaRef"
grep -q 'Uncontrolled textarea' "$HOOK" \
  || fail "uncontrolled textarea doc missing in hook"
! grep -q 'setLocalText(t)' "$HOOK" \
  || fail "hook must not setLocalText on every input (caret jump regression)"

grep -q 'useProtectedPromptField' "$BGTAB" \
  || fail "BgTab must use useProtectedPromptField"
grep -q 'ref={promptField.textareaRef}' "$BGTAB" \
  || fail "BgTab beat prompt must bind textareaRef (uncontrolled)"
grep -q 'applyPromptEditsToBeats' "$BGTAB" \
  || fail "BgTab refreshState must apply prompt edit overlay"
grep -q 'stripProtectedPromptFromPatch' "$BGTAB" \
  || fail "BgTab O3 poll merge must strip protected prompt fields"
! grep -q 'value={promptField.text}' "$BGTAB" \
  || fail "BgTab must not use controlled value={promptField.text} (caret jump regression)"

echo "[prompt-edit-durability] OK — uncontrolled prompt field + refresh overlay guards present"
