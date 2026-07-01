#!/usr/bin/env bash
# verify_stitch_four_files_durability.sh — STITCH_FOUR_FILES_V1 multipass gate
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOLS="$ROOT/Production/tools"
cd "$TOOLS"

fail() { echo "FATAL: $1" >&2; exit 1; }

echo "=== STITCH_FOUR_FILES_V1 durability ==="

echo "[1/6] pytest four-files authority + client playback"
python3 -m pytest tests/test_stitch_four_files_playback_authority.py -v --tb=short
python3 -m pytest tests/test_stitch_four_files_client_playback.py -v --tb=short

echo "[2/6] static: upsert branch present"
grep -q "bake_and_persist_slot_playback_mp4" server_handlers/stitch_editor.py
grep -q "STITCH_FOUR_FILES_V1" server_handlers/stitch_slot_playback.py

echo "[3/6] static: client four-files read gate"
grep -q "stitchSlotUsesFourFilesPlayback" storyboard-v2/src/utils/stitchJobMediaHydrate.ts
grep -q "stitchSlotUsesFourFilesPlayback(slot)" storyboard-v2/src/utils/stitchJobMediaHydrate.ts
grep -q "STITCH_FOUR_FILES_V1" storyboard-v2/src/utils/stitchSlotMuxAudioSig.ts
grep -q "stitchSlotUsesFourFilesPlayback(slotData)" storyboard-v2/src/components/StitcherTab.tsx

echo "[4/6] static: server preview passthrough"
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

echo "[5/6] static: invalidation clears playback recipe"
grep -q 'slot.pop("playback_recipe_version", None)' "$ROOT/Production/tools/bg_o3_stitch_invalidation.py" \
  || fail "invalidation must clear playback_recipe_version"

echo "[6/6] static: module bake passthrough"
grep -q "playback_recipe_is_four_files" production_server.py

echo "OK verify_stitch_four_files_durability"
