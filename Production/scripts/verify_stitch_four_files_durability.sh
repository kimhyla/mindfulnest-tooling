#!/usr/bin/env bash
# verify_stitch_four_files_durability.sh — STITCH_FOUR_FILES_V1 multipass gate
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail() { echo "FATAL: $1" >&2; exit 1; }

echo "=== STITCH_FOUR_FILES_V1 durability ==="

echo "[1/8] pytest four-files authority + client playback"
python3 -m pytest tests/test_stitch_four_files_playback_authority.py -v --tb=short
python3 -m pytest tests/test_stitch_four_files_client_playback.py -v --tb=short

echo "[2/8] static: Send uses dry concat; four-files bake kept for rebake"
grep -q "persist_dry_authority_slot_export" server_handlers/stitch_editor.py
grep -q "bake_and_persist_slot_playback_mp4" server_handlers/stitch_slot_playback.py
grep -q "STITCH_FOUR_FILES_V1" server_handlers/stitch_slot_playback.py

echo "[3/8] static: client four-files read gate"
grep -q "stitchSlotUsesFourFilesPlayback" storyboard-v2/src/utils/stitchJobMediaHydrate.ts
grep -q "stitchSlotUsesFourFilesPlayback(slot)" storyboard-v2/src/utils/stitchJobMediaHydrate.ts
grep -q "STITCH_FOUR_FILES_V1" storyboard-v2/src/utils/stitchSlotMuxAudioSig.ts
grep -q "stitchSlotUsesFourFilesPlayback(slotData)" storyboard-v2/src/components/StitcherTab.tsx

echo "[4/8] static: server preview passthrough"
preview_block="$(python3 - "$TOOLS/server_handlers/stitch_editor.py" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
start = src.index("def handle_stitch_preview")
end = src.index("\ndef ", start + 1)
print(src[start:end])
PY
)"
echo "$preview_block" | grep -q "playback_recipe_is_four_files(slot)" \
  || fail "handle_stitch_preview must passthrough four-files slots"
echo "$preview_block" | grep -q "four_files_passthrough" \
  || fail "handle_stitch_preview missing four_files_passthrough marker"

echo "[5/8] static: invalidation clears playback recipe"
grep -q 'slot.pop("playback_recipe_version", None)' "$ROOT/Production/tools/bg_o3_stitch_invalidation.py" \
  || fail "invalidation must clear playback_recipe_version"

echo "[6/8] static: four-files legacy purge gates"
grep -q 'STITCH_FOUR_FILES_LEGACY_PURGE_V1' server_handlers/stitch_slot_playback.py \
  || fail "missing STITCH_FOUR_FILES_LEGACY_PURGE_V1 marker"
grep -q 'slot_skips_legacy_playback_artifact_tiers' server_handlers/stitch_slot_edit_dispatch.py \
  || fail "slot_needs_ambient_rebuild must skip four-files"
grep -q 'reconcile_four_files_slot_authority' server_handlers/stitch_editor.py \
  || fail "load_job must purge four-files legacy fields"
rebuild_block="$(python3 - "$TOOLS/server_handlers/stitch_editor.py" <<'PY'
import sys
from pathlib import Path
src = Path(sys.argv[1]).read_text(encoding="utf-8")
start = src.index("def rebuild_stitch_ambient_mixes_for_job")
end = src.index("\ndef handle_stitch_save_job", start)
print(src[start:end])
PY
)"
echo "$rebuild_block" | grep -q 'slot_skips_legacy_playback_artifact_tiers(slot)' \
  || fail "rebuild_stitch_ambient_mixes must skip four-files slots"
grep -q 'reconcileFourFilesSlotArtifacts' storyboard-v2/src/utils/stitchJobMediaHydrate.ts \
  || fail "client hydrate must reconcile four-files legacy artifacts"

echo "[7/8] pytest legacy purge contract"
python3 -m pytest tests/test_stitch_four_files_legacy_purge.py -v --tb=short

echo "[8/8] static: module bake passthrough"
grep -q "playback_recipe_is_four_files" production_server.py

echo "OK verify_stitch_four_files_durability"
