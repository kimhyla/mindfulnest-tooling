#!/usr/bin/env bash
# P4/P6 — SQLite sidecar cutover gate (BEATGEN_SIDECAR_SQLITE_AUTHORITY_SPEC_v1 §9).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BG="$REPO_ROOT/Production/tools/beat_generator.py"
HANDLER="$REPO_ROOT/Production/tools/server_handlers/background.py"
KLING_O3="$REPO_ROOT/Production/tools/server_handlers/kling_o3.py"
PROD_SERVER="$REPO_ROOT/Production/tools/production_server.py"

fail() { echo "FATAL: $*" >&2; exit 1; }

_lock_free_check() {
  local label="$1"
  local path="$2"
  python3 - <<'PY' "$path" "$label" || fail "sidecar_file_lock still in $label"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
label = sys.argv[2]
for i, line in enumerate(text.splitlines(), 1):
    if line.strip().startswith("#"):
        continue
    if "with bg.sidecar_file_lock" in line:
        raise SystemExit(f"{label} line {i}: {line.strip()}")
print(f"  {label} lock-free ok")
PY
}

echo "[sqlite-cutover-gate] beat_generator flock isolated to legacy helper..."
grep -q "def _legacy_json_sidecar_file_lock" "$BG" \
  || fail "missing _legacy_json_sidecar_file_lock in beat_generator.py"
# fcntl must not appear in sidecar_file_lock body (only in legacy helper).
python3 - <<'PY' "$BG" || fail "fcntl.flock still in sidecar_file_lock hot path"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
body = text.split("def sidecar_file_lock", 1)[1].split("\ndef ", 1)[0]
legacy = text.split("def _legacy_json_sidecar_file_lock", 1)[1].split("\ndef ", 1)[0]
if "fcntl.flock" in body:
    raise SystemExit("fcntl.flock found in sidecar_file_lock")
if "fcntl.flock" not in legacy:
    raise SystemExit("fcntl.flock missing from _legacy_json_sidecar_file_lock")
print("  flock isolation ok")
PY

echo "[sqlite-cutover-gate] session-state GET must not persist heals under lock..."
python3 - <<'PY' "$HANDLER" || fail "session-state still writes sidecar on default GET"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
fn = text.split("def handle_bg_session_state", 1)[1].split("\ndef ", 1)[0]
doc_close = fn.find('"""')
if doc_close >= 0:
    doc_close = fn.find('"""', doc_close + 3)
    if doc_close >= 0:
        fn = fn[doc_close + 3 :]
default_path = fn.split("if force_reconcile_o3", 1)[0]
if "bg.write_sidecar" in default_path:
    raise SystemExit(1)
print("  session-state read-only ok")
PY

echo "[sqlite-cutover-gate] background.py must not call sidecar_file_lock..."
_lock_free_check "background.py" "$HANDLER"

echo "[sqlite-cutover-gate] kling_o3.py must not call sidecar_file_lock..."
_lock_free_check "kling_o3.py" "$KLING_O3"

echo "[sqlite-cutover-gate] production_server.py must not call sidecar_file_lock..."
_lock_free_check "production_server.py" "$PROD_SERVER"

echo "[sqlite-cutover-gate] submit intent after sidecar commit..."
python3 - <<'PY' "$HANDLER" || fail "submit must write_generation_intent after sidecar commit"
import sys
text = open(sys.argv[1], encoding="utf-8").read()
fn = text.split("def handle_bg_submit_arlo_o3_voice", 1)[1].split("\ndef ", 1)[0]
w = fn.find("update_beat_locked(str(beat_id), _commit_o3)")
i = fn.find("write_generation_intent(committed_intent")
if w < 0 or i < 0 or i < w:
    raise SystemExit(1)
print("  submit ordering ok")
PY

echo "[sqlite-cutover-gate] pytest store + cutover contracts..."
cd "$REPO_ROOT/Production/tools"
python3 -m pytest \
  tests/test_beatgen_store.py \
  tests/test_sidecar_sqlite_cutover_gate.py \
  tests/test_o3_sidecar_lock_hold_durability.py \
  -q

echo "[sqlite-cutover-gate] ALL PASSED"
