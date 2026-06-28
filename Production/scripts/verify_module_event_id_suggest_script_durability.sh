#!/usr/bin/env bash
# verify_module_event_id_suggest_script_durability.sh — Suggest Script must resolve
# Event_N folder ids to the correct module (not silent M1 fallback).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

fail() { echo "[module-event-id-suggest] FAIL: $1" >&2; exit 1; }

PSERVER="${REPO_ROOT}/Production/tools/production_server.py"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
MEI="${REPO_ROOT}/Production/lib/module_event_id.py"

[[ -f "$PSERVER" ]] || fail "missing production_server.py"
[[ -f "$PHASES" ]] || fail "missing phases.py"
[[ -f "$MEI" ]] || fail "missing module_event_id.py"

BG="${REPO_ROOT}/Production/tools/beat_generator.py"

[[ -f "$BG" ]] || fail "missing beat_generator.py"

grep -q 'find_m_number_for_play_order_event' "$BG" \
  || fail "beat_generator must expose find_m_number_for_play_order_event"
grep -q 'heal_production_state_event_id' "$PSERVER" \
  || fail "run_server must heal event_id on startup"
grep -q 'production_folder_id' "$PHASES" \
  || fail "handle_phase_suggest_script must pass production_folder_id to resolver"
grep -q 'extract_skeleton_module_metadata' "$BG" \
  || fail "beat_generator must expose extract_skeleton_module_metadata"
grep -q 'load_phase_b_research_dossier' "$BG" \
  || fail "beat_generator must load Phase B research dossiers"
grep -q 'slice_technique_inventory_for_module' "$BG" \
  || fail "beat_generator must slice technique inventory by M-number"
grep -q 'format_therapeutic_brief_for_script_prompt' "$PHASES" \
  || fail "phases must inject therapeutic brief into script prompt"

export PYTHONPATH="${REPO_ROOT}/Production/tools:${REPO_ROOT}/Production:${PYTHONPATH:-}"

python3 -m unittest Production.tools.tests.test_module_event_id_suggest_script -v \
  || fail "unit tests failed"
python3 -m unittest Production.tools.tests.test_phase_b_suggest_sources -v \
  || fail "phase b suggest source tests failed"

echo "[module-event-id-suggest] OK — Arc Skeleton play-order → m_number + suggest script guards"
