#!/usr/bin/env bash
# verify_library_audio_durability.sh — Library SFX/ambient preview + upload durability.
#
# Regression classes (2026-06-12):
#   1. LibraryPanel only loaded cr_library → SFX "disappeared"
#   2. upload accept= image-only → MP3 grayed out
#   3. audio_file route did not URL-decode spaced ambient filenames → 0:00 preview
set -euo pipefail

ROOT="${MN_TOOLING_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
LIB="$ROOT/Production/tools/storyboard-v2/src/components/LibraryPanel.tsx"
ENDPOINTS="$ROOT/Production/tools/storyboard-v2/src/api/endpoints.ts"
CROPPER="$ROOT/Production/tools/server_handlers/cropper.py"
SERVER="$ROOT/Production/tools/production_server.py"
DIST="$ROOT/Production/tools/storyboard-v2/dist/index.html"
TESTS="$ROOT/Production/tools/tests"

fail() { echo "FATAL: $1" >&2; exit 1; }

grep -q 'LIBRARY_AUDIO_PREVIEW_V1' "$LIB" || fail "missing LIBRARY_AUDIO_PREVIEW_V1 marker"
grep -q 'stitchLibraryToLibItems' "$LIB" || fail "missing stitchLibraryToLibItems"
grep -q "stitch_editor_library" "$LIB" || fail "LibraryPanel must load stitch_editor/library"
grep -q 'libraryAudioPreviewUrl' "$LIB" || fail "missing libraryAudioPreviewUrl"
grep -q 'encodeURIComponent' "$LIB" || fail "audio preview URLs must encode filenames"
grep -q 'stitch_editor_library' "$ENDPOINTS" || fail "endpoints.ts missing stitch_editor_library"
grep -q 'sound_library' "$CROPPER" || fail "cr_upload must write to sound_library"
grep -q 'urllib.parse.unquote' "$SERVER" || fail "audio_file route must URL-decode filenames"
grep -q 'sound_library/ambient' "$SERVER" || fail "audio serve must scan sound_library/ambient"

[[ -f "$TESTS/test_cr_upload_audio.py" ]] || fail "missing test_cr_upload_audio.py"
[[ -f "$TESTS/test_stitch_audio_file_serve.py" ]] || fail "missing test_stitch_audio_file_serve.py"

if [[ -f "$DIST" ]]; then
  grep -q 'LIBRARY_AUDIO_PREVIEW_V1' "$DIST" || fail "dist missing LIBRARY_AUDIO_PREVIEW_V1"
  grep -q 'library-preview-audio' "$DIST" || fail "dist missing library-preview-audio testid"
fi

echo "[library-audio-durability] OK — source + dist markers + tests present"
