#!/usr/bin/env bash
# verify_per_event_library_durability.sh — PER_EVENT_LIBRARY_DURABILITY_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PATHS="${REPO_ROOT}/Production/lib/paths.py"
EVENT_LIB="${REPO_ROOT}/Production/lib/event_library.py"
CROPPER="${REPO_ROOT}/Production/tools/server_handlers/cropper.py"
META_TEST="${REPO_ROOT}/Production/tools/tests/test_cr_library_metadata_only.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_event_library_scoping.py"
APP_CTX_TEST="${REPO_ROOT}/Production/tools/tests/test_app_context_library_roots.py"
SMOKE="${SCRIPT_DIR}/smoke_per_event_library.sh"

fail() { echo "[per-event-library-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$PATHS" ]] || fail "missing paths.py"
[[ -f "$EVENT_LIB" ]] || fail "missing event_library.py"
[[ -f "$CROPPER" ]] || fail "missing cropper.py"
[[ -f "$META_TEST" ]] || fail "missing test_cr_library_metadata_only.py"
[[ -f "$TEST" ]] || fail "missing test_event_library_scoping.py"
[[ -f "$APP_CTX_TEST" ]] || fail "missing test_app_context_library_roots.py"
[[ -x "$SMOKE" ]] || fail "missing smoke_per_event_library.sh"

grep -q 'library/images' "$PATHS" \
  || fail "bg_paths must use Event_N/library/images for per-event stills"
grep -q 'def event_images_dir' "$EVENT_LIB" \
  || fail "event_library.py missing event_images_dir"
grep -q 'metadata_only' "$CROPPER" \
  || fail "cropper handle_cr_library must return metadata_only list"
grep -q 'panel_tabs' "$CROPPER" \
  || fail "cropper handle_cr_library must emit panel_tabs (LIBRARY_PANEL_CLASSIFICATION_V1)"
grep -q 'def handle_cr_thumb' "$CROPPER" \
  || fail "cropper must expose on-demand GET /api/cr/thumb"
grep -q 'CR_THUMB_HOT_SERVE_V1' "$CROPPER" \
  || fail "cropper thumb must hot-serve before PIL decode (CR_THUMB_HOT_SERVE_V1)"
grep -q 'ensure_hot_serve_file' "$CROPPER" \
  || fail "cropper thumb must call ensure_hot_serve_file"
grep -q 'Canonical registry images are intentionally excluded' "$CROPPER" \
  || fail "cropper must exclude canonical registry from library grid"
grep -q 'apply_to_all_events' "${REPO_ROOT}/Production/canonical_image_registry.json" \
  || fail "canonical_image_registry.json must set apply_to_all_events for all Event_N"
grep -q 'apply_to_all_events' "$EVENT_LIB" \
  || fail "event_library canonical_meta_for_arc must honor apply_to_all_events"

python3 -m pytest "$TEST" "$APP_CTX_TEST" "$META_TEST" -q

if curl -sf --max-time 5 "http://localhost:${MN_SERVER_PORT:-5111}/api/event/current" >/dev/null 2>&1; then
  export MN_SERVER_PORT="${MN_SERVER_PORT:-5111}"
  bash "$SMOKE"
  echo "[per-event-library-durability] OK — pytest + live smoke passed"
else
  echo "[per-event-library-durability] OK — source guards + pytest passed (server down; skip live smoke)"
fi
