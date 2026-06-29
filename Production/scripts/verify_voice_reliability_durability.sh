#!/usr/bin/env bash
# VOICE_RELIABILITY_V1 — tagged samples + delete/stitch category fixes.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${ROOT}/Production/tools"
PROD="${ROOT}/Production"

fail() { echo "FATAL: $1" >&2; exit 1; }

echo "=== voice reliability durability ==="

[[ -f "${PROD}/docs/TECH_SPEC_VOICE_RELIABILITY_V1.md" ]] \
  || fail "missing TECH_SPEC_VOICE_RELIABILITY_V1.md"

[[ -f "${PROD}/scripts/sync_roster_voice_sample_tags.py" ]] \
  || fail "missing sync_roster_voice_sample_tags.py"

grep -q 'delete_beat_locked' "${TOOLS}/beat_generator.py" \
  || fail "beat_generator missing delete_beat_locked"

grep -q 'stitchSlotServerArtifactReady' "${TOOLS}/storyboard-v2/src/utils/stitchSlotSessionCache.ts" \
  || fail "missing stitchSlotServerArtifactReady"

bash "${SCRIPT_DIR}/verify_character_voice_onboarding_contract.sh"

cd "${TOOLS}"
PYTHONPATH="${PROD}:${ROOT}" python3 -m pytest \
  tests/test_beatgen_per_event_sqlite.py::test_delete_beat_locked_sqlite \
  tests/test_stitch_slot_artifact_freshness.py \
  tests/test_character_voice_onboarding_gates.py \
  -q

cd "${PROD}"
python3 scripts/sync_roster_voice_sample_tags.py --dry-run --char Ember \
  | grep -q 'text_unchanged' || fail "tag sync dry-run failed"

python3 <<'PY'
import sys
sys.path.insert(0, "tools")
from tools import kling_character_registry as reg
from kling_voice_sample_lock import validate_voice_onboarding_before_spend

reg.set_prod_root(".")
skip = {"Bramble"}
for name, cfg in (reg.load_character_subjects().get("characters") or {}).items():
    if cfg.get("status") != "active" or not cfg.get("kling_voice_id"):
        continue
    if name in skip:
        continue
    errs = validate_voice_onboarding_before_spend(name, cfg)
    if errs:
        raise SystemExit(f"{name} onboarding: " + "; ".join(errs))
print("active roster onboarding OK (Bramble waived)")
PY

echo "=== voice reliability OK ==="
