#!/usr/bin/env bash
# verify_baseline_image_library_durability.sh — SHARED_BASELINE_IMAGE_LIBRARY_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVENT_LIB="${REPO_ROOT}/Production/lib/event_library.py"
CROPPER="${REPO_ROOT}/Production/tools/server_handlers/cropper.py"
BASELINE_TEST="${REPO_ROOT}/Production/tools/tests/test_baseline_image_library.py"
SEED="${REPO_ROOT}/Production/scripts/seed_baseline_image_library.py"

fail() { echo "[baseline-library-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$EVENT_LIB" ]] || fail "missing event_library.py"
[[ -f "$CROPPER" ]] || fail "missing cropper.py"
[[ -f "$BASELINE_TEST" ]] || fail "missing test_baseline_image_library.py"
[[ -f "$SEED" ]] || fail "missing seed_baseline_image_library.py"

grep -q 'def baseline_images_dir' "$EVENT_LIB" \
  || fail "event_library must define baseline_images_dir"
grep -q 'def list_baseline_meta' "$EVENT_LIB" \
  || fail "event_library must define list_baseline_meta"
grep -q 'shared_baseline' "$CROPPER" \
  || fail "cropper handle_cr_library must emit shared_baseline rows"
grep -q 'BASELINE_IMAGE_PROTECTED' "$CROPPER" \
  || fail "cropper delete must guard baseline paths"

python3 -m pytest "$BASELINE_TEST" -q \
  || fail "test_baseline_image_library.py failed"

BASELINE_DIR="${MN_DROPBOX_ROOT:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}/Production/assets/image_library/baseline"
REGISTRY="${MN_DROPBOX_ROOT:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files}/Production/baseline_image_registry.json"
[[ -d "$BASELINE_DIR" ]] || fail "Dropbox baseline dir missing — run seed_baseline_image_library.py"
[[ -f "$REGISTRY" ]] || fail "Dropbox baseline_image_registry.json missing"

BASELINE_COUNT="$(find "$BASELINE_DIR" -maxdepth 1 -name '*.png' | wc -l | tr -d ' ')"
[[ "$BASELINE_COUNT" -ge 17 ]] || fail "expected >=17 baseline PNGs, got $BASELINE_COUNT"

if curl -sf --max-time 5 "http://localhost:5113/" >/dev/null 2>&1; then
  API_COUNT="$(curl -sf "http://localhost:5113/api/cr/library?event_id=Event_3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for i in d.get('images',[]) if i.get('shared_baseline')))")"
  [[ "$API_COUNT" -ge 17 ]] || fail "Event_3 API shared_baseline count=$API_COUNT expected >=17"
  echo "[baseline-library-durability] OK — pytest + live API baseline=$API_COUNT"
else
  echo "[baseline-library-durability] OK — source guards + pytest (server down; skip live API)"
fi
