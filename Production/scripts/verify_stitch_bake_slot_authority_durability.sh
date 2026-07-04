#!/usr/bin/env bash
# verify_stitch_bake_slot_authority_durability.sh — STITCH_BAKE_SLOT_AUTHORITY_V1 (pre-deploy)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PHASES="${REPO_ROOT}/Production/tools/server_handlers/phases.py"
EDITOR="${REPO_ROOT}/Production/tools/server_handlers/stitch_editor.py"
DOC="${REPO_ROOT}/Production/docs/TECH_SPEC_STITCH_BAKE_SLOT_AUTHORITY_V1.md"
REGISTRY="${REPO_ROOT}/Production/tools/authority_registry.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_stitch_bake_slot_authority_v1.py"

fail() { echo "[stitch-bake-slot-authority] FAIL: $1" >&2; exit 1; }

[[ -f "$DOC" ]] || fail "missing tech spec"
grep -q 'STITCH_BAKE_SLOT_AUTHORITY_V1' "$DOC" || fail "spec missing marker"
grep -q 'stitch_bake_slot_authority' "$REGISTRY" || fail "registry missing concept id"
grep -q 'validate_phase_b_stitch_slot_authority' "$PHASES" || fail "phases missing read gate"
grep -q 'STITCH_BAKE_SLOT_AUTHORITY_V1' "$PHASES" || fail "phases missing marker"

PREFLIGHT_BLOCK="$(sed -n '/def ensure_phase_b_stitch_slot_for_bake/,/^def handle_phase_b_preview/p' "$PHASES")"
echo "$PREFLIGHT_BLOCK" | grep -q 'validate_phase_b_stitch_slot_authority' \
  || fail "preflight must call validate_phase_b_stitch_slot_authority"
echo "$PREFLIGHT_BLOCK" | grep -q 'stitch_upsert_event_slot' \
  && fail "preflight must not call stitch_upsert_event_slot"
echo "$PREFLIGHT_BLOCK" | grep -q '_phase_ensure_overlay_mp4' \
  && fail "preflight must not rebuild overlay mp4"

BAKE_BLOCK="$(sed -n '/def _run_stitch_bake_core/,/^def /p' "$EDITOR" | head -n 80)"
echo "$BAKE_BLOCK" | grep -q 'PHASE_B_SLOT_AUTHORITY_VALIDATED' \
  || fail "bake core missing PHASE_B_SLOT_AUTHORITY_VALIDATED audit"
echo "$BAKE_BLOCK" | grep -q 'Validating Phase B stitch slot' \
  || fail "bake core still shows refresh wording"

export PYTHONPATH="${REPO_ROOT}/Production:${REPO_ROOT}/Production/tools${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m pytest "$TEST" -q || fail "pytest failed"

echo "[stitch-bake-slot-authority] OK — source guards + pytest passed"
