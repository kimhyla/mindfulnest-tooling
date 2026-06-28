#!/usr/bin/env bash
# verify_bg_directus_export_durability.sh — BG_DIRECTUS_EXPORT_V1
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
Kling="${REPO_ROOT}/Production/tools/server_handlers/kling_o3.py"
REGISTER="${REPO_ROOT}/Production/tools/bg_directus_register.py"
TEST="${REPO_ROOT}/Production/tools/tests/test_bg_directus_export_register.py"

fail() { echo "[bg-directus-export-durability] FAIL: $1" >&2; exit 1; }

[[ -f "$REGISTER" ]] || fail "missing bg_directus_register.py"
[[ -f "$Kling" ]] || fail "missing kling_o3.py"
[[ -f "$TEST" ]] || fail "missing test_bg_directus_export_register.py"

grep -q 'BG_DIRECTUS_EXPORT_V1' "$REGISTER" \
  || fail "bg_directus_register.py missing BG_DIRECTUS_EXPORT_V1 marker"

grep -q 'register_bg_export_to_directus' "$Kling" \
  || fail "kling_o3.py export handler missing register_bg_export_to_directus"

grep -q 'preserve_kling_o3_segment_beats' "$Kling" \
  || fail "kling_o3.py export handler missing segment preserve on export"

grep -q 'resolve_segment_stitch_export_clip_paths' "${REPO_ROOT}/Production/tools/beat_generator.py" \
  || fail "beat_generator.py missing shared export clip resolver"

python3 -m pytest "$TEST" -q

echo "[bg-directus-export-durability] OK — source guards + pytest passed"
