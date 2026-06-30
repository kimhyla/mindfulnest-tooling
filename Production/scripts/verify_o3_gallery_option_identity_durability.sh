#!/usr/bin/env bash
# verify_o3_gallery_option_identity_durability.sh — O3_GALLERY_OPTION_IDENTITY_V1 (FF-022)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
BG="$TOOLS/beat_generator.py"
BGH="$TOOLS/server_handlers/background.py"
K3="$TOOLS/server_handlers/kling_o3.py"
IDENT="$TOOLS/o3_gallery_option_identity.py"

fail() { echo "[o3-gallery-identity] FATAL: $1" >&2; exit 1; }

echo "[o3-gallery-identity] pass 1/4 — contract module"
[[ -f "$IDENT" ]] || fail "missing o3_gallery_option_identity.py"
grep -q 'O3_GALLERY_OPTION_IDENTITY_V1' "$IDENT" || fail "missing marker"
grep -q 'def normalize_o3_gallery_options' "$IDENT" || fail "missing normalize"
grep -q 'def resolve_o3_gallery_option' "$IDENT" || fail "missing resolve"
grep -q 'def assert_beat_export_gallery_authority' "$IDENT" || fail "missing export gate"

echo "[o3-gallery-identity] pass 2/4 — wire points"
grep -q 'resolve_o3_gallery_option_or_path' "$BGH" || fail "background must delegate select resolve"
grep -q 'canonical_o3_option_key' "$BGH" || fail "background must use canonical keys on select"
grep -q 'normalize_o3_gallery_options' "$BG" || fail "beat_generator reconcile must normalize"
grep -q 'EXPORT_GALLERY_AUTHORITY' "$K3" || fail "kling_o3 export must fail closed on gallery drift"

echo "[o3-gallery-identity] pass 3/4 — ban stem key assignment"
if grep -E 'o\["key"\] = Path\(vp\)\.stem' "$BGH" >/dev/null 2>&1; then
  fail "background still assigns Path(vp).stem as option key"
fi

echo "[o3-gallery-identity] pass 4/4 — pytest"
export PYTHONPATH="${ROOT}/Production/tools:${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest "$TOOLS/tests/test_o3_gallery_option_identity.py" -q \
  || fail "gallery identity pytest failed"

echo "[o3-gallery-identity] OK"
