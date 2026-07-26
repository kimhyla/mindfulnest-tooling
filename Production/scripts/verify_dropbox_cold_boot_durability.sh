#!/usr/bin/env bash
# verify_dropbox_cold_boot_durability.sh — DROPBOX_COLD_BOOT_FLEET_DURABILITY_V1
#
# Guards the vacation-return / login thundering-herd class:
# - local state locks (not on Dropbox)
# - durable Dropbox reads + storyboard cache fallback
# - empty snapshot mirror skipped
# - launchd boot stagger
# - atomic non-empty snapshot copies
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${REPO_ROOT}/Production/tools"
PS="${TOOLS}/production_server.py"
BG="${TOOLS}/beat_generator.py"
CORE="${TOOLS}/server_handlers/core.py"
SNAP="${REPO_ROOT}/Production/lib/production_snapshot.py"
INSTALL="${SCRIPT_DIR}/install_production_server_launchagent.sh"
UNDO="${SCRIPT_DIR}/vacation_pc_mac_undo.sh"

fail() { echo "[dropbox-cold-boot] FAIL: $1" >&2; exit 1; }

[[ -f "$PS" ]] || fail "missing production_server.py"
grep -q '_read_json_file_dropbox_durable' "$PS" \
  || fail "production_server must durable-read Dropbox JSON"
grep -q 'read_storyboard_html_durable' "$PS" \
  || fail "production_server must expose read_storyboard_html_durable"
grep -q '".mindfulnest"' "$PS" \
  || fail "StateManager locks must live under ~/.mindfulnest/locks"
grep -q '"locks"' "$PS" \
  || fail "StateManager must use locks subdirectory under ~/.mindfulnest"
grep -q 'hydrate_from_disk=False' "$PS" \
  || fail "startup stitch bootstrap must not block on Dropbox hydrate"

grep -q 'read_storyboard_html_durable' "$CORE" \
  || fail "serve_storyboard must use read_storyboard_html_durable"

grep -q 'JSONDecodeError' "$BG" \
  || fail "merge_missing_segment_beats_from_json_mirror must catch JSONDecodeError"
grep -q 'st_size == 0' "$BG" \
  || fail "merge_missing must skip empty mirror files"

grep -q 'staging' "$SNAP" \
  || fail "create_snapshot must use staging directory"
grep -q 'empty copy of non-empty source' "$SNAP" \
  || fail "snapshot _copy_file must reject empty copies"
grep -q 'preserved prior non-empty' "$SNAP" \
  || fail "snapshot must preserve prior beat_generator_state when staging empty"

grep -q 'EVENT_SERVER_BOOT_STAGGER_V1' "$INSTALL" \
  || fail "launchagent install must stagger RunAtLoad"
grep -q 'run_launchd_event_server.sh' "$INSTALL" \
  || fail "launchagent install must use stagger wrapper"

[[ -f "$UNDO" ]] || fail "missing vacation_pc_mac_undo.sh"
grep -q 'stagger' "$UNDO" \
  || fail "vacation undo must stagger bootstrap"

cd "$TOOLS"
python3 -m pytest \
  tests/test_state_manager_dropbox_io_durability.py \
  ../lib/tests/test_production_snapshot.py \
  -q --tb=line

bash "${SCRIPT_DIR}/verify_production_server_launchagent_durability.sh"

echo "[dropbox-cold-boot] OK — DROPBOX_COLD_BOOT_FLEET_DURABILITY_V1"
