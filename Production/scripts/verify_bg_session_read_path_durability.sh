#!/usr/bin/env bash
# verify_bg_session_read_path_durability.sh — BG_SESSION_READ_PATH_COMPLETION_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
BG="${TOOLS}/server_handlers/background.py"
O3="${TOOLS}/o3_session_terminal_reconcile.py"
BG_PY="${TOOLS}/beat_generator.py"

fail() { echo "FATAL: $*" >&2; exit 1; }

grep -q "_compose_o3_session_terminal_view" "$BG" \
  || fail "handle path must call _compose_o3_session_terminal_view"
grep -q "compose_session_terminal_view" "$O3" \
  || fail "missing compose_session_terminal_view"
grep -q "preview_orphan_o3_delivery_on_beat" "$BG_PY" \
  || fail "missing preview_orphan_o3_delivery_on_beat"
grep -q "_run_event_sidecar_reconcile_on_sidecar" "$BG_PY" \
  || fail "startup reconcile must plan outside lock"

SESSION_BLOCK="$(python3 - <<'PY' "$BG"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
start = text.index("def handle_bg_session_state")
end = text.index("def handle_bg_poll", start)
block = text[start:end]
idle = block.split("force_reconcile_o3 and event_dir.is_dir()", 1)[0]
if "mutate_sidecar_locked" in idle:
    raise SystemExit("default session GET still calls mutate_sidecar_locked")
if "_apply_o3_session_terminal_reconcile(" in idle:
    raise SystemExit("default session GET still calls _apply_o3_session_terminal_reconcile")
print("ok")
PY
)" || fail "session GET persist leak: ${SESSION_BLOCK:-check failed}"

cd "$TOOLS"
python3 -m pytest tests/test_bg_session_read_path_completion.py -v --cache-clear
echo "[verify_bg_session_read_path] OK"
