#!/usr/bin/env bash
# verify_element_visual_canonical_lock_durability.sh — ELEMENT_VISUAL_CANONICAL_LOCK_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
SCRIPTS="$ROOT/Production/scripts"
DOC="$ROOT/Production/docs/TECH_SPEC_ELEMENT_VISUAL_CANONICAL_LOCK_v1.md"
REG="$TOOLS/kling_character_registry.py"

fail() { echo "[element-visual-canonical-lock] FATAL: $1" >&2; exit 1; }

echo "[element-visual-canonical-lock] pass 1/6 — spec + registry markers"
[[ -f "$DOC" ]] || fail "missing $DOC"
grep -q 'ELEMENT_VISUAL_CANONICAL_LOCK_V1' "$DOC" || fail "spec missing marker"
grep -q 'set_element_identity' "$REG" || fail "registry missing set_element_identity"
grep -q 'verify_frontal_sha256' "$REG" || fail "registry missing verify_frontal_sha256"
grep -q 'ElementVisualCanonicalError' "$REG" || fail "registry missing ElementVisualCanonicalError"

echo "[element-visual-canonical-lock] pass 2/6 — no promote_frontal in category paths"
if grep -q 'promote_frontal' "$REG"; then
  fail "kling_character_registry.py still contains promote_frontal"
fi
if grep -q 'promote_frontal' "$TOOLS/beat_generator.py"; then
  fail "beat_generator.py still contains promote_frontal"
fi
BGTAB="$TOOLS/storyboard-v2/src/components/BgTab.tsx"
if grep -q 'promote_frontal' "$BGTAB"; then
  fail "BgTab still sends promote_frontal"
fi
if ! grep -q 'bg_set_element_identity' "$BGTAB"; then
  fail "BgTab missing bg_set_element_identity wiring"
fi
if ! grep -q 'Set as Element identity' "$BGTAB"; then
  fail "BgTab missing Set as Element identity button"
fi

echo "[element-visual-canonical-lock] pass 3/6 — patch scripts removed"
[[ ! -f "$SCRIPTS/heal_benson_element_frontal_authority.py" ]]   || fail "heal_benson_element_frontal_authority.py must be deleted (patch class)"
[[ ! -f "$SCRIPTS/verify_benson_element_frontal_authority.sh" ]]   || fail "verify_benson_element_frontal_authority.sh must be deleted (superseded)"

echo "[element-visual-canonical-lock] pass 4/6 — HTTP route + authority registry row"
grep -q 'handle_bg_set_element_identity' "$TOOLS/server_handlers/background.py"   || fail "missing handle_bg_set_element_identity"
grep -q '/api/bg/set-element-identity' "$TOOLS/production_server.py"   || fail "missing /api/bg/set-element-identity route"
grep -q 'element_visual_canonical_lock' "$TOOLS/authority_registry.py"   || fail "authority_registry.py missing element_visual_canonical_lock"
grep -q 'element_visual_canonical_lock' "$ROOT/Production/docs/STORYBOARD_AUTHORITY_REGISTRY_v1.md"   || fail "STORYBOARD_AUTHORITY_REGISTRY missing element_visual_canonical_lock row"

echo "[element-visual-canonical-lock] pass 5/6 — pytest"
export PYTHONPATH="${ROOT}/Production:${ROOT}/Production/tools${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest \
  "$TOOLS/tests/test_element_visual_canonical_lock.py" \
  "$TOOLS/tests/test_beat_ref_drop_lock.py" \
  "$TOOLS/tests/test_library_add_element_ui.py" \
  -q \
  || fail "pytest bundle failed"

echo "[element-visual-canonical-lock] pass 6/6 — authority registry sibling gate"
bash "$SCRIPTS/verify_authority_registry_durability.sh" \
  || fail "verify_authority_registry_durability failed"

echo "[element-visual-canonical-lock] OK — category lock shipped + no promote_frontal + pytest green"
