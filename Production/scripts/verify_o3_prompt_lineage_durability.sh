#!/usr/bin/env bash
# verify_o3_prompt_lineage_durability.sh — O3-004/005/006 closure (intent transaction)
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
SPEC="$ROOT/Production/docs/TECH_SPEC_O3_GENERATION_INTENT_SNAPSHOT_v1.md"

fail() { echo "[o3-prompt-lineage] FATAL: $1" >&2; exit 1; }

echo "[o3-prompt-lineage] pass 1/3 — spec + submit path guards"
[[ -f "$SPEC" ]] || fail "missing O3 intent spec"
BG="$TOOLS/server_handlers/background.py"
grep -q 'validate_o3_submit_prompt_for_mode' "$BG" || fail "submit validation missing"
python3 <<PY || fail "heal_beat_dual_prompts must not run on element submit path"
from pathlib import Path
block = Path("$BG").read_text().split("def handle_bg_submit_arlo_o3_voice", 1)[1]
block = block.split("\ndef handle_bg_submit_kling", 1)[0]
assert "heal_beat_dual_prompts" not in block
PY

echo "[o3-prompt-lineage] pass 2/3 — pytest (g7→g8 slot, parenthetical, char ref gate)"
(
  cd "$TOOLS"
  python3 -m pytest \
    tests/test_o3_generation_intent_commit.py \
    tests/test_o3_verbatim_prompt_durability.py \
    tests/test_o3_prompt_isolation_beat03.py \
    -q --tb=short
) || fail "O3 lineage pytest failed"

echo "[o3-prompt-lineage] pass 3/3 — intent transaction gate"
bash "$ROOT/Production/scripts/verify_o3_generation_intent_transaction_durability.sh"

echo "[o3-prompt-lineage] OK"
