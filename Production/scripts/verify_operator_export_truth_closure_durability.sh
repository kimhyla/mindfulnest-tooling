#!/usr/bin/env bash
# verify_operator_export_truth_closure_durability.sh — OPERATOR_EXPORT_TRUTH_CLOSURE_V1 (FF-022..027 meta)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPTS="$ROOT/Production/scripts"

fail() { echo "[operator-export-truth-closure] FATAL: $1" >&2; exit 1; }

echo "[operator-export-truth-closure] pass 1/5 — FF-022 gallery identity"
bash "$SCRIPTS/verify_o3_gallery_option_identity_durability.sh"

echo "[operator-export-truth-closure] pass 2/5 — FF-019 trim (prerequisite)"
bash "$SCRIPTS/verify_stitch_export_trim_authority_durability.sh"

echo "[operator-export-truth-closure] pass 3/5 — FF-024 timeline authority"
bash "$SCRIPTS/verify_stitch_export_timeline_authority_durability.sh"

echo "[operator-export-truth-closure] pass 4/5 — FF-025 atomic export + FF-026 ambient seam"
TOOLS="$ROOT/Production/tools"
grep -q 'STITCH_EXPORT_ATOMIC_V1' "$TOOLS/server_handlers/stitch_editor.py" \
  || fail "missing STITCH_EXPORT_ATOMIC_V1 in stitch_editor"
grep -q 'STITCH_AMBIENT_SINGLE_SEAM_V1' "$TOOLS/server_handlers/stitch_ambient_loop.py" \
  || fail "missing STITCH_AMBIENT_SINGLE_SEAM_V1"

echo "[operator-export-truth-closure] pass 5/5 — spec doc present"
[[ -f "$ROOT/Production/docs/TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md" ]] \
  || fail "missing TECH_SPEC_OPERATOR_EXPORT_TRUTH_CLOSURE_V1.md"

echo "[operator-export-truth-closure] OK"
