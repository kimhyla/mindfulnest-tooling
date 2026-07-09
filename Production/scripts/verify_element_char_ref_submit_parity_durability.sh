#!/usr/bin/env bash
# verify_element_char_ref_submit_parity_durability.sh — ELEMENT_CHAR_REF_SUBMIT_PARITY_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
DOC="$ROOT/Production/docs/TECH_SPEC_ELEMENT_CHAR_REF_SUBMIT_PARITY_v1.md"
OWC="$TOOLS/operator_workbench_contract.py"
BG="$TOOLS/beat_generator.py"
REG="$TOOLS/kling_character_registry.py"
BGTAB="$TOOLS/storyboard-v2/src/components/BgTab.tsx"

fail() { echo "[element-char-ref-submit-parity] FATAL: $1" >&2; exit 1; }

echo "[element-char-ref-submit-parity] pass 1/5 — spec + markers"
[[ -f "$DOC" ]] || fail "missing $DOC"
grep -q 'ELEMENT_CHAR_REF_SUBMIT_PARITY_V1' "$DOC" || fail "spec missing marker"
grep -q 'char_ref_aligned_for_intent_commit' "$OWC" || fail "workbench gate must delegate to char_ref_aligned_for_intent_commit"
grep -q 'ELEMENT_CHAR_REF_SUBMIT_PARITY_V1' "$OWC" || fail "workbench missing parity marker"
grep -q 'resolve_beat_element_char_ref_gate' "$BG" || fail "beat_generator element_char_ref_gate must delegate to workbench gate"

echo "[element-char-ref-submit-parity] pass 2/5 — no stale sidecar trust"
if grep -q 'element_char_ref_ok.*is True' "$OWC"; then
  fail "operator_workbench_contract must not trust stale element_char_ref_ok"
fi

echo "[element-char-ref-submit-parity] pass 3/5 — frontal_sha256 strict without visual_canonical_locked flag"
grep -q 'frontal_sha256 is the byte authority' "$REG" || fail "registry must document frontal_sha256 authority"

echo "[element-char-ref-submit-parity] pass 4/5 — UI preflight before optimistic pending"
grep -q 'bg-element-ref-submit-block' "$BGTAB" || fail "BgTab must toast ELEMENT_REGISTRATION_FAILED"
grep -q 'onBeginGenerateSubmit?.();' "$BGTAB" || fail "BgTab must defer submit pending until after prompt save"

echo "[element-char-ref-submit-parity] pass 5/5 — pytest"
export PYTHONPATH="${ROOT}/Production:${ROOT}/Production/tools${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest \
  "$TOOLS/tests/test_operator_workbench_contract.py" \
  "$TOOLS/tests/test_element_visual_canonical_lock.py" \
  -q \
  || fail "pytest bundle failed"

echo "[element-char-ref-submit-parity] OK — submit authority unified; stale sidecar trust removed"
