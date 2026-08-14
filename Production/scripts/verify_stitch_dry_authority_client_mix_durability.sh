#!/usr/bin/env bash
# verify_stitch_dry_authority_client_mix_durability.sh — FF-042 multipass gate
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

echo "[FF-042] pytest bundle"
python3 -m pytest \
  tests/test_stitch_dry_authority_client_mix.py \
  tests/test_stitch_export_truth_durability.py \
  tests/test_stitch_four_files_playback_authority.py \
  tests/test_stitch_sfx_hot_serve_prefetch.py \
  tests/test_stitch_dry_hot_serve_playback.py \
  -q --tb=short

echo "[FF-042] marker grep"
grep -q STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 server_handlers/stitch_slot_playback.py
grep -q persist_dry_authority_slot_export server_handlers/stitch_editor.py
grep -q StitchSlotAudioMixEngine storyboard-v2/src/audio/StitchSlotAudioMixEngine.ts
grep -q STITCH_SFX_HOT_SERVE_PREFETCH_V1 storyboard-v2/src/audio/StitchSlotAudioMixEngine.ts
grep -q prefetchAllSfx storyboard-v2/src/audio/StitchSlotAudioMixEngine.ts
grep -q STITCH_DRY_HOT_SERVE_PLAYBACK_V1 storyboard-v2/src/utils/stitchDryHotServePlayback.ts
grep -q slot_ambient_loop production_server.py

echo "[FF-042] verify_stitch_dry_authority_client_mix_durability.sh OK"
