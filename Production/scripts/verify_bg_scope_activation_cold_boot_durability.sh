#!/usr/bin/env bash
# BG_SCOPE_ACTIVATION_COLD_BOOT_ONLY_V1 — warm GET must not re-run mirror reconcile.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="${MN_TOOLING_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}/Production/tools"
BG="${TOOLS}/beat_generator.py"

echo "=== bg scope activation cold-boot-only durability ==="

grep -q '_BG_ACTIVE_SCOPE_KEY' "${BG}" \
  || { echo "FATAL: _BG_ACTIVE_SCOPE_KEY missing from beat_generator.py" >&2; exit 1; }

grep -q 'def _run_bg_paths_cold_boot' "${BG}" \
  || { echo "FATAL: _run_bg_paths_cold_boot missing" >&2; exit 1; }

python3 - <<PY
from pathlib import Path
text = Path("${BG}").read_text(encoding="utf-8")
init = text.split("def _init_bg_paths_unlocked", 1)[1].split("\ndef ", 1)[0]
cold = text.split("def _run_bg_paths_cold_boot", 1)[1].split("\ndef ", 1)[0]
if "reconcile_sqlite_segment_beats_from_json_mirror" in init:
    raise SystemExit("FATAL: mirror reconcile still inline in _init_bg_paths_unlocked")
if "reconcile_sqlite_segment_beats_from_json_mirror" not in cold:
    raise SystemExit("FATAL: mirror reconcile missing from _run_bg_paths_cold_boot")
print("[scope-cold-boot] struct OK")
PY

cd "${TOOLS}"
python3 -m pytest tests/test_bg_scope_activation_cold_boot_only.py -q

echo "[scope-cold-boot] OK"
