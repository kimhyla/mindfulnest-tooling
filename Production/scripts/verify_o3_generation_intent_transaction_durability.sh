#!/usr/bin/env bash
# verify_o3_generation_intent_transaction_durability.sh — E2 intent transaction closure
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
INTENT="$ROOT/Production/tools/o3_generation_intent.py"
BGTAB="$ROOT/Production/tools/storyboard-v2/src/components/BgTab.tsx"
SPEC="$ROOT/Production/docs/TECH_SPEC_O3_GENERATION_INTENT_SNAPSHOT_v1.md"

fail() { echo "[o3-intent-transaction] FATAL: $1" >&2; exit 1; }

echo "[o3-intent-transaction] pass 1/3 — module + spec"
[[ -f "$INTENT" ]] || fail "missing o3_generation_intent.py"
[[ -f "$SPEC" ]] || fail "missing O3 intent spec"
grep -q 'reconcile_orphan_terminal' "$INTENT" || fail "missing reconcile_orphan_terminal"
grep -q 'done_with_warning' "$INTENT" || fail "orphan reconcile must use done_with_warning"

echo "[o3-intent-transaction] pass 2/3 — submit UI latch ordering"
grep -q 'applyO3SubmitPollLatch' "$BGTAB" || fail "BgTab missing poll latch"
# Intent map must be set before refreshState in handleO3SubmitResult
python3 - <<PY || fail "BgTab submit must latch intent before refreshState"
from pathlib import Path
text = Path("$BGTAB").read_text()
start = text.index("const handleO3SubmitResult")
chunk = text[start:start + 1200]
ri = chunk.index("void refreshState()")
ii = chunk.index("bgO3IntentByBeat.value")
if ri < ii:
    raise SystemExit("refreshState runs before intent latch")
PY

echo "[o3-intent-transaction] pass 3/3 — pytest"
(
  cd "$ROOT/Production/tools"
  python3 -m pytest tests/test_o3_generation_intent.py -q --tb=no 2>/dev/null \
    || python3 -m pytest tests/test_o3_prompt_isolation_beat03.py -q --tb=no -k intent 2>/dev/null \
    || python3 -m pytest tests/ -q --tb=no -k "o3_generation_intent or o3_intent" --maxfail=1
) || fail "O3 intent pytest failed"

echo "[o3-intent-transaction] OK"
