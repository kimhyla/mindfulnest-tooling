#!/usr/bin/env bash
# LIBRARY_CLIENT_CACHE_COHERENCE_V1 — unified cache bust + optimistic merge.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SB="$ROOT/Production/tools/storyboard-v2"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

grep -q 'LIBRARY_CLIENT_CACHE_COHERENCE_V1' "$SB/src/utils/libraryCachePolicy.ts" \
  && mark 'libraryCachePolicy module' \
  || err 'missing libraryCachePolicy.ts'

grep -q 'mergeLibraryRefetchWithOptimistic' "$SB/src/components/LibraryPanel.tsx" \
  && grep -q 'invalidateLibrarySessionCache' "$SB/src/components/LibraryPanel.tsx" \
  && mark 'LibraryPanel uses cache policy' \
  || err 'LibraryPanel missing cache policy wiring'

grep -q 'mn.library.items.v4' "$SB/src/utils/libraryCachePolicy.ts" \
  && mark 'v4 session key in libraryCachePolicy authority' \
  || err 'libraryCachePolicy missing v4 session key'

exit "$fail"
