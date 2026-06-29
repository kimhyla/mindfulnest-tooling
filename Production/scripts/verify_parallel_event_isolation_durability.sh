#!/usr/bin/env bash
# verify_parallel_event_isolation_durability.sh — PARALLEL_EVENT_ISOLATION_V1 gate
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
TOOLS="$ROOT/Production/tools"
PY="${MN_PYTHON:-${HOME}/.pyenv/versions/3.12.7/bin/python3}"

echo "[parallel-event-isolation] spec + wiring"
grep -q "PARALLEL_EVENT_ISOLATION_V1" "$ROOT/Production/docs/TECH_SPEC_PARALLEL_EVENT_ISOLATION_V1.md"
grep -q "MN_SIDECAR_MIRROR_PATH" "$ROOT/Production/scripts/install_production_server_launchagent.sh"
grep -q "force=False" "$ROOT/Production/tools/server_handlers/background.py"
grep -q "event_sidecar_mirror_path" "$ROOT/Production/lib/paths.py"

echo "[parallel-event-isolation] pytest"
(
  cd "$TOOLS"
  "$PY" -m pytest tests/test_parallel_event_isolation_v1.py -v
)

echo "[parallel-event-isolation] OK"
