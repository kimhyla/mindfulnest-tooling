#!/usr/bin/env bash
# Visible magic contract gate — all events, intro + resolution, magic_still + magic_video.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"
echo "[visible-magic-contract] version marker..."
python3 -c "import sys; sys.path.insert(0,'Production/tools'); from magic_render_contract import MAGIC_RENDER_CONTRACT_VERSION; print(MAGIC_RENDER_CONTRACT_VERSION)"
echo "[visible-magic-contract] pytest magic durability suite..."
python3 -m pytest \
  Production/tools/tests/test_magic_render_contract_durability.py \
  Production/tools/tests/test_magic_golden_beat01_replay.py \
  Production/tools/tests/test_magic_path_polyline.py \
  Production/tools/tests/test_bg_magic_sync.py \
  -q
echo "[visible-magic-contract] all gates passed"
