#!/usr/bin/env bash
# verify_insert_beat_form_first_durability.sh — INSERT_BEAT_FORM_FIRST_SPEC_v1
#
# Regression: blank add-beat rows bypassed extract materialization (Beat 13 male voice).
# Char-ref gate must sync + auto-register on insert (same as bg_update_beat drop).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BG="${REPO_ROOT}/Production/tools/beat_generator.py"
HANDLER="${REPO_ROOT}/Production/tools/server_handlers/background.py"
SERVER="${REPO_ROOT}/Production/tools/production_server.py"
BGTAB="${REPO_ROOT}/Production/tools/storyboard-v2/src/components/BgTab.tsx"
TEST="${REPO_ROOT}/Production/tools/tests/test_insert_beat_form_first.py"

fail() { echo "[insert-beat-form-first-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$BG" ]] || fail "missing beat_generator.py"
[[ -f "$HANDLER" ]] || fail "missing background.py"
[[ -f "$TEST" ]] || fail "missing test_insert_beat_form_first.py"

grep -q 'create_blank_bg_beat is removed' "$BG" \
  || fail "create_blank_bg_beat must raise (no blank rows)"

grep -q 'def materialize_sidecar_beat_from_plan_row' "$BG" \
  || fail "materialize_sidecar_beat_from_plan_row missing"

grep -q 'def maybe_auto_register_beat_char_ref' "$BG" \
  || fail "maybe_auto_register_beat_char_ref missing"

FINALIZE_BLOCK=$(python3 - <<'PY' "$BG"
import sys, re
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"def finalize_proven_element_beat\([\s\S]*?\n\n\n", text)
if not m:
    raise SystemExit("finalize_proven_element_beat block not found")
print(m.group(0))
PY
)
echo "$FINALIZE_BLOCK" | grep -q 'sync_element_char_ref_status(beat, heal_mismatch=False)' \
  || fail "finalize_proven_element_beat must sync element gate"
echo "$FINALIZE_BLOCK" | grep -q 'else:\s*$' \
  && echo "$FINALIZE_BLOCK" | grep -A2 'else:' | grep -q 'sync_element_char_ref_status' \
  && fail "finalize must not sync element gate only in else branch (changed=True bug)" \
  || true

grep -q 'INSERT_BEAT_FORM_REQUIRED' "$HANDLER" \
  || fail "handle_bg_add_beat must return INSERT_BEAT_FORM_REQUIRED"
grep -q 'maybe_auto_register_beat_char_ref' "$HANDLER" \
  || fail "handle_bg_insert_beat must call maybe_auto_register_beat_char_ref"
grep -q 'mutate_sidecar_locked' "$HANDLER" \
  || fail "insert-beat must use mutate_sidecar_locked"

grep -q '"/api/bg/insert-beat"' "$SERVER" \
  || fail "production_server missing /api/bg/insert-beat route"

grep -q 'InsertBeatModal' "$BGTAB" \
  || fail "BgTab must wire InsertBeatModal"
grep -q 'Add empty beat' "$BGTAB" \
  && fail "BgTab must not show Add empty beat" \
  || true

python3 -m pytest "$TEST" -q

echo "[insert-beat-form-first-durability] OK — source guards + pytest passed"
