#!/usr/bin/env bash
# verify_per_event_library_durability.sh — PER_EVENT_LIBRARY_DURABILITY_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PATHS="${REPO_ROOT}/Production/lib/paths.py"
EVENT_LIB="${REPO_ROOT}/Production/lib/event_library.py"
CROPPER="${REPO_ROOT}/Production/tools/server_handlers/cropper.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_event_library_scoping.py"
SMOKE="${SCRIPT_DIR}/smoke_per_event_library.sh"

fail() { echo "[per-event-library-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$PATHS" ]] || fail "missing paths.py"
[[ -f "$EVENT_LIB" ]] || fail "missing event_library.py"
[[ -f "$CROPPER" ]] || fail "missing cropper.py"
[[ -f "$TEST" ]] || fail "missing test_event_library_scoping.py"
[[ -x "$SMOKE" ]] || fail "missing smoke_per_event_library.sh"

grep -q 'library/images' "$PATHS" \
  || fail "bg_paths must use Event_N/library/images for per-event stills"
grep -q 'def event_images_dir' "$EVENT_LIB" \
  || fail "event_library.py missing event_images_dir"
grep -q 'canonical_meta_for_arc' "$CROPPER" \
  || fail "cropper handle_cr_library must inject canonical tier"

python3 -m pytest "$TEST" -q

if curl -sf "http://localhost:${MN_SERVER_PORT:-5111}/api/event/current" >/dev/null 2>&1; then
  bash "$SMOKE"
  echo "[per-event-library-durability] OK — pytest + live smoke passed"
else
  echo "[per-event-library-durability] OK — source guards + pytest passed (server down; skip live smoke)"
fi
