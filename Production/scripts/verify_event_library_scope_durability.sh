#!/usr/bin/env bash
# verify_event_library_scope_durability.sh — EVENT_LIBRARY_SCOPE_ON_LOAD_V1
# Ensures /api/event/load rebinds BG stills paths so cr/library is per-event.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HANDLER="${REPO_ROOT}/Production/tools/server_handlers/event_video.py"

fail() { echo "[event-library-scope] FAIL: $1" >&2; exit 1; }

[[ -f "$HANDLER" ]] || fail "missing event_video.py"

grep -q 'def handle_event_load' "$HANDLER" || fail "handle_event_load missing"
grep -qE 'init_bg_paths\(new_event_dir(, clear_milestone_scope=True)?\)' "$HANDLER" \
  || fail "handle_event_load must call init_bg_paths(new_event_dir) after event swap"
grep -q 'library/images' "${REPO_ROOT}/Production/lib/paths.py" \
  || fail "bg_paths must scope stills_dir to Event_N/library/images"

echo "[event-library-scope] OK — event/load rebinds BG library paths"
