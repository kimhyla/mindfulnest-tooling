#!/usr/bin/env bash
# verify_beatgen_truth_stack_durability.sh — P6/P7 CI grep gates for Truth Stack.
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"

fail() { echo "[beatgen-truth-stack-durability] FATAL: $1" >&2; exit 1; }

[[ -f "$TOOLS/beatgen_scope.py" ]] || fail "missing beatgen_scope.py"
[[ -f "$TOOLS/production_server.py" ]] || fail "missing production_server.py"

grep -q 'rebind_bg_paths_from_app' "$TOOLS/production_server.py" \
  || fail "P3: production_server must rebind on mutation scope guard"

grep -q 'MN_BEATGEN_SCOPE_JSON' "$TOOLS/o3_subprocess_bootstrap.py" \
  || fail "P7: O3 subprocess must serialize MN_BEATGEN_SCOPE_JSON"

grep -q 'scope_to_env_json' "$TOOLS/beatgen_scope.py" \
  || fail "P7: beatgen_scope must export scope_to_env_json"

grep -q 'beatgen_db_backup' "$TOOLS/server_handlers/core.py" \
  || fail "P9: state snapshot must include beatgen db backup"

grep -q 'import-delivery-clip' "$TOOLS/server_handlers/background.py" \
  || fail "P4: import-delivery-clip handler missing"

grep -q 'assert_direct_write_allowed' "$TOOLS/beat_generator.py" \
  || fail "P1: single-writer gate missing from beat_generator"

python3 - <<'PY' "$TOOLS/beat_generator.py" || fail "P6: event_dir_for_beat_id must raise BeatGenScopeError"
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
block = src.split("def event_dir_for_beat_id", 1)[1].split("\ndef ", 1)[0]
if "BeatGenScopeError" not in block or "raise" not in block:
    raise SystemExit("event_dir_for_beat_id must raise BeatGenScopeError")
PY

if grep -q 'else prod_root / "Event_1"' "$TOOLS/o3_subprocess_bootstrap.py"; then
  fail "P6: o3_subprocess_bootstrap still has bare Event_1 fallback"
fi

CLI="$TOOLS/scripts/run_o3_pov_motion_i2v.py"
if [[ -f "$CLI" ]] && grep -q 'args.event_dir = "Event_1"' "$CLI"; then
  fail "P7: run_o3_pov_motion_i2v still defaults event_dir to Event_1"
fi

export PYTHONPATH="${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

python3 -m pytest \
  "$TOOLS/tests/test_beatgen_truth_stack.py" \
  "$TOOLS/tests/test_milestone_o3_job_busy.py" \
  "$TOOLS/tests/test_o3_subprocess_bootstrap.py" \
  -q \
  || fail "Truth Stack pytest guards failed"

grep -q 'scope_from_app' "$TOOLS/beatgen_scope.py" \
  || fail "Layer 1: beatgen_scope must export scope_from_app"

grep -q '_in_beatgen_scope' "$TOOLS/production_server.py" \
  || fail "Layer 1: production_server must wrap BG mutations in _in_beatgen_scope"

grep -q 'write_magic_delivery' "$TOOLS/server_handlers/background.py" \
  || fail "MAGIC_WRITE_AUTHORITY_V1: write_magic_delivery missing"

grep -q 'run_in_beatgen_scope' "$TOOLS/beatgen_scope.py" \
  || fail "Layer 1: beatgen_scope must export run_in_beatgen_scope"

grep -q 'run_in_beatgen_scope' "$TOOLS/server_handlers/kling_o3.py" \
  || fail "Layer 1: kling_o3 async workers must use run_in_beatgen_scope"

grep -q 'KLING_STATUS_WRITE_CACHE_V1' "$ROOT/Production/docs/TECH_SPEC_KLING_STATUS_WRITE_CACHE_v1.md" \
  || fail "missing KLING_STATUS_WRITE_CACHE_V1 spec"

echo "[beatgen-truth-stack-durability] OK — P3/P6/P7/P9 grep + Layer1 markers + pytest passed"
