#!/usr/bin/env bash
# STITCH_SLOT_ARTIFACT_FRESHNESS_V1
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TOOLS="${ROOT}/Production/tools"
cd "${TOOLS}"
PYTHONPATH="${ROOT}/Production:${ROOT}" python3 -m pytest tests/test_stitch_slot_artifact_freshness.py -q
grep -q 'purgeStitchSlotPlaybackCache' "${TOOLS}/storyboard-v2/src/utils/stitchJobMediaHydrate.ts" \
  || { echo "FATAL: hydrate must purge stale playback cache" >&2; exit 1; }
echo "=== stitch slot artifact freshness OK ==="
