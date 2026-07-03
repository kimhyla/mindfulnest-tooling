#!/usr/bin/env bash
# verify_crop_save_library_durability.sh — CROP_SAVE_LIBRARY_VISIBILITY_V1
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
CROPPER="${ROOT}/Production/tools/server_handlers/cropper.py"
BG="${ROOT}/Production/tools/beat_generator.py"
LIB="${ROOT}/Production/tools/storyboard-v2/src/components/LibraryPanel.tsx"
UTIL="${ROOT}/Production/tools/storyboard-v2/src/utils/libraryCropSave.ts"
TEST="${ROOT}/Production/tools/tests/test_cr_save_crop_library.py"

fail() { echo "[crop-save-library] FAIL: $1" >&2; exit 1; }

[[ -f "$CROPPER" ]] || fail "missing cropper.py"
[[ -f "$BG" ]] || fail "missing beat_generator.py"
[[ -f "$LIB" ]] || fail "missing LibraryPanel.tsx"
[[ -f "$UTIL" ]] || fail "missing libraryCropSave.ts"
[[ -f "$TEST" ]] || fail "missing test_cr_save_crop_library.py"

grep -q 'CROP_SAVE_LIBRARY_VISIBILITY_V1' "$CROPPER" \
  || fail "cropper must document CROP_SAVE_LIBRARY_VISIBILITY_V1"
grep -q 'import base64' "$BG" \
  || fail "beat_generator.process_crop requires import base64"
grep -q '_crop_delivery_names' "$CROPPER" \
  || fail "missing _crop_delivery_names"
grep -q 'invalidate_cr_library_cache' "$CROPPER" \
  || fail "save-crop must invalidate library cache"
grep -q '_source_abs_path_from_source_key' "$CROPPER" \
  || fail "parent link must resolve file_path from source_key"
grep -q 'mn:library-crop-saved' "$LIB" \
  || fail "LibraryPanel must listen for mn:library-crop-saved"
grep -q 'prependCropLibraryItem' "$UTIL" \
  || fail "libraryCropSave must prepend optimistic row"

python3 -m pytest "$TEST" -q \
  || fail "test_cr_save_crop_library.py failed"

echo "[crop-save-library] OK — source guards + pytest"
