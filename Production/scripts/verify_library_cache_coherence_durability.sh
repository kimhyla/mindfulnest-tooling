#!/usr/bin/env bash
# LIBRARY_CLIENT_CACHE_COHERENCE_V2 — tagged optimistic merge + upload visibility.
# LIBRARY_CLIENT_CACHE_COHERENCE_V1 — legacy marker retained for closure grep.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SB="$ROOT/Production/tools/storyboard-v2"

fail=0
mark() { echo "  OK  $1"; }
err() { echo "  FAIL $1"; fail=1; }

grep -q 'LIBRARY_CLIENT_CACHE_COHERENCE_V2' "$SB/src/utils/libraryCachePolicy.ts" \
  && grep -q 'LIBRARY_CLIENT_CACHE_COHERENCE_V1' "$SB/src/utils/libraryCachePolicy.ts" \
  && mark 'libraryCachePolicy V2 + V1 grep markers' \
  || err 'missing libraryCachePolicy markers'

grep -q 'markLibraryOptimistic' "$SB/src/utils/libraryCachePolicy.ts" \
  && grep -q 'itemsForLibrarySessionPersist' "$SB/src/utils/libraryCachePolicy.ts" \
  && mark 'tagged optimistic merge API' \
  || err 'missing tagged optimistic API'

grep -q 'mergeLibraryRefetchWithOptimistic' "$SB/src/components/LibraryPanel.tsx" \
  && grep -q 'invalidateLibrarySessionCache' "$SB/src/components/LibraryPanel.tsx" \
  && grep -q 'libraryItemFromUpload' "$SB/src/components/LibraryPanel.tsx" \
  && grep -q 'markLibraryOptimistic' "$SB/src/components/LibraryPanel.tsx" \
  && mark 'LibraryPanel uses V2 cache policy + upload row' \
  || err 'LibraryPanel missing V2 wiring'

grep -q 'mn.library.items.v5' "$SB/src/utils/libraryCachePolicy.ts" \
  && mark 'v5 session key (flushes poisoned v4 cache)' \
  || err 'libraryCachePolicy missing v5 session key'

test -f "$SB/src/utils/libraryUpload.ts" \
  && grep -q 'libraryItemFromUpload' "$SB/src/utils/libraryUpload.ts" \
  && mark 'libraryUpload.ts present' \
  || err 'missing libraryUpload.ts'

(
  cd "$SB"
  npx --yes vitest run src/utils/__tests__/libraryCachePolicy.test.ts
) && mark 'vitest libraryCachePolicy.test.ts' || err 'vitest libraryCachePolicy.test.ts failed'

awk '/const onUpload = async/,/^  };/' "$SB/src/components/LibraryPanel.tsx" | grep -q 'invalidateLibrarySessionCache' \
  && awk '/const onUpload = async/,/^  };/' "$SB/src/components/LibraryPanel.tsx" | grep -q 'prependCropLibraryItem' \
  && mark 'upload path invalidates cache + prepends optimistic row' \
  || err 'upload path missing invalidate or prepend'

test -f "$ROOT/Production/docs/TECH_SPEC_LIBRARY_CLIENT_CACHE_COHERENCE_V2.md" \
  && mark 'TECH_SPEC_LIBRARY_CLIENT_CACHE_COHERENCE_V2.md' \
  || err 'missing TECH_SPEC_LIBRARY_CLIENT_CACHE_COHERENCE_V2.md'

exit "$fail"
