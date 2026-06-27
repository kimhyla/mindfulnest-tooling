#!/usr/bin/env bash
# verify_beatgen_siblings_durability.sh — S1–S5 sibling program CI gates (Truth Stack Siblings V2).
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
SCRIPTS="$ROOT/Production/scripts"

fail() { echo "[beatgen-siblings-durability] FATAL: $1" >&2; exit 1; }

[[ -f "$ROOT/Production/docs/TECH_SPEC_BEATGEN_TRUTH_STACK_SIBLINGS_v2.md" ]] \
  || fail "missing TECH_SPEC_BEATGEN_TRUTH_STACK_SIBLINGS_v2.md"

[[ -f "$TOOLS/beatgen_sidecar_health.py" ]] \
  || fail "S5: missing beatgen_sidecar_health.py"

grep -q 'warn_dropbox_conflict_copies' "$TOOLS/beatgen_sidecar_health.py" \
  || fail "S5: warn_dropbox_conflict_copies missing"

[[ -f "$SCRIPTS/restore_beatgen_event_snapshot.sh" ]] \
  || fail "S4: missing restore_beatgen_event_snapshot.sh"

grep -q 'MN_SIDECAR_ALLOW_FULL_REPLACE' "$SCRIPTS/restore_beatgen_event_snapshot.sh" \
  || fail "S4: restore script must set MN_SIDECAR_ALLOW_FULL_REPLACE"

grep -q 'beatgen_db_backup' "$TOOLS/server_handlers/core.py" \
  || fail "P9: snapshot must include beatgen_db_backup"

# S5: Dropbox conflict copies — warn by default; fail when MN_ENFORCE_NO_DROPBOX_CONFLICTS=1
DROPBOX_PROD="${MN_DROPBOX_PRODUCTION:-$HOME/Library/CloudStorage/Dropbox/Claude Mindfulnest Project Files/Production}"
if [[ -d "$DROPBOX_PROD" ]]; then
  CONFLICTS="$(find "$DROPBOX_PROD"/Event_* -iname '*conflicted copy*' -type f 2>/dev/null | head -5 || true)"
  if [[ -n "$CONFLICTS" ]]; then
    echo "[beatgen-siblings-durability] WARN: Dropbox conflict copies under Production/Event_*:"
    echo "$CONFLICTS"
    if [[ "${MN_ENFORCE_NO_DROPBOX_CONFLICTS:-0}" == "1" ]]; then
      fail "S5: resolve conflict copies before deploy (or unset MN_ENFORCE_NO_DROPBOX_CONFLICTS)"
    fi
  fi
fi

export PYTHONPATH="${ROOT}/Production/tools:${ROOT}/Production:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

python3 -m pytest \
  "$TOOLS/tests/test_beatgen_sidecar_health.py" \
  "$TOOLS/tests/test_beatgen_truth_stack.py" \
  -q \
  || fail "sibling pytest guards failed"

echo "[beatgen-siblings-durability] OK — S4/S5/P9 gates + pytest passed"
