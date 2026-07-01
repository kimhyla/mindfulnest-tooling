#!/usr/bin/env bash
# DIRECTUS_HAS_CROP_DISK_FALLBACK_V1 — has_crop from crops/ stem when Directus down.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

grep -q '_enrich_has_crop_from_disk' server_handlers/cropper.py \
  && grep -q 'DIRECTUS_HAS_CROP_DISK_FALLBACK_V1' server_handlers/cropper.py \
  && mark 'disk has_crop fallback present' \
  || err 'missing disk has_crop fallback'

python3 -m pytest tests/test_has_crop_disk_fallback.py -q \
  && mark 'pytest test_has_crop_disk_fallback' \
  || err 'pytest failed'

exit "$fail"
