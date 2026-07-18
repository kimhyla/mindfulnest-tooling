#!/usr/bin/env bash
# HOT_SERVE_ALL_FILES_V1 — /files must rematerialize cloud media before any read.
# Bug class (Event_3, 2026-07-17): Phase B voice stem GET /files returned 500
# Errno 11 because non-video paths bypassed ensure_hot_serve_file.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PS="$ROOT/Production/tools/production_server.py"
MPC="$ROOT/Production/tools/media_playback_cache.py"
TEST="$ROOT/Production/tools/tests/test_media_playback_cache.py"

fail() { echo "FATAL: $*" >&2; exit 1; }

grep -q "HOT_SERVE_ALL_FILES_V1" "$PS" \
  || fail "marker HOT_SERVE_ALL_FILES_V1 missing from production_server.py"
grep -q "_ensure_local_file_for_serve" "$PS" \
  || fail "_ensure_local_file_for_serve missing"

# Non-video /files path must call hot-serve before open().read().
python3 - "$PS" <<'PY' || fail "source contract: /files must hot-serve before open"
import sys
from pathlib import Path
ps = Path(sys.argv[1]).read_text(encoding="utf-8")
start = ps.find("def _handle_files_serve")
end = ps.find("\n    def _handle_cr_save_crop", start)
body = ps[start:end]
if "_ensure_local_file_for_serve" not in body:
    raise SystemExit("hot-serve not called inside _handle_files_serve")
# Prefer serve_path (post CodeQL re-gate); accept file_path for older trees.
open_idx = body.find('open(serve_path, "rb")')
if open_idx < 0:
    open_idx = body.find('open(file_path, "rb")')
hot_idx = body.find("_ensure_local_file_for_serve")
if open_idx < 0 or hot_idx < 0 or hot_idx > open_idx:
    raise SystemExit("ensure_local must precede open(...) in _handle_files_serve")
if "HOT_SERVE_MATERIALIZE_FAILED" not in body:
    raise SystemExit("materialize failure must map to HOT_SERVE_MATERIALIZE_FAILED")
# Native CodeQL sanitizer: realpath + startswith before the open sink.
if "serve_path.startswith" not in body:
    raise SystemExit("post-hot-serve must re-gate with startswith before open")
print("OK source contract")
PY

# LRU cleanup must cover audio stems (pb_*), not only .mp4.
grep -Fq 'name.startswith("pb_")' "$MPC" \
  || fail "playback_cache_lru_cleanup must retain pb_* (all extensions)"
grep -q "test_ensure_hot_serve_file_remaps_cloud_mp3_stem" "$TEST" \
  || fail "mp3 stem hot-serve test missing"

cd "$ROOT/Production/tools"
python3 -m pytest tests/test_media_playback_cache.py -q \
  --tb=line -k "ensure_hot_serve_file"
echo "OK: HOT_SERVE_ALL_FILES_V1 durability"
